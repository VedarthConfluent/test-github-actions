#!/usr/bin/env python

#
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
#

"""
Python script to build and push docker image
Usage: docker_release.py

Interactive utility to push the docker image to dockerhub
"""

import subprocess
from distutils.dir_util import copy_tree
from datetime import date
import shutil

def push_jvm(image, kafka_url):
    copy_tree("resources", "jvm/resources")
    subprocess.run(["docker", "buildx", "build", "-f", "jvm/Dockerfile", "--build-arg", f"kafka_url={kafka_url}", "--build-arg", f"build_date={date.today()}",
    "--push",
    "--platform", "linux/amd64,linux/arm64",
    "--tag", image, "jvm"])
    shutil.rmtree("jvm/resources")

def login():
    status = subprocess.run(["docker", "login"])
    if status.returncode != 0:
        print("Docker login failed, aborting the docker release")
        raise PermissionError

def create_builder():
    subprocess.run(["docker", "buildx", "create", "--name", "kafka-builder", "--use"])

def remove_builder():
    subprocess.run(["docker", "buildx", "rm", "kafka-builder"])

if __name__ == "__main__":
    print("\
          This script will build and push docker images of apache kafka.\n\
          Please ensure that image has been sanity tested before pushing the image")
    login()
    docker_registry = input("Enter the docker registry you want to push the image to [docker.io]: ")
    if docker_registry == "":
        docker_registry = "docker.io"
    docker_namespace = input("Enter the docker namespace you want to push the image to: ")
    image_name = input("Enter the image name: ")
    if image_name == "":
        raise ValueError("image name cannot be empty")
    image_tag = input("Enter the image tag for the image: ")
    if image_tag == "":
        raise ValueError("image tag cannot be empty")
    kafka_url = input("Enter the url for kafka binary tarball: ")
    if kafka_url == "":
        raise ValueError("kafka url cannot be empty")
    image = f"{docker_registry}/{docker_namespace}/{image_name}:{image_tag}"
    print(f"Docker image containing kafka downloaded from {kafka_url} will be pushed to {image}")
    proceed = input("Should we proceed? [y/N]: ")
    if proceed == "y":
        print("Building and pushing the image")
        create_builder()
        push_jvm(image, kafka_url)
        remove_builder()
        print(f"Image has been pushed to {image}")
    else:
        print("Image push aborted")
