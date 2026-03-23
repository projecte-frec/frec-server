#!/usr/bin/python3

import os
from pathlib import Path
import subprocess
import sys

print("Staring nginx wrapper entrypoint", flush=True)

conf_dir = Path("/etc/nginx/user_conf.d")
conf_template_dir = Path("/etc/nginx/user_conf.template.d")
env_vars_to_replace = ["NGINX_SERVER_NAME"]

for env_var in env_vars_to_replace:
    if os.getenv(env_var) is None:
        print(f"No ${env_var} defined.")
        sys.exit(1)
    print(
        f"Found {env_var}='" + (os.getenv(env_var) or "") + "'",
        flush=True,
    )


for file in conf_template_dir.glob("*.conf"):
    print(f"Substituting env vars in nginx config file {file}", flush=True)
    for env_var in env_vars_to_replace:
        conf_dir.joinpath(file.name).write_text(
            file.read_text().replace("${" + env_var + "}", os.getenv(env_var) or "")
        )

result = subprocess.run(["/scripts/start_nginx_certbot.sh"], check=False)
sys.exit(result.returncode)
