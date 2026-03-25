import json
from typing import Sequence

from pydantic import BaseModel
import pydantic

from frec_server.llm.inference import ChatMessage, LlmInference
from frec_server.llm.prompt_templates import PromptTemplate
from frec_server.persistence import models


def generate_conversation_title_prompt(
    messages: Sequence[models.ChatMessage],
) -> list[ChatMessage]:
    prompt = PromptTemplate.from_path("./prompts/conversation_title_generator")
    prompt_msgs = prompt.render({})

    conv_log_msg = ""
    for msg in messages:
        if msg.role in [models.MessageRole.Assistant, models.MessageRole.User]:
            conv_log_msg += f"###{msg.role} said:###\n{msg.visible_content}\n-------\n"
    prompt_msgs.append(ChatMessage(role="user", content=conv_log_msg))

    return prompt_msgs


class ConversationTitleResponse(BaseModel):
    chat_name: str | None


async def try_generate_conversation_title(
    llm: LlmInference, llm_model: str, messages: Sequence[models.ChatMessage]
) -> str | None:
    prompt = generate_conversation_title_prompt(messages)
    response = await llm.chat_complete(
        llm_model,
        prompt,
        json_schema=ConversationTitleResponse.model_json_schema(),
    )
    try:
        return ConversationTitleResponse.model_validate_json(response.content).chat_name
    except pydantic.ValidationError:
        return None
