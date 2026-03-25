from typing import AsyncGenerator


async def iter_response_lines(
    gen: AsyncGenerator[tuple[bytes, bool], None],
) -> AsyncGenerator[str]:
    buffer = ""
    async for chunk_bytes, _b in gen:
        if len(chunk_bytes) > 0:
            buffer += str(chunk_bytes, "utf-8")
        while (i := buffer.find("\n")) != -1:
            yield buffer[: i + 1]
            buffer = buffer[i + 1 :]
    if len(buffer) > 0:
        print(
            "[Warning]: Leftover line returned by a line-by-line readable streaming API"
        )
        yield buffer
