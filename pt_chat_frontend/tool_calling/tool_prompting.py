import json
import re
from typing import Any, Sequence

from pydantic import BaseModel

from pt_chat_frontend.configuration import get_config_file
from pt_chat_frontend.llm.inference import ChatMessage
from pt_chat_frontend.llm.prompt_templates import PromptTemplate
from pt_chat_frontend.persistence import models


def try_parse_int(s: str, base=10, val=None) -> int | None:
    try:
        return int(s, base)
    except ValueError:
        return None


def try_parse_float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def try_parse_bool(b: str) -> bool | None:
    if b.lower().strip() == "true":
        return True
    elif b.lower().strip() == "false":
        return False
    else:
        return None


def assoc_in(obj, path, value):
    """Updates a value, deeply nested inside a data structure made up of lists and dicts
    so that the element at `path` ends up containing `value`."""
    curr_obj = obj
    for i in range(0, len(path)):
        kcurr = path[i]
        knext = path[i + 1] if i + 1 < len(path) else None

        # print(f"Iter {i} kcurr={kcurr}, knext={knext} obj={obj}, curr_obj={curr_obj}")

        if type(kcurr) is str:
            if type(curr_obj) is not dict:
                raise Exception("Try to assoc string key into a list")

            if type(knext) is int and kcurr not in curr_obj:
                curr_obj[kcurr] = []
            elif type(knext) is str and kcurr not in curr_obj:
                curr_obj[kcurr] = {}
            elif type(knext) is type(None):
                curr_obj[kcurr] = value

            curr_obj = curr_obj[kcurr]

        elif type(kcurr) is int:
            if type(curr_obj) is not list:
                raise Exception("Try to assoc int key into a dict")
            if len(curr_obj) <= kcurr:
                for i in range(0, kcurr - len(curr_obj) + 1):
                    curr_obj.append(None)

            if type(knext) is int and curr_obj[kcurr] is None:
                curr_obj[kcurr] = []
            elif type(knext) is str and curr_obj[kcurr] is None:
                curr_obj[kcurr] = {}
            elif type(knext) is type(None):
                curr_obj[kcurr] = value

            curr_obj = curr_obj[kcurr]

        else:
            raise Exception("Invalid item type in path. Should be string or int")


def parse_json_shorthand(text: str) -> dict:
    root_obj = {}
    accumulated = ""
    current_path = None

    def close_accumulated(accumulated: str):
        # print(f"Closing accumulated: {accumulated}")

        # Strip the trailing newline
        if accumulated.endswith("\n"):
            accumulated = accumulated[:-1]

        if (ival := try_parse_int(accumulated)) is not None:
            value = ival
        elif (fval := try_parse_float(accumulated)) is not None:
            value = fval
        elif (bval := try_parse_bool(accumulated)) is not None:
            value = bval
        else:
            value = accumulated

        assoc_in(root_obj, current_path, value)

    for line in text.splitlines():
        print(f"PARSING LINE '{line}'")
        key_marker = "##key##"
        if line.strip().startswith(key_marker):
            keypath = line.strip()[len(key_marker) :].strip()
            if current_path is not None:
                close_accumulated(accumulated)
            accumulated = ""

            # Split the path at common markers. This is a bit hacky, but we take advantage
            # from the fact that both [, ] and . are delimiters and work exactly the same
            # way in splitting path segments.
            keypath_pattern = r"[\[\]\.]+"
            current_path = re.split(keypath_pattern, keypath)

            # Parse integers in path
            for i, element in enumerate(current_path):
                if (intval := try_parse_int(element)) is not None:
                    current_path[i] = intval

            # Remove empty elements from path
            current_path = [
                x for x in current_path if type(x) is int or x.strip() != ""
            ]

            if len(current_path) == 0:
                raise ValueError(f"Bad format for key line: {line}")
        else:
            accumulated += line + "\n"

    if current_path is not None:
        close_accumulated(accumulated)
    accumulated = ""

    return root_obj


class ToolCallInPrompt(BaseModel):
    toolset: str
    tool: str
    args: dict


def parse_and_strip_tool_calls(text: str) -> tuple[str, list[ToolCallInPrompt]]:
    """
    Parse tool calls from message text in the format:
    <tool_call>..json data..</tool_call>
    """
    pattern = r"<tool_call toolset=\"(.*?)\" tool=\"(.*?)\">(.*?)</tool_call>"
    tool_calls = []

    for match in re.finditer(pattern, text, re.DOTALL):
        try:
            toolset = match.group(1).strip()
            tool = match.group(2).strip()
            tool_call_jshorthand = match.group(3).strip()
            tool_call_data = parse_json_shorthand(tool_call_jshorthand)
            tool_calls.append(
                ToolCallInPrompt(toolset=toolset, tool=tool, args=tool_call_data)
            )
        except Exception:
            print(f"Failed to parse tool call: {match.group(1)}")
            continue

    stripped = re.sub(pattern, "", text, flags=re.DOTALL).strip()

    return stripped, tool_calls


def start_tool_call_chat() -> list[ChatMessage]:
    config = get_config_file()
    prompt_template_args = {}
    if (prompt_cfg := config.prompt) is not None:
        prompt_template_args |= {
            k: v
            for k, v in prompt_cfg.model_dump().items()
            if v is not None and type(v) is str and v.strip() != ""
        }
    prompt = PromptTemplate.from_path("./prompts/chat_tools")
    return prompt.render(prompt_template_args)


def tool_call_result_prompt(tool_calls: Sequence[models.ToolCall]) -> str:
    content = "[System information]\nTool calls have provided the following replies:"
    for tool_call in tool_calls:
        content += f"Tool: {tool_call.display_name()}:"
        if tool_call.status == models.ToolCallStatus.Rejected:
            content += " permission declined by the user.\n"
        elif tool_call.status == models.ToolCallStatus.Completed:
            content += "\n"
            content += json.dumps(tool_call.tool_answer)
        else:
            print(
                "[WARNING]: Call to `tool_call_result_prompt` but some tools had not finished executing!"
            )
            content += " could not complete.\n"
    return content


def tool_call_result_verbatim_content(
    tool_calls: Sequence[models.ToolCall],
) -> str | None:
    parts: list[str] = []
    for tool_call in tool_calls:
        if tool_call.status != models.ToolCallStatus.Completed:
            continue
        if type(tool_call.tool_answer) is not dict:
            continue
        verbatim = tool_call.tool_answer.get("verbatim_response")
        if type(verbatim) is str and verbatim.strip() != "":
            parts.append(verbatim)

    if len(parts) == 0:
        return None
    return "\n\n".join(parts)


def toolset_prompt(toolset_key: str, custom_instructions: str | None, contents: str):
    prompt = f'<tool_set name="{toolset_key}">\n'
    if custom_instructions is not None and custom_instructions.strip() != "":
        prompt += f"   <instructions>\n"
        prompt += custom_instructions
        prompt += f"   </instructions>\n"

    prompt += contents
    prompt += "</tool_set>"
    return prompt


def tool_definition_prompt(
    tool_key: str, tool_description: str | None, json_schema: dict
):
    prompt = "<tool>\n"
    prompt += f"    <name>{tool_key}</name>\n"
    prompt += f"    <description>{tool_description}</description>\n"
    prompt += f"    <json_schema>{json.dumps(json_schema)}</json_schema>\n"
    prompt += "</tool>\n"
    return prompt

