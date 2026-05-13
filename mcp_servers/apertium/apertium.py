import sys, os, signal
import requests
import json, re
import subprocess, threading
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptResult

# ========================================================
#  Auxliary
# ========================================================

# ==============================================
class Apertium:
    # ----------------------------------------------------
    # load the LanguageTools server for text correction
    def __init__(self, ):
        print("LAUNCHING APERTIUM APY",
              file=sys.stderr, flush=True)
        cmd = f"apertium-apy /usr/share/apertium"
        self.server = subprocess.Popen(cmd, shell=True)
        self.url = "http://localhost:2737/"
        self.mutex = threading.Lock()

    # ----------------------------------------------------
    # stop the LanguageTools server
    def __del__(self):
        os.kill(self.server.pid, signal.SIGTERM)

    # ----------------------------------------------------
    # send request to server
    def call_server(self, endpoint, params={}, files=None):
        print("CALLING ENDPOINT", f"{self.url}/{endpoint}", f"params={params}",
              file=sys.stderr, flush=True)

        params = [f"{k}={v}" for k,v in params.items()]
        
        request_headers = {"Content-Type": "application/json; charset=utf-8"}
        self.mutex.acquire()
        response = requests.post(f"{self.url}/{endpoint}?{'&'.join(params)}",
                                 headers=request_headers,
                                 files=files
                                )
        self.mutex.release()
        response.raise_for_status()
        return response.json()



# ========================================================
# instantiate an MCP server client

mcp = FastMCP("Apertium")

apertium = Apertium()


@mcp.tool()
# ----------------------------------------------------
def list_language_pairs() -> dict:
    """
    Returns available translation pairs 
    Args: - 
    Returns:
        A json structure containing the list of available translation pairs
    """

    try:
        response = apertium.call_server("listPairs")
        return response
    except Exception as e:
        return {"status": "error", "reason": repr(e)}

@mcp.tool()
# ----------------------------------------------------
def translate(text:str, source:str, target:str) -> dict:
    """
    Returns the translation of given text in source language to target language 
    Args:
        text : Text to translate
        source : Source language code (cat, ca, esp, en, etc...).
        target : Target language code (cat, ca, esp, en, etc...).
        The pair source-target must be one of the existing pairs.
    Returns:
        A json structure containing the requested translatrion
    """

    try:
        params = {"langpair": f"{source}|{target}",
                  "q" : text
                  }
        response = apertium.call_server("translate", params)
        return response
    except Exception as e:
        return {"status": "error", "reason": repr(e)}

'''
# TO BE FINISHED WHEN FREC SUPPORTS PASSING FILES
@mcp.tool()
# ----------------------------------------------------
def translateDoc(doc: bytes, source:str, target:str) -> dict:
    """
    Returns the translation of given document in source language to target language 
    Args:
        doc : bytes of the file (.doc, .odt, .txt, .html, etc...  to be translated)
        source : Source language code (cat, ca, esp, en, etc...).
        target : Target language code (cat, ca, esp, en, etc...).
        The pair source-target must be one of the existing pairs.
    Returns:
        A json structure containing the requested translatrion
    """

    try:
        params = {"langpair": f"{source}|{target}" }
        files = {"file": doc}
        response = apertium.call_server("translateDoc", params, files)
        return response
    except Exception as e:
        return {"status": "error", "reason": repr(e)}
'''

@mcp.tool()
# ----------------------------------------------------
def identifyLang(text:str) -> dict:
    """
    Returns the probabilities of given text to belong to different possible languages
    Args:
        text : Text for which language must be identified
    Returns:
        A json structure containing the probabilities of the text belonging to different languages.
    """

    try:
        params = {"q" : text}
        response = apertium.call_server("translate", params)
        return response
    except Exception as e:
        return {"status": "error", "reason": repr(e)}



# ------------------------------------
if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="http", host="0.0.0.0", port=8000)
