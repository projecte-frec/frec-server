
Aquest servidor proporciona accés al traductor de Apertium (http://apertium.org)

El traductor s'executa localment, i iblou els parells següents:

De català a altres llengües:
    Català → Castellà (spa)
    Català → Portuguès (por)
    Català → Occità (oci)
    Català → Italià (ita)
    Català → Aragonès (arg)
    Català → Francès (fra)
    Català → Sard (srd)
    Català → Occità aranès (oci_aran)

D'altres llengües al català:
    Castellà → Català (spa → cat)
    Castellà → Català valencià (spa → cat_valencia)
    Anglès → Català (eng → cat)
    Anglès → Català valencià (eng → cat_valencia)
    Portuguès → Català (por → cat)
    Italià → Català (ita → cat)
    Occità → Català (oci → cat)
    Aragonès → Català (arg → cat)
    Francès → Català (fra → cat)

## Inclusió de nous parells

Per incloure nous parells de llengües, cal fer:

- Editar el fitxer `docker/frec_server_apertium/Dockerfile` i afegir a la linia 14 els paquets debian dels parells desitjats. Trobareu una llista de parells suportats a `https://apertium.org/releases` 
- Executar `./run-docker.py build`
- Engegar el sistema normalment amb `./run-docker.py up`
