from fastmcp import FastMCP

mcp = FastMCP("NameOfTheTool")


@mcp.tool()
def tool_function_name(arg1: str) -> str:
    """Replace this line with a description of the tool. This will be seen by the prompt."""
    return "replace with your code"

@mcp.tool()
def tool_function_name_2():
    """
    Replace this line with a description of the tool.
    This will be seen by the prompt. You can use multiline.
    """
    return "replace with your code"

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        print(tool_function_name.fn("concept"))
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8010, path="/mcp")
