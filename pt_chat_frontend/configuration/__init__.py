import os
from pathlib import Path
import sys
from typing import Annotated, Literal, Optional, Union
from dotenv import load_dotenv
from jinja2 import Environment, StrictUndefined
import pydantic
from pydantic import BaseModel
import yaml

from frec_server.persistence import models

class PropmptConfig(BaseModel):
    """Various bits of the prompt can be customized by specifying these sections in the
    config file. If left blank (None), we take the defaults from the FREC prompt."""
    prompt_identity: str | None = None
    propmpt_purpose: str | None = None
    propmpt_task: str | None = None
    prompt_how_to_use_tools: str | None = None
    prompt_tool_call_rules: str | None = None
    prompt_final_generic_rules: str | None = None
    prompt_date: str | None = None
    prompt_next_up: str | None = None
    prompt_language_switch: str | None = None

class ToolsetBase(BaseModel):
    name: str
    custom_instructions: str | None = None


class McpToolset(ToolsetBase):
    kind: Literal["mcp"] = "mcp"
    endpoint: str


class ExternalTool(BaseModel):
    name: str
    description: str
    input_schema: dict


class ExternalToolset(ToolsetBase):
    kind: Literal["external"] = "external"
    tools: dict[str, ExternalTool]


class RagToolset(ToolsetBase):
    kind: Literal["rag"] = "rag"
    url: str
    # NOTE: Storing tokens in the config file is not the best idea, even though this
    # doesn't need to be checked into the repo. However, we need some secrets management.
    token: str


class AgentToolset(ToolsetBase):
    kind: Literal["agent"] = "agent"
    # Name of the agent inside the agent server. We decoupled this name from the
    # toolset name, which may be more human-readable, and from the toolset key.
    # The latter is important because you may end up having to call two agents
    # with the same name in two different servers, and we need to be able to
    # disambiguate
    agent_key: str
    # URL of the agent. Only the name of the server and port, without trailing
    # slash. The code will generate the URLs for the endpoints to: (1) Retrieve
    # the agent description, (2) Initiate a session and (3) Post a message to
    # the agent and wait for its streaming response using SSE.
    url: str


Toolset = Annotated[
    McpToolset | ExternalToolset | RagToolset | AgentToolset,
    pydantic.Field(discriminator="kind"),
]


class ConfigFile(BaseModel):
    deploy_name: str
    prompt: PropmptConfig | None = None
    toolsets: dict[str, Toolset]

    @staticmethod
    def read_from_path(path: Path) -> Optional["ConfigFile"]:
        load_dotenv(".env")
        template_env = Environment(
            variable_start_string="${{",
            variable_end_string="}}",
            undefined=StrictUndefined,
            autoescape=False,
        )
        try:
            rendered_data = template_env.from_string(path.read_text()).render(**os.environ)
            py_data = yaml.load(rendered_data, Loader=yaml.Loader)
            return ConfigFile.model_validate(py_data)
        except Exception as e:
            print(f"[ERROR] Failed to load config file: {e}")
            return None


_global_config_file: ConfigFile | None = None


def get_config_file() -> ConfigFile:
    global _global_config_file
    if _global_config_file is None:
        config_path = Path(os.getenv("FREC_CONFIG_FILE") or "frec-config.yml")
        if (cfg_file := ConfigFile.read_from_path(config_path)) is not None:
            _global_config_file = cfg_file
        else:

            sys.exit(1)

    return _global_config_file
