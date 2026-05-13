from fastmcp import FastMCP
import wikipedia

mcp = FastMCP("Wikipedia")
wikipedia.set_lang("ca")


@mcp.tool()
def get_resum(concept: str, language: str = "ca") -> str:
    """Checks the wikipedia page for an existing concept and returns its summary.
    The language parameter is the two-letter country code, according to the List of Wikipedias.
    Unless specified, assign the code of the language in which the query was made
    Use 'ca' for catalan, 'es' for spanish, 'en' for english...
    Default to catalan when in doubt.
    If there is no entry in the chosen language, try again in catalan, and then english.
    """
    wikipedia.set_lang(language)
    return wikipedia.summary(concept)


@mcp.tool()
def get_random(language: str = "ca") -> str:
    """Use this to get a random wikipedia page
    The language parameter is the two-letter country code, according to the List of Wikipedias.
    Unless specified, assign the code of the language in which the query was made
    Use 'ca' for catalan, 'es' for spanish, 'en' for english...
    Default to catalan when in doubt.
    If there is no entry in the chosen language, try again in catalan, and then english.
    """
    wikipedia.set_lang(language)
    concept = wikipedia.random(pages=1)
    summary = wikipedia.summary(concept)
    return f"Concepte: {concept}\nResum: {summary}"


@mcp.tool()
def get_images(concept: str):
    """Use this when you're prompted to show images.
    Keep yourself on topic."""
    return wikipedia.page(concept).images


@mcp.tool()
def get_references(concept: str):
    """Use this when you're prompted to show references for a certain topic.
    Keep yourself on topic."""
    return wikipedia.page(concept).references


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
