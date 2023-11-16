#!/usr/bin/env python

# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import subprocess
from HTMLTestRunner import HTMLTestRunner
import test.constants as constants

class DockerSanityTest(unittest.TestCase):
    IMAGE="apache/kafka"
    
    def resume_container(self):
        subprocess.run(["docker", "start", constants.BROKER_CONTAINER])

    def stop_container(self) -> None:
        subprocess.run(["docker", "stop", constants.BROKER_CONTAINER])

    def start_compose(self, filename) -> None:
        old_string="image: {$IMAGE}"
        new_string=f"image: {self.IMAGE}"
        with open(filename) as f:
            s = f.read()
        with open(filename, 'w') as f:
            s = s.replace(old_string, new_string)
            f.write(s)

        subprocess.run(["docker-compose", "-f", filename, "up", "-d"])
    
    def destroy_compose(self, filename) -> None:
        old_string=f"image: {self.IMAGE}"
        new_string="image: {$IMAGE}"
        subprocess.run(["docker-compose", "-f", filename, "down"])
        with open(filename) as f:
            s = f.read()
        with open(filename, 'w') as f:
            s = s.replace(old_string, new_string)
            f.write(s)

    def create_topic(self, topic, topic_config):
        command = [constants.KAFKA_TOPICS, "--create", "--topic", topic]
        command.extend(topic_config)
        subprocess.run(command)
        check_command = [constants.KAFKA_TOPICS, "--list"]
        check_command.extend(topic_config)
        output = subprocess.check_output(check_command, timeout=constants.CLIENT_TIMEOUT)
        if topic in output.decode("utf-8"):
            return True
        return False
        
    def produce_message(self, topic, producer_config, key, value):
        command = ["echo", f'"{key}:{value}"', "|", constants.KAFKA_CONSOLE_PRODUCER, "--topic", topic, "--property", "'parse.key=true'", "--property", "'key.separator=:'"]
        command.extend(producer_config)
        subprocess.run(["bash", "-c", " ".join(command)], timeout=constants.CLIENT_TIMEOUT)
    
    def consume_message(self, topic, consumer_config):
        command = [constants.KAFKA_CONSOLE_CONSUMER, "--topic", topic, "--property", "'print.key=true'", "--property", "'key.separator=:'", "--from-beginning", "--max-messages", "1"]
        command.extend(consumer_config)
        message = subprocess.check_output(["bash", "-c", " ".join(command)], timeout=constants.CLIENT_TIMEOUT)
        return message.decode("utf-8").strip()
    
    def get_metrics(self, jmx_tool_config):
        command = [constants.KAFKA_RUN_CLASS, constants.JMX_TOOL]
        command.extend(jmx_tool_config)
        message = subprocess.check_output(["bash", "-c", " ".join(command)], timeout=constants.CLIENT_TIMEOUT)
        return message.decode("utf-8").strip().split()
    
    def broker_metrics_flow(self):
        print(f"Running {constants.BROKER_METRICS_TESTS}")
        errors = []
        try:
            self.assertTrue(self.create_topic(constants.BROKER_METRICS_TEST_TOPIC, ["--bootstrap-server", "localhost:9092"]))
        except AssertionError as e:
            errors.append(constants.BROKER_METRICS_ERROR_PREFIX + str(e))
            return errors
        jmx_tool_config = ["--one-time", "--object-name", "kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec", "--jmx-url", "service:jmx:rmi:///jndi/rmi://:9101/jmxrmi"]
        metrics_before_message = self.get_metrics(jmx_tool_config)
        try:
            self.assertEqual(len(metrics_before_message), 2)
            self.assertEqual(metrics_before_message[0], constants.BROKER_METRICS_HEADING)
        except AssertionError as e:
            errors.append(constants.BROKER_METRICS_ERROR_PREFIX + str(e))
            return errors

        producer_config = ["--bootstrap-server", "localhost:9092", "--property", "client.id=host"]
        self.produce_message(constants.BROKER_METRICS_TEST_TOPIC, producer_config, "key", "message")
        consumer_config = ["--bootstrap-server", "localhost:9092", "--property", "auto.offset.reset=earliest"]
        message = self.consume_message(constants.BROKER_METRICS_TEST_TOPIC, consumer_config)
        try:
            self.assertEqual(message, "key:message")
        except AssertionError as e:
            errors.append(constants.BROKER_METRICS_ERROR_PREFIX + str(e))
            return errors
        
        metrics_after_message = self.get_metrics(jmx_tool_config)
        try:
            self.assertEqual(len(metrics_before_message), 2)
            self.assertEqual(metrics_after_message[0], constants.BROKER_METRICS_HEADING)
            before_metrics_data, after_metrics_data = metrics_before_message[1].split(","), metrics_after_message[1].split(",")
            self.assertEqual(len(before_metrics_data), len(after_metrics_data))
            print(before_metrics_data[1])
            print(after_metrics_data[1])
            for i in range(len(before_metrics_data)):
                if after_metrics_data[i].replace(".", "").isnumeric():
                    self.assertGreater(float(after_metrics_data[i]), float(before_metrics_data[i]))
                else:
                    self.assertEqual(after_metrics_data[i], before_metrics_data[i])
        except AssertionError as e:
            errors.append(constants.BROKER_METRICS_ERROR_PREFIX + str(e))

        return errors

    def ssl_flow(self, ssl_broker_port, test_name, test_error_prefix, topic):
        print(f"Running {test_name}")
        errors = []
        try:
            self.assertTrue(self.create_topic(topic, ["--bootstrap-server", ssl_broker_port, "--command-config", constants.SSL_CLIENT_CONFIG]))
        except AssertionError as e:
            errors.append(test_error_prefix + str(e))
            return errors

        producer_config = ["--bootstrap-server", ssl_broker_port,
                           "--producer.config", constants.SSL_CLIENT_CONFIG]
        self.produce_message(topic, producer_config, "key", "message")

        consumer_config = [
            "--bootstrap-server", ssl_broker_port,
            "--property", "auto.offset.reset=earliest",
            "--consumer.config", constants.SSL_CLIENT_CONFIG,
        ]
        message = self.consume_message(topic, consumer_config)
        try:
            self.assertEqual(message, "key:message")
        except AssertionError as e:
            errors.append(test_error_prefix + str(e))
        
        return errors
    
    def broker_restart_flow(self):
        print(f"Running {constants.BROKER_RESTART_TESTS}")
        errors = []
        
        try:
            self.assertTrue(self.create_topic(constants.BROKER_RESTART_TEST_TOPIC, ["--bootstrap-server", "localhost:9092"]))
        except AssertionError as e:
            errors.append(constants.BROKER_RESTART_ERROR_PREFIX + str(e))
            return errors
        
        producer_config = ["--bootstrap-server", "localhost:9092", "--property", "client.id=host"]
        self.produce_message(constants.BROKER_RESTART_TEST_TOPIC, producer_config, "key", "message")

        print("Stopping Container")
        self.stop_container()
        print("Resuming Container")
        self.resume_container()

        consumer_config = ["--bootstrap-server", "localhost:9092", "--property", "auto.offset.reset=earliest"]
        message = self.consume_message(constants.BROKER_RESTART_TEST_TOPIC, consumer_config)
        try:
            self.assertEqual(message, "key:message")
        except AssertionError as e:
            errors.append(constants.BROKER_RESTART_ERROR_PREFIX + str(e))
        
        return errors

    def execute(self):
        total_errors = []
        try:
            total_errors.extend(self.broker_metrics_flow())
        except Exception as e:
            print(constants.BROKER_METRICS_ERROR_PREFIX, str(e))
            total_errors.append(str(e))
        try:
            total_errors.extend(self.ssl_flow('localhost:9093', constants.SSL_FLOW_TESTS, constants.SSL_ERROR_PREFIX, constants.SSL_TOPIC))
        except Exception as e:
            print(constants.SSL_ERROR_PREFIX, str(e))
            total_errors.append(str(e))
        try:
            total_errors.extend(self.ssl_flow('localhost:9094', constants.FILE_INPUT_FLOW_TESTS, constants.FILE_INPUT_ERROR_PREFIX, constants.FILE_INPUT_TOPIC))
        except Exception as e:
            print(constants.FILE_INPUT_ERROR_PREFIX, str(e))
            total_errors.append(str(e))
        try:
            total_errors.extend(self.broker_restart_flow())
        except Exception as e:
            print(constants.BROKER_RESTART_ERROR_PREFIX, str(e))
            total_errors.append(str(e))
        
        self.assertEqual(total_errors, [])

class DockerSanityTestJVM(DockerSanityTest):
    def setUp(self) -> None:
        self.start_compose(constants.JVM_COMPOSE)
    def tearDown(self) -> None:
        self.destroy_compose(constants.JVM_COMPOSE)
    def test_bed(self):
        self.execute()

def run_tests(image, mode):
    DockerSanityTest.IMAGE = image

    test_classes_to_run = []
    if mode == "jvm":
        test_classes_to_run = [DockerSanityTestJVM]
    
    loader = unittest.TestLoader()
    suites_list = []
    for test_class in test_classes_to_run:
        suite = loader.loadTestsFromTestCase(test_class)
        suites_list.append(suite)
    big_suite = unittest.TestSuite(suites_list)
    outfile = open(f"report_{mode}.html", "w")
    runner = HTMLTestRunner.HTMLTestRunner(
                stream=outfile,
                title='Test Report',
                description='This demonstrates the report output.'
                )
    result = runner.run(big_suite)
    return result.failure_count
