from fastmcp import FastMCP
import asyncio
from googletrans import Translator

mcp = FastMCP("Google Translate")


@mcp.tool()
async def translate(text: str, dst: str, src: str | None) -> str:
    """Translates the given text into destination language. Source language can be given,
    if not, it will be autodetected. Languages must be specified as language code (e.g.
    'en', 'es', 'ca')"""
    async with Translator() as translator:
        kwargs = {}
        if src is not None:
            kwargs["src"] = src
        result = await translator.translate(text, dest=dst, **kwargs)
        return result.text


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8012, path="/mcp")
