import json
from collections import defaultdict

from fastmcp import FastMCP
from pathlib import Path
from typing import List, Optional, Tuple

DIR_DATA = Path('./mcp_servers/diec/data/')
FILE_IDXS =  DIR_DATA / 'DIEC2_indices.json'
FILE_DEFS = DIR_DATA / 'DIEC2_content.json'

#=====================================
# CLASSES
#=====================================

class Entry:
    def __init__(self, form: str, entry: dict) -> None:
        self.search_form = form
        self.lex_form = self._get_lexical_form(entry)
        self.senses = entry['sense']

    def _get_lexical_form(self, entry: dict) -> str:
        lex_form = ''
        forms_list = entry['entrada']['form']
        for form in forms_list:
            form_orth = form['orth'][0]
            if isinstance(form_orth, dict):
                if '#text' in form_orth:
                    lf = form_orth['#text']
                elif 'rd' in form_orth:
                    lf = form_orth['rd'][0]['cs']
                else:
                    print(f"ERROR: No lexical entry form found for: {self.search_form} (1)")
            elif isinstance(form_orth, str):
                lf = form_orth
            else:
                exit(f"ERROR: No lexical entry form found for: {self.search_form} (2)")
            lex_form = ' '.join([lex_form, lf]).strip()
        return lex_form

    def _get_gramcat_from_block(self, gram_block) -> set:
        cgs = set()
        if isinstance(gram_block, dict):
            if 'pos' in gram_block:
                gram_subblock = gram_block['pos']
                sb_cgs = self._get_gramcat_from_subblock(gram_subblock)
                cgs.update(sb_cgs)
            else: print(f">>> WARNING: No gramatical POS for {self.search_form} (5.a)")
        elif isinstance(gram_block, list):
            for i in gram_block:
                if 'pos' in i:
                    gram_subblock = i['pos']
                    sb_cgs = self._get_gramcat_from_subblock(gram_subblock)
                    cgs.update(sb_cgs)
                else: print(f">>> WARNING: No gramatical POS for {self.search_form} (5.b)")
        else: print(f">>> WARNING: No gramatical POS for {self.search_form} (4)")
        return cgs

    def _get_gramcat_from_subblock(self, gram_subblock) -> set:
        cgs = set()
        if isinstance(gram_subblock, str):
            cgs.add(gram_subblock)
        elif isinstance(gram_subblock, dict):
            cgs.add(gram_subblock['#text'])
        else:
            print(f">>> WARNING: No gramatical POS for {self.search_form} (2) ")
        return cgs

    def get_grammatical_categories(self) -> set:
        cgs = set()
        for sense in self.senses:
            if 'gramgrp' in sense:
                gram_block = sense['gramgrp']
                gb_cgs = self._get_gramcat_from_block(gram_block)
                cgs.update(gb_cgs)
            elif 'eg' in sense and 'gramgrp' in sense['eg']:
                gram_block = sense['eg']['gramgrp']
                eg_cgs = self._get_gramcat_from_block(gram_block)
                cgs.update(eg_cgs)
            else:
                pass
        return cgs



class Diec:
    def __init__(self, f_idxs: Path, f_defs: Path) -> None:
        self.idxs = json.loads(f_idxs.read_text(encoding='utf-8'))
        self.defs = json.loads(f_defs.read_text(encoding='utf-8'))

    def _get_indices(self, form: str) -> Optional[List]:
        if form in self.idxs:
            return self.idxs[form]
        else: return None

    def _get_definitions(self, idx: str) -> Optional[List]:
        if idx in self.defs:
            return self.defs[idx]
        else: return None

    def get_entries(self, form: str) -> List[dict]:
        entries = []
        idxs = self._get_indices(form)
        if idxs:
            for i in idxs:
                entry = self._get_definitions(i)
                entries.append(entry)
        return entries

    def get_grammatical_categories(self, form: str) -> dict:
        entries_cgs = defaultdict(set)
        entries = self.get_entries(form)
        # A form can belong to multiple entries (homonymy)
        for entry in entries:
            e = Entry(form, entry)
            cgs = e.get_grammatical_categories()
            entries_cgs[e.lex_form].update(cgs)
        sorted_cgs = {k: sorted(v) for k, v in entries_cgs.items()}
        return sorted_cgs


#=====================================
# MCP SERVER
#=====================================

# Instantiate MCP server
# ------------------------
mcp = FastMCP("DIEC")

# Instantiate DIEC
# ------------------------
diec = Diec(FILE_IDXS, FILE_DEFS)

# MCP tools
# ------------------------
@mcp.tool()
def get_word_definitions(word: str) -> List[dict]:
    """Use this tool to get the list of definitions for a word in Catalan.
    - @param word: The word to search for. It can be a lemma, an inflected form or a phrase (multiword expression).
    """
    return diec.get_entries(word)

@mcp.tool()
def get_word_grammatical_categories(word: str) -> dict:
    """Use this tool to get the list of grammatical categories for a word.
    - @param word: The word to search for. It can be a lemma, an inflected form or a phrase (multiword expression).
    """
    return diec.get_grammatical_categories(word)



if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        if len(sys.argv) == 2:
            result = get_word_definitions.fn('hola')
        elif len(sys.argv) == 3:
            wrd = sys.argv[2]
            result = get_word_definitions.fn(wrd)
        else:
            exit(f"Testing Usage:\n\tpython {__file__} --test [word_to_search]")
        print(result)
    elif len(sys.argv) < 2:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
    else:
        exit(f"Usage:\n\tpython {__file__}")
