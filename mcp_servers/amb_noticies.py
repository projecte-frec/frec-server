import requests

from fastmcp import FastMCP

BASE_URL = "http://opendata.amb.cat"
HEADERS = {"accept": "application/json"}

# instantiate an MCP server client
mcp = FastMCP("Notícies AMB")


@mcp.tool()
def amb_news_search(term: str | None = None, year: int | None = None) -> list[dict]:
    """
    News search against AMB Opendata "noticies" collection, up to 5 items at a time.

    Args:
        term: optional free text search - OPTIONAL argument. If not provided, don't use this argument at all!
        year: optional year filter (e.g. 2026) - OPTIONAL argument. Don't assume the year if asked for latest news, just don't use the argument if not given.
    Returns:
        A list of dictionaries containing the title and URL of each news item.
    """

    params = {
        "rows": 5,
        "sort": "data_noticia,desc",
        "getFields": "destacat_titol,detail_url,data_noticia",
    }

    # cerca per terme
    if term:
        params["q"] = term

    # filtrar dins de l'any sol·licitat
    if year:
        params["data_noticia"] = [
        f">01/01/{year}",
        f"<01/01/{year+1}"
    ]

    response = requests.get(
        f"{BASE_URL}/noticies/search",
        headers=HEADERS,
        params=params,
        timeout=10
    )
    response.raise_for_status()
    data = response.json()

    results = [
        {
            "title": item.get("destacat_titol"),
            "url": item.get("detail_url"),
        }
        for item in data.get("items", [])
    ]

    # possibles errors
    if term and year and not results:
        raise ValueError(f"No news found for term '{term}' and year '{year}'.")
    if term and not results:
        raise ValueError(f"No related news found for term '{term}'.")
    if year and not results:
        raise ValueError(f"No news found for year '{year}'.")

    return results

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='http', host="0.0.0.0", port=8000)