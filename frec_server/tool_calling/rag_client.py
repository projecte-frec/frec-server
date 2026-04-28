from enum import StrEnum
import json
from typing import AsyncGenerator, Optional
import uuid
import aiohttp
import fastapi
from pydantic import BaseModel
from . import iter_response_lines


class RagServerStatus(StrEnum):
    Online = "Online"
    InvalidToken = "InvalidToken"
    Unavailable = "Unavailable"


async def get_status(url: str, token: str) -> tuple[RagServerStatus, str]:
    async with aiohttp.ClientSession() as session:
        if url.endswith("/"):
            url = url[:-1]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = await session.get(f"{url}/api/status", headers=headers)
            text = await resp.text()
            if resp.status == 401:
                return RagServerStatus.InvalidToken, text
            elif not resp.ok:
                return RagServerStatus.Unavailable, text
            else:
                return RagServerStatus.Online, text
        except Exception as e:
            return RagServerStatus.Unavailable, str(e)


class RagTextChunk(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    text: str
    heading: Optional[list[str]] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class RagClientResponse(BaseModel):
    full_response: str
    references: dict[str, RagTextChunk]


async def call_rag_client(
    url: str, token: str, question: str
) -> AsyncGenerator[str | RagClientResponse, None]:
    async with aiohttp.ClientSession() as session:
        if url.endswith("/"):
            url = url[:-1]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {"query": question}
        async with session.get(
            f"{url}/api/questionanswer", headers=headers, json=body
        ) as response:
            if response.ok:
                # NOTE: Due to a hardcoded buffer size in aiohttp, we cannot reliably
                # iterate the lines using `response.content` directly, so we have to
                # build our own line buffer.
                # (source: https://github.com/open-webui/open-webui/issues/17626#issuecomment-3337804643)

                async for line in iter_response_lines(
                    response.content.iter_chunks()  # type:ignore
                ):
                    if len(line) > 0:
                        try:
                            chunk_dict = json.loads(line)
                        except:
                            print(
                                f"\n[Error] Received invalid json line from rag client: {line}",
                                flush=True,
                            )
                            raise
                        if "full_response" in chunk_dict:
                            yield RagClientResponse.model_validate(chunk_dict)
                        else:
                            yield chunk_dict["chunk"]
            else:
                raise Exception(
                    f"RAG server responded with status code {response.status}: {await response.text()}"
                )


async def get_rag_document_file(
    session: aiohttp.ClientSession,
    url: str,
    token: str,
    chunk_id: uuid.UUID,
    request_headers: fastapi.datastructures.Headers,
) -> fastapi.responses.StreamingResponse:
    if url.endswith("/"):
        url = url[:-1]

    # The original request may include relevant headers such as range / if-range which
    # the browser uses to speed up loads, so we forward those.
    headers = {}
    for h in ("range", "if-range"):
        if h in request_headers:
            headers[h] = request_headers[h]
    headers["Authorization"] = f"Bearer {token}"

    upstream_response = await session.get(
        f"{url}/api/get_chunk_file/{chunk_id}", headers=headers
    )

    # We forward most response headers to the client except for those that may cause
    # trouble. NOTE: This code is llm-generated so take it with a grain of salt
    passthrough_headers = {
        k: v
        for k, v in upstream_response.headers.items()
        if k.lower()
        not in {"transfer-encoding", "connection", "keep-alive", "content-length"}
    }

    # The Content-Disposition header can be specified as "inline" and the browser will
    # open the PDF directly on a new tab
    passthrough_headers["Content-Disposition"] = passthrough_headers.get(
        "Content-Disposition", ""
    ).replace("attachment", "inline")

    return fastapi.responses.StreamingResponse(
        upstream_response.content.iter_chunked(8192),
        status_code=upstream_response.status,
        headers=passthrough_headers,
        media_type=upstream_response.headers.get("Content-Type"),
    )
