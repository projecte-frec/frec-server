#!/usr/bin/env python3

import subprocess
import argparse
import os
from pathlib import Path
import sys

# NOTE: PyYAML is vendored inside the repo so we can run this script without dependencies,
# since this is run outside of docker and we can only rely on the system's python.
import vendor.yaml as yaml

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prod", action="store_true", help="Run in production")
    parser.add_argument(
        "--conf",
        default="frec-config.yml",
        help="Path to the config file used inside the frec_server container",
    )
    parser.add_argument("command")
    parser.add_argument("extra_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    # Read the compose files from the config file. A docker deploy will be started by
    # including all the compose files.
    conf_file = yaml.load(Path(args.conf).read_text(), Loader=yaml.Loader)
    if conf_file is None:
        print(f"Error: Failed to read config file: '{args.conf}'")
        sys.exit(1)
    if type(conf_file) is not dict:
        print(
            f"Error: Wrong format for config file: '{args.conf}'. Should be a dictionary."
        )
        sys.exit(1)

    tool_compose_files = []
    if "toolsets" in conf_file:
        tool_compose_files = [
            x["compose-file"]
            for x in conf_file["toolsets"].values()
            if "compose-file" in x
        ]

    command_args = ["docker", "compose", "-f", "./docker/docker-compose.yml"]
    if args.prod:
        command_args += ["-f", "./docker/docker-compose.prod.yml"]
    else:
        command_args += ["-f", "./docker/docker-compose.dev.yml"]

    for compose_file in tool_compose_files:
        command_args += ["-f", compose_file]

    command_args += [args.command]
    command_args += args.extra_args

    print("CMD", command_args)

    env = os.environ.copy()
    env["FREC_CONFIG_FILE"] = args.conf
    env["FREC_DEPLOY_MODE"] = "production" if args.prod else "development"

    subprocess.run(command_args, check=True, env=env)
