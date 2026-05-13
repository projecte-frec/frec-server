from fastmcp import FastMCP
import requests
from bs4 import BeautifulSoup

mcp = FastMCP("Viccionari")

@mcp.tool()
def get_word_definition(word: str) -> str:
    """You can use this tool to get the list of definitions for a word.
    - @param word: The word to search for
    """
    headers = {
        "accept": "application/json",
        "charset": "utf-8",
        "profile": '"https://www.mediawiki.org/wiki/Specs/definition/0.8.0"',
        "User-Agent": "Process Talks development platform (hello@processtalks.com)",
    }
    response = requests.get(
        f"https://en.wiktionary.org/api/rest_v1/page/definition/{word}", headers=headers
    )
    response.raise_for_status()
    resp_json = response.json()

    if "ca" in resp_json:
        accepcions = [
            BeautifulSoup(definition["definition"], "html.parser").get_text()
            for definition in resp_json["ca"][0]["definitions"]
            if definition["definition"]
        ]
        out_text = "Al Viccionari hi ha les següents accepcions:\n"

        responses_angles : list[dict] = []
        for i, accepcio in enumerate(accepcions):
            response_angles = requests.get(
                f"https://en.wiktionary.org/api/rest_v1/page/definition/{accepcio}",
                headers=headers,
            )
            if response_angles.ok:
                responses_angles.append(response_angles.json())

        for acepcio_angles in responses_angles:
            if "en" in acepcio_angles:
                acepcions_angles = [
                    BeautifulSoup(definition["definition"], "html.parser").get_text()
                    for definition in acepcio_angles["en"][0]["definitions"]
                    if definition["definition"]
                ]
                out_text = f"Definicions de {word} en anglès:\n"
                for i, accepcio in enumerate(acepcions_angles):
                    out_text += f"{i+1}. {accepcio}\n"
                return out_text

            return f"{accepcio} Not found"

        out_text = f"Definicions de {word} en anglès:\n"
        # aquí no volem fer tot el bucle sino només retornar la current que es la que no té definició en anglès només accepcions que trenquen la url
        for i, accepcio in enumerate(accepcions):
            out_text += f"{i+1}. {accepcio}\n"
        return out_text
    return f"{word} Not found"


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        print(get_word_definition.fn("bola"))
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
