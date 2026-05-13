import string
import random
import urllib.parse
from fastmcp import FastMCP

mcp = FastMCP("Jitsi")

@mcp.tool()
def create_meeting(name: str | None = None) -> list[dict]:
    """
       Create a Jitsi meeting. Notice there's no additional information about the meeting, only it's name and resulting URL.
    Args:
        name: optional name for the meeting - OPTIONAL argument. If not provided, a random meeting name will be generated. Never add this argument if it's not in the user's request.
    Returns:
        A list of dictionaries containing the URL of the created meeting.
    """
    
    if name:
        if name=="null":
            alphabet = string.ascii_letters + string.digits
            code = ''.join(random.choice(alphabet.lower()) for _ in range(9))
            url = "https://meet.jit.si/" + code
        else:
            url = "https://meet.jit.si/" + name
    else:
        alphabet = string.ascii_letters + string.digits
        code = ''.join(random.choice(alphabet.lower()) for _ in range(9))
        url = "https://meet.jit.si/" + code

    return [{"url": url}]

@mcp.tool()
def obtain_meeting_qr(url: str) -> list[dict]:
    """
       Create a QR code for a Jitsi meeting URL.
    Args:
        url: The URL of the Jitsi meeting.
    Returns:
        A list of dictionaries containing the path to the generated QR code file.
    """

    encoded = urllib.parse.quote(url, safe="")

    return [{
        "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?data={encoded}&size=300x300"
    }]

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)