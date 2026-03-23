from enum import StrEnum
import json
from typing import AsyncGenerator
from uuid import uuid4
import aiohttp
import fastapi
from pydantic import BaseModel, Field
from . import iter_response_lines


class AgentClientResponse(BaseModel):
    full_response: str


async def get_agent_description(url: str, agent_name: str) -> str:
    if url.endswith("/"):
        url = url[:-1]

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{url}/apps/{agent_name}") as resp:
            if not resp.ok:
                raise Exception(
                    f"Agent server responded with status code {resp.status}: {await resp.text()}"
                )
            payload = await resp.json(content_type=None)

    description = payload.get("root_agent", {}).get("description")
    if not isinstance(description, str):
        raise Exception(
            f"Agent description not found in /apps/{agent_name} response from {url}"
        )
    return description


async def call_agent_client(
    url: str, agent_name: str, question: str
) -> AsyncGenerator[str | AgentClientResponse, None]:
    async with aiohttp.ClientSession() as session:
        if url.endswith("/"):
            url = url[:-1]

        user_id = "frec"
        session_id = str(uuid4())

        # The ADK server requires an active session before running messages.
        create_session_errors: list[str] = []
        session_created = False
        create_session_urls = [
            f"{url}/apps/{agent_name}/users/{user_id}/sessions/{session_id}",
            f"{url}/apps/{agent_name}/users/{user_id}/sessions",
        ]
        for create_session_url in create_session_urls:
            async with session.post(create_session_url, json={}) as create_resp:
                if create_resp.ok or create_resp.status == 409:
                    session_created = True
                    if create_session_url.endswith("/sessions"):
                        try:
                            payload = await create_resp.json(content_type=None)
                            maybe_session_id = payload.get("id")
                            if (
                                isinstance(maybe_session_id, str)
                                and maybe_session_id != ""
                            ):
                                session_id = maybe_session_id
                        except:
                            pass
                    break
                body = await create_resp.text()
                create_session_errors.append(
                    f"{create_session_url}: {create_resp.status} {body}"
                )
                if create_resp.status not in (404, 405, 422):
                    raise Exception(
                        f"Agent server failed to create session at {create_session_url}. Status {create_resp.status}: {body}"
                    )

        if not session_created:
            raise Exception(
                "Agent server failed to create session at known endpoints. "
                + "\n".join(create_session_errors)
            )

        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        run_payloads = [
            {
                "app_name": agent_name,
                "user_id": user_id,
                "session_id": session_id,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": question}],
                },
            },
            {
                "appName": agent_name,
                "userId": user_id,
                "sessionId": session_id,
                "newMessage": {
                    "role": "user",
                    "parts": [{"text": question}],
                },
            },
        ]
        run_errors: list[str] = []
        for run_payload in run_payloads:
            async with session.post(
                f"{url}/run_sse", headers=headers, json=run_payload
            ) as response:
                if not response.ok:
                    body = await response.text()
                    run_errors.append(f"{response.status} {body}")
                    if response.status in (400, 404, 405, 422):
                        continue
                    raise Exception(
                        f"Agent server responded with status code {response.status}: {body}"
                    )

                full_response = ""
                yielded_final = False

                async for line in iter_response_lines(
                    response.content.iter_chunks()  # type:ignore
                ):
                    line = line.strip()
                    if line == "" or line.startswith(":") or line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "" or line == "[DONE]":
                        continue

                    try:
                        chunk_dict = json.loads(line)
                    except:
                        print(
                            f"\n[Error] Received invalid SSE line from agent server: {line}",
                            flush=True,
                        )
                        raise

                    if not isinstance(chunk_dict, dict):
                        continue

                    if isinstance(chunk_dict.get("full_response"), str):
                        final_response = AgentClientResponse.model_validate(chunk_dict)
                        yielded_final = True
                        yield final_response
                        continue

                    chunk_text = None
                    if isinstance(chunk_dict.get("chunk"), str):
                        chunk_text = chunk_dict["chunk"]
                    elif isinstance(chunk_dict.get("text"), str):
                        chunk_text = chunk_dict["text"]
                    else:
                        content = chunk_dict.get("content")
                        if isinstance(content, dict):
                            parts = content.get("parts")
                            if isinstance(parts, list):
                                chunk_text = "".join(
                                    p.get("text", "")
                                    for p in parts
                                    if isinstance(p, dict)
                                    and isinstance(p.get("text"), str)
                                )

                    if isinstance(chunk_text, str) and chunk_text != "":
                        if full_response != "" and chunk_text.startswith(full_response):
                            chunk_text = chunk_text[len(full_response) :]
                        if chunk_text != "":
                            full_response += chunk_text
                            yield chunk_text

                if not yielded_final:
                    yield AgentClientResponse(full_response=full_response)
                return

        raise Exception(
            "Agent server failed to run /run_sse with known payload formats. "
            + "\n".join(run_errors)
        )
