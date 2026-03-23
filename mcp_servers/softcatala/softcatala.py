import sys, os, signal
import requests
import json, re
import subprocess, threading
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptResult

# ========================================================
#  Auxliary classes
# ========================================================

HERE = os.path.dirname(__file__)


# ==============================================
class Dictionary:

    # ----------------------------------------------------
    # Load dictionaries for dictionary_look_up function
    def __init__(self, dir=None):
        if not dir:
            dir = HERE
        # load morphological dictionary
        self.morfo = {}
        with open(os.path.join(dir, "morfo.txt")) as mf:
            line = mf.readline()
            while line != "":
                line = line.split()
                lemma, pos = line[0:2]
                if pos in "NVAR":
                    for i in range(2, len(line)):
                        word = line[i]
                        if word not in self.morfo:
                            self.morfo[word] = set()
                        self.morfo[word].add(lemma)
                line = mf.readline()

        # load synonyms dictionary
        self.synonyms = {"synsets": {}, "index": {}}
        with open(os.path.join(dir, "sinonims.txt")) as sin:
            synsetnum = 0
            line = sin.readline()
            while line != "":
                synsetnum += 1
                p = line.find("#")
                if p != -1:
                    line = line[:p]
                line = line.strip()
                line = line.replace("NOFEM", "").replace(" )", ")").replace("( ", "(")
                line = re.sub("FEM[^\\)]*\\)", ")", line)
                line = line.replace("()", "")
                line = line.replace("(f)", "").replace("(f ", "(")
                line = line.replace(" ,", ",")

                # print(line)
                p = line.find(":")

                # categoria gamatical i el que hi hagi abans dels ":"
                pos = line[:p].replace("-", "")
                obs = None
                q = pos.find(" ")
                if q != -1:
                    obs = pos[q + 1 :][1:-1]
                    pos = pos[:q]

                # resta de la linia, amb els sinonims
                line = line[p + 1 :].split(",")
                sinon = []
                anton = []
                for x in line:
                    x = x.strip()
                    m = re.match("([^\\(\\)]*) (\\([^\\)]*\\))", x)
                    if m:
                        if m.group(2) == "(antònim)":
                            anton.append(m.group(1))
                        else:
                            sinon.append({"word": m.group(1), "obs": m.group(2)[1:-1]})

                    else:
                        sinon.append({"word": x})

                # indexacio. 1: associar cada paraula del synset amb el codi del synset
                for s in sinon:
                    w = s["word"]
                    if w not in self.synonyms["index"]:
                        self.synonyms["index"][w] = []
                    self.synonyms["index"][w].append(synsetnum)
                # indexacio. 2: crear synset i indexar-lo per numero
                newsynset = {"pos": pos, "sinonims": sinon, "antonims": anton}
                if obs:
                    newsynset["obs"] = obs
                self.synonyms["synsets"][synsetnum] = newsynset

                line = sin.readline()

    # ----------------------------------------------------
    # convert the result of a dictionray look_up into something human-friendly
    def readable(self, response):
        output = []
        for r in response:
            lm = r["lemma"]
            s = r["synset"]
            entry = f"{lm} [{s['pos']}]"
            if "obs" in s:
                entry += f" ({s['obs']})"
            entry += ":"
            for i, x in enumerate(s["sinonims"]):
                entry += f" {x['word']}"
                if "obs" in x:
                    entry += f" ({x['obs']})"
                if i < len(s["sinonims"]) - 1:
                    entry += ","

            if s["antonims"]:
                entry += f". Antònims:"
                for i, x in enumerate(s["antonims"]):
                    entry += f" {x}"
                    if i < len(s["antonims"]) - 1:
                        entry += ","
            entry += "."

            output.append(entry)
        return output

    # ----------------------------------------------------
    # get lemmas for given word
    def get_lemmas(self, word):
        lemmas = self.morfo.get(word, set())
        # not found, use word as is
        if not lemmas:
            lemmas = {word}
        return lemmas

    # ----------------------------------------------------
    # get synset nums for given lemma
    def get_synsets(self, lemma):
        return self.synonyms["index"].get(lemma, [])

    # ----------------------------------------------------
    # get words inside given synset num
    def get_synset_words(self, synset):
        return self.synonyms["synsets"].get(synset, {})


# ==============================================
class Corrector:
    # ----------------------------------------------------
    # load the LanguageTools server for text correction
    def __init__(self, dir=None):
        if not dir:
            dir = os.path.join(HERE, "LanguageTool-6.8")
        cmd = f"cd {dir} && java -cp languagetool-server.jar org.languagetool.server.HTTPServer --config server.properties --port 8884 --allow-origin"
        self.server = subprocess.Popen(cmd, shell=True)
        self.url = "http://localhost:8884/v2"
        self.mutex = threading.Lock()

    # ----------------------------------------------------
    # stop the LanguageTools server
    def __del__(self):
        os.kill(self.server.pid, signal.SIGTERM)

    # ----------------------------------------------------
    # send request to server
    def call_server(self, endpoint, request_data=None):
        print(
            "CALLING ENDPOINT", self.url + "/" + endpoint, file=sys.stderr, flush=True
        )
        request_headers = {"Content-Type": "application/json; charset=utf-8"}
        self.mutex.acquire()
        response = requests.post(
            self.url + "/" + endpoint, headers=request_headers, data=request_data
        )
        self.mutex.release()
        response.raise_for_status()
        return response.json()


# ========================================================
# instantiate an MCP server client

mcp = FastMCP("Softcatala")

# auxiliary structures
dicc = Dictionary()
corr = Corrector()


@mcp.tool()
# ----------------------------------------------------
def dictionary_look_up(word: str) -> list:
    """
    Look up given word in a synonym/antohnym dictionary.
    Args:
        word: word to look up.
    Returns:
        A json structure containing synonym/anthonym information.
    """

    response = []
    for lem in dicc.get_lemmas(word):  # for each lemma for this word
        for syns in dicc.get_synsets(lem):  # for each sysnet this lemma belongs to
            # add words in the synset
            response.append({"lemma": lem, "synset": dicc.get_synset_words(syns)})

    # return in human-friendly json (omit if full-structure response is desired)
    response = dicc.readable(response)
    return response


@mcp.tool()
# ----------------------------------------------------
def corrector_languages() -> list:
    """
    Returns a list of dictionaries, each element describes one of the languages supported by the corrector
    Args:
        none
    Returns:
        A json structure containing the list of supported languages
    """
    try:
        response = corr.call_server("languages")
        return response
    except Exception as e:
        return [{"status": "error", "reason": repr(e)}]


@mcp.tool()
# ----------------------------------------------------
def corrector_check(language: str, text: str) -> dict:
    """
    Checks the grammar and spelling of the given text in the given language, and returns a json structure describing spotted mistakes.
    Args:
        - language: the code of the language in which the text is written (e.g. ca-ES, pt-PT, es-ES, etc).
        - text: the text to be checked.
    Returns:
        A json structure containing a description of detected potential mistakes with corresponding correction suggestions.
    """
    try:
        response = corr.call_server("check", {"language": language, "text": text})
        return response
    except Exception as e:
        return {"status": "error", "reason": repr(e)}


# ------------------------------------
if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="http", host="0.0.0.0", port=8007)
