import base64
import json
import traceback
from fastmcp import Client as FastMcpClient
import mcp
from pydantic import BaseModel
import uuid

from frec_server.persistence import models
from frec_server.persistence.db import Database
import frec_server.persistence.db_queries as queries
from frec_server.tool_calling.tool_prompting import (
    tool_definition_prompt,
    toolset_prompt,
)


class ChatToolFunction(BaseModel):
    name: str
    description: str | None
    json_schema: dict

    def to_prompt(self) -> str:
        return tool_definition_prompt(self.name, self.description, self.json_schema)


class ChatToolSet(BaseModel):
    toolset_key: str
    available_functions: dict[str, ChatToolFunction]

    def to_prompt(
        self,
        custom_instructions: str | None,
    ) -> str:
        return toolset_prompt(
            self.toolset_key,
            custom_instructions,
            str.join("\n", (t.to_prompt() for t in self.available_functions.values())),
        )


class McpConnectionError(BaseModel):
    error: str


class McpToolCallError(BaseModel):
    error: str


class ToolResponse(BaseModel):
    should_display_verbatim: bool
    response: str


async def check_status(
    toolset_key: str, endpoint: str
) -> ChatToolSet | McpConnectionError:
    try:
        async with FastMcpClient(endpoint) as client:
            available_fns: dict[str, ChatToolFunction] = {}
            tools = await client.list_tools()
            for tool in tools:
                available_fns[tool.name] = ChatToolFunction(
                    name=tool.name,
                    description=tool.description or "",
                    json_schema=tool.inputSchema,
                )
            return ChatToolSet(
                toolset_key=toolset_key, available_functions=available_fns
            )
    except Exception as e:
        return McpConnectionError(error=str(e))


def _decode_image_or_audio_data(b64_data: str) -> bytes:
    """
    MCP ImageContent.data and AudioContent.data is base64-encoded bytes. Some
    providers might send a data URL, so handle that too.
    """
    if "," in b64_data and b64_data.strip().startswith("data:"):
        # data:image/png;base64,AAA...
        b64_data = b64_data.split(",", 1)[1]
    return base64.b64decode(b64_data, validate=False)


async def call_tool(
    database: Database,
    conversation_id: uuid.UUID,
    endpoint: str,
    function: str,
    args: dict,
) -> ToolResponse | McpToolCallError:
    print(f"CALLING TOOL {function} with args {args}", flush=True)
    result = None
    async with FastMcpClient(endpoint) as client:
        try:
            result = await client.call_tool(function, args, raise_on_error=False)
            print(f"TOOL RESPONSE: {result}", flush=True)

            # NOTE: Sometimes MCP tools will respond with things like images, where we
            # don't want our model to read this text and reply to it, we just want to show
            # the output to the user. In those cases, we flag this response as a
            # "verbatim" response. Note that a response is only verbatim if everything in
            # it should be shown verbatim.
            result_texts = []
            should_display_verbatim: bool = True  # until proven otherwise

            for idx, block in enumerate(result.content):
                if type(block) == mcp.types.TextContent:
                    should_display_verbatim = False
                    result_texts.append(block.text)
                    # if idx < len(result.content) - 1:
                    #     result_text += "\n------\n"
                elif type(block) == mcp.types.ImageContent:
                    data = _decode_image_or_audio_data(block.data)
                    conv_file_id = queries.store_conversation_file(
                        database, conversation_id, data, block.mimeType
                    )
                    file_url = f"/chat/{conversation_id}/files/{conv_file_id}"
                    # Markdown inline image
                    result_texts.append(f"![Image]({file_url})")
                elif type(block) == mcp.types.AudioContent:
                    data = _decode_image_or_audio_data(block.data)
                    conv_file_id = queries.store_conversation_file(
                        database, conversation_id, data, block.mimeType
                    )
                    file_url = f"/chat/{conversation_id}/files/{conv_file_id}"
                    # inline HTML audio player
                    result_texts.append(
                        f"""<audio controls>
<source src="{file_url}" type="{block.mimeType}">
Your browser does not support the audio element.
</audio>"""
                    )
            final_result_text = "\n------\n".join(result_texts)
            print("Generated text response:", final_result_text, flush=True)
            return ToolResponse(
                response=final_result_text,
                should_display_verbatim=should_display_verbatim,
            )
        except Exception as e:
            print(f"ERROR on tool call: {result}", flush=True)
            print("Exception:", repr(e), flush=True)
            stack = traceback.format_exc()
            print(stack, flush=True)
            return McpToolCallError(error=str(e))
