#!/usr/bin/env python3

import subprocess
import argparse
import os

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

    command_args = ["docker", "compose", "-f", "./docker/docker-compose.yml"]
    if args.prod:
        command_args += ["-f", "./docker/docker-compose.prod.yml"]
    else:
        command_args += ["-f", "./docker/docker-compose.dev.yml"]

    command_args += [args.command]
    command_args += args.extra_args

    print("CMD", command_args)

    env = os.environ.copy()
    env["FREC_CONFIG_FILE"] = args.conf
    env["FREC_DEPLOY_MODE"] = "production" if args.prod else "development"

    subprocess.run(command_args, check=True, env=env)
