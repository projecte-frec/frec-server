import xmltodict
import json

from pathlib import Path
from typing import Dict, List
from collections import defaultdict

DIR_DATA = 'data'

stopwords = ['a', 'al', 'als', 'de', 'del', 'dels', 'el', 'els', 'en', 'la', 'les', 'per', 'pel', 'pels']

BODY = 'body'
ENTRADA = 'entrada'
ENTRY = 'entry'
FORM = 'form'
ID = 'selid'
ORTH = 'orth'
SENSE = 'sense'
TEXT = 'text'
TEXT2 = '#text'

#=================================
# CLASSES
#=================================

class Entry:
    def __init__(self, entry: Dict) -> None:
        self.id = entry[ID]
        self.forms = entry[FORM]
        self.lemma = self.forms[0][ORTH][0][ENTRADA][TEXT]  #normalized lemma (i.e., no accents & umlaut)
        self.variants = self.get_variants()
        self.content = {ENTRADA: entry[ENTRADA],
                        SENSE: entry[SENSE]}

    def get_variants(self) -> List:
        variants = []
        if len(self.forms) == 2:
            variants = [var[TEXT2] for var in self.forms[1][ORTH]]
        if len(self.forms) > 2:
            print(f"WARNING: Lemma {self.lemma} has more form blocks than expected: {len(self.forms)}")
        return variants


#=================================
# MAIN FUNCTIONS
#=================================

def build_indices(infile: Path) -> None:
    """ Given DIEC in JSON format, split content into 2 files for queries:
      - diec_indices.json, with entry forms as keys pointing to entry IDs.
      - diec_content.json, with entry IDs as keys pointing to entry content
        (lemma, grammatical information, definitions, etc.)"""
    ddic_idxs = defaultdict(set)    # Format: { form1: [id1, id2, ...], ...}, where form can be both the lemma or a variant
    dic_content = {}        # Format: { id1: {lex_entry_content},...}, where lex_entry_content corresponds to 'entrada' + 'sense' attributes from source
    with infile.open(encoding='utf-8') as f:
        data = json.load(f)
        entries = data[BODY][ENTRY]
        for e in entries:
            lex = Entry(e)
            # Store IDs for lemma
            ddic_idxs[lex.lemma].add(lex.id)
            # Store IDs for variants
            for v in lex.variants:
                ddic_idxs[v].add(lex.id)
            # Store IDs for forms in phrases (Cat. 'locucions') that have independent entries
            split_lemma = lex.lemma.split(' ')
            if len(split_lemma) > 1:
                non_stopword_forms = [i for i in split_lemma if i not in stopwords]
                for f in non_stopword_forms:
                    ddic_idxs[f].add(lex.id)
            # Store lexical entry content by ID
            dic_content[lex.id] = lex.content
    # Convert defaultdic to dic format
    dic_idxs = {k: list(v) for k, v in ddic_idxs.items()}

    # Print results
    outdir = Path(DIR_DATA)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile_idx = outdir / f"{infile.stem}_indices.json"
    outfile_content = outdir / f"{infile.stem}_content.json"
    with outfile_idx.open("w", encoding='utf-8') as f_idxs:
        json.dump(dic_idxs, f_idxs, indent=2, ensure_ascii=False)
    with outfile_content.open("w", encoding='utf-8') as f_content:
        json.dump(dic_content, f_content, indent=2, ensure_ascii=False)


def xml_2_json(infile: Path, outfile: Path) -> None:
    """ Convert input XML file to JSON format and print it out."""
    data_xml = infile.read_text(encoding='utf-8')
    data_dic = xmltodict.parse(data_xml, force_list=['entry', 'form', 'orth', 'sense', 'rd'])
    data_json = json.dumps(data_dic, indent=2)
    outfile.write_text(data_json, encoding='utf-8')


def main(infile: Path, outfile: Path) -> None:
    print(f"Converting XML to JSON format...")
    xml_2_json(infile, outfile)
    print(f"Extracting indices and content files...")
    build_indices(outfile)
    print("Done.")



if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        xml_file = Path(sys.argv[1])
        json_file = Path(sys.argv[2])
        main(xml_file, json_file)
    else:
        exit(f"\nUsage:\n\tpython {__file__} path/to/in_file.xml path/to/out_file.json")


