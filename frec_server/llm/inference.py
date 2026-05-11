from abc import ABC, abstractmethod
from typing import AsyncGenerator, Literal
import json
import ollama
import aiohttp

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "system", "assistant"]
    content: str


class LlmInference(ABC):
    @abstractmethod
    async def chat_complete(
        self, model: str, messages: list[ChatMessage], json_schema: dict | None
    ) -> ChatMessage: ...

    @abstractmethod
    def chat_stream(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncGenerator[str, None]: ...


class OpenAiCompatibleInference(LlmInference):
    endpoint: str
    api_key: str | None
    # temperature: float = 0.1

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    def request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _chat_request(
        self,
        model: str,
        messages: list[ChatMessage],
        json_schema: dict | None,
        stream: bool,
    ) -> dict:
        request_data = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            # "temperature": self.temperature,
            "stream": stream,
        }
        if json_schema is not None and not stream:
            request_data["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": json_schema,
                },
            }
        return request_data

    @staticmethod
    def _extract_content(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            result = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                # OpenAI-compatible responses may return a list of content parts.
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    result.append(part["text"])
            return "".join(result)
        return ""

    async def chat_complete(
        self, model: str, messages: list[ChatMessage], json_schema: dict | None
    ) -> ChatMessage:
        async with aiohttp.ClientSession() as session:
            request_data = self._chat_request(
                model=model, messages=messages, json_schema=json_schema, stream=False
            )
            resp = await session.post(
                f"{self.endpoint}/chat/completions",
                json=request_data,
                headers=self.request_headers(),
            )
            if not resp.ok and json_schema is not None:
                # Some OpenAI-compatible providers (for example some vLLM
                # setups) don't support response_format=json_schema. Retry with
                # a plain request. We assume the original messages already
                # explain that the answer must be a JSON.
                fallback_request_data = self._chat_request(
                    model=model,
                    messages=messages,
                    json_schema=None,
                    stream=False,
                )
                resp = await session.post(
                    f"{self.endpoint}/chat/completions",
                    json=fallback_request_data,
                    headers=self.request_headers(),
                )

            if not resp.ok:
                raise Exception(f"HTTP ERROR {resp.status}.\n{await resp.text()}")

            jsresp = await resp.json()
            content = self._extract_content(
                jsresp.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return ChatMessage(role="assistant", content=content)

    async def chat_stream(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncGenerator[str, None]:
        async with aiohttp.ClientSession() as session:
            request_data = self._chat_request(
                model=model, messages=messages, json_schema=None, stream=True
            )
            resp = await session.post(
                f"{self.endpoint}/chat/completions",
                json=request_data,
                headers=self.request_headers() | {"X-Accel-Buffering": "no"},
            )
            if not resp.ok:
                raise Exception(f"HTTP ERROR {resp.status}.\n{await resp.text()}")

            buffer = ""
            while (chunk := await resp.content.readany()) is not None:
                if len(chunk) == 0:
                    break

                buffer += chunk.decode("utf-8").replace("\r\n", "\n")
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    for line in event.splitlines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [{}])
                        if len(choices) == 0:
                            choices = [{}]
                        delta_content = self._extract_content(
                            choices[0].get("delta", {}).get("content")
                        )
                        if delta_content:
                            yield delta_content


class PtInference(LlmInference):
    endpoint: str
    token: str
    temperature: float = 0.1

    def request_headers(self) -> dict:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.token}",
        }

    def __init__(self, endpoint: str, token: str) -> None:
        self.endpoint = endpoint
        self.token = token

    async def chat_complete(
        self, model: str, messages: list[ChatMessage], json_schema: dict | None
    ) -> ChatMessage:
        async with aiohttp.ClientSession() as session:
            request_data = {
                "prompt": [m.model_dump() for m in messages],
                "num_ctx": 16384,
                "maxtok": 2048,
                "model": model,
                "temperature": self.temperature,
            }
            if json_schema is not None:
                request_data["struct_output"] = json_schema
            resp = await session.post(
                f"{self.endpoint}/completion",
                json=request_data,
                headers=self.request_headers(),
            )
            if not resp.ok:
                raise (Exception(f"HTTP ERROR {resp.status}.\n{await resp.text()}"))
            else:
                jsresp = await resp.json()
                return ChatMessage(role="assistant", content=jsresp["output"])

    async def chat_stream(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncGenerator[str, None]:
        async with aiohttp.ClientSession() as session:
            request_data = {
                "prompt": [m.model_dump() for m in messages],
                "num_ctx": 16384,
                "maxtok": 2048,
                "model": model,
                "temperature": self.temperature,
            }
            resp = await session.post(
                f"{self.endpoint}/completion_stream",
                json=request_data,
                # The X-Accel-Buffering header can be sent to disable buffering in a
                # reverse proxy, such as nginx, and have it stream data directly as it's
                # available. This can (and should) also be controlled on the nginx side by
                # setting `proxy_buffering off` for an endpoint like this.
                headers=self.request_headers() | {"X-Accel-Buffering": "no"},
            )
            if not resp.ok:
                raise (Exception(f"HTTP ERROR {resp.status}.\n{await resp.text()}"))
            else:
                while (chunk := await resp.content.readany()) is not None:
                    if len(chunk) == 0:
                        break
                    yield chunk.decode("utf-8")


class OllamaInference(LlmInference):
    client: ollama.AsyncClient

    def __init__(self, host: str | None = None) -> None:
        self.client = ollama.AsyncClient(host=host)

    async def chat_complete(
        self, model: str, messages: list[ChatMessage], json_schema: dict | None
    ) -> ChatMessage:
        request_data = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
        }
        if json_schema is not None:
            request_data["format"] = json_schema

        result = await self.client.chat(**request_data)
        return ChatMessage.model_validate(
            {"role": result.message.role, "content": result.message.content}
        )

    async def chat_stream(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncGenerator[str, None]:
        result = await self.client.chat(
            model=model, messages=[m.model_dump() for m in messages], stream=True
        )
        async for part in result:
            yield part["message"]["content"]


class VllmInference(OpenAiCompatibleInference):
    def __init__(self, endpoint: str, token: str | None = None) -> None:
        super().__init__(endpoint=endpoint, api_key=token)


class OpenAiInference(OpenAiCompatibleInference):
    def __init__(self, token: str, endpoint: str = "https://api.openai.com/v1") -> None:
        super().__init__(endpoint=endpoint, api_key=token)
