
# Servidor DIEC

Aquest servidor proporciona un servei d'accés al _Diccionari General de la Llengua Catalana_ (2a edició) de l'Institut d'Estudis Catalans (DIEC2).

## Obtenció de les dades
Les dades no són de lliure distribució, i per tant us cal obtenir-les posant-vos en contacte directament de l'IEC. 

## Preprocessament de les dades
Per a la versió actual del servidor, es va fer servir la versió de dades `DIEC2_20260226.xml`, en format XML. Les dades a consumir pel servidor es van preparar processant aquest fitxer amb el codi de python `aux/conversor.py`.

### Requeriments:

* Versió de python: `3.13.0`
* Llibreria `xmltodict==1.0.4`, que podeu instal·lar amb `pip install`

### Execució

```
cd mcp_servers/diec
python aux/conversor.py  path/to/input/DIEC_file.xml  path/to/output/DIEC_file.json
```

L'script convertirà les dades a un fitxer JSON, que guardarà a `path/to/output/DIEC_file.json`. 

A continuació, generarà dos fitxers més amb el contingut del DIEC2 indexat, que es guardaran a la carpeta `mcp_servers/diec/data`: 

* `mcp_servers/diec/data/DIEC_file_indices.json`
* `mcp_servers/diec/data/DIEC_file_content.json`

Aquests són els fitxers que el servidor MCP farà servir. Cal que quedin en aquesta mateixa ubicació `mcp_servers/diec/data`.




