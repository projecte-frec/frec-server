<p align="center">
    <img src="img/frec-banner.png">
</p>

> La tecnologia que connecta en català

![AGPL-v3](https://img.shields.io/badge/llicència-AGPL-v3.svg)
![Català](https://img.shields.io/badge/idioma-català-green.svg)

*Find the English version [here](docs/README_EN.md)*

FREC és una finestra única d'accés a la IA local i autogestionada per a empreses i
organitzacions. Ofereix una interfície conversacional on diversos usuaris podran
interactuar amb agents connectats a tot un ecosistema d'eines digitals: des de serveis
públics fins a les bases de dades de la teva organització.


![Captura de pantalla de FREC](img/captura_pantalla.png)

**Característiques**
- **Intel·ligència artificial, en Català**: FREC s'ha dissenyat posant especial èmfasi en
  l'ús del català. Malgrat les limitacions dels LLMs en la nostra llengua, el sistema
  incorpora els últims models amb millor suport pel català i ho complementa amb eines
  robustes de l'ecosistema digital en català: Correctors, traductors i diccionaris.
- **Privadesa per defecte, per garantir la sobirania digital**: FREC no comparteix cap
  dada amb tercers i es connecta amb motors d'inferència com [Ollama](https://ollama.com)
  i [Vllm](https://github.com/vllm-project/vllm). Això permet una gestió total de les
  dades sense haver de confiar-ne el bon tractament a empreses externes.
- **Connexió amb el protocol MCP**: FREC aplica el [protocol
  MCP](https://modelcontextprotocol.io/docs/getting-started/intro). Aquest protocol permet
  a agents basats en tecnologia LLM connectar-se a eines digitals. L'ús d'eines mitjançant
  protocols com MCP és fonamental per a suplir les carències d'aquests models: fent que el
  model es dediqui al processament de llenguatge i minimitzant la tasca cognitiva, reduim
  significativament el risc d'al·lucinacions.
- **Programari lliure, adaptable a cada organització**: FREC es distribueix com a
  programari lliure, juntament amb un conjunt d'eines d'interès general. A més, s'inclou
  documentació perquè qualsevol organització pugui adaptar-lo a les seves necessitats,
  proveïnt al model de noves eines.

# Configuració inicial

### Requisits previs:
- Python 3.13.5
- Docker

### Pas 0 - Clonar aquest repositori
```
git clone https://github.com/projecte-frec/frec-server.git
```

### Pas 1 - Configurar les variables d'entorn. 
Copieu el fitxer env.example a un nou fitxer `.env` i editeu-ne el contingut. Caldrà
seleccionar un proveïdor LLM i configurar-lo.
```
cp env.example .env
```
Un exemple de fitxer .env configurat per a Ollama seria el següent:
```
LLM_PROVIDER="ollama"
OLLAMA_INFERENCE_HOST="http://localhost:11434"
OLLAMA_INFERENCE_MODEL="ministral-3:14b"
```
Per a més informació, vegeu la secció "Configurar proveïdor d'inferència" més avall.

> [!IMPORTANT]
> Alguns servidors MCP (per exemple, TMB) requereixen claus d'API addicionals que s'hauran d'introduir en aquest fitxer.

### Pas 2 - Compilar el servei
Utilitzarem l'script `run-docker.py` per facilitar algunes de les tasques. Aquest script és un petit wrapper sobre [`docker compose`](https://docs.docker.com/compose/).
```
./run-docker.py build frec_server
./run-docker.py build
```

> [!NOTE]
> Aquest pas només caldrà executar-lo durant la primera configuració

### Pas 3 - Aixecar el servei
```
./run-docker.py up
```
### Pas 4 - Accés
Un cop iniciat el sistema, la interfície de FREC es trobarà a http://localhost:3000/ 

> [!CAUTION]
> Si no es configuren credencials d'admin per entorn, el primer usuari que iniciï sessió es considerarà l'Admin (mode desenvolupament).

# Guia d'ús de FREC
## Eines
### Configuració
#### Nova eina
Les eines de FREC es configuren al fitxer de configuració frec-config.yml, o creant un arxiu específic corresponent de la vostra versió per evitar incompatibilitats amb futures versions. Recomanem seguir l'estàndard de `[nom de la vostra integració]-config.yml`

#### Gestió de permisos

Des de la interfície de FREC, a l'apartat de Configuració, es poden modificar les diferents
eines i permisos. Cada eina es pot Activar/Desactivar mitjançant l'interruptor `Activada`.

Clicant sobre l'`Estat` de l'eina es pot veure quines funcions té.

A la secció `Gestiona` es troba l'opció d'*editar* l'eina.

Permet gestionar els permisos de cadascuna de les funcions de l'eina, entre *Off* (inactiva), *Ask* (requereix confirmació per part de l'usuari) i *Auto* (ús automàtic quan calgui).

## Xat
Introduïu el missatge al camp de text. El xat rebrà un nom automàticament a partir del contingut de la conversa, però ho podeu editar clicant el ✏️ al costat del nom.

### Ús d'eines
Quan es cridi una eina, sortirà un missatge informatiu. Si l'eina està configurada com a manual *(Ask)*, caldrà que l'usuari confirmi si la vol activar. En cas que l'eina estigui configurada com a automàtica, es llançarà directament.  
Prémer sobre el missatge informatiu mostrarà el procés que segueix l'eina i la resposta que rep de l'mcp, a partir de la qual es redactarà la resposta a l'usuari.

### Eliminar un xat
*Funcionalitat en desenvolupament.*

# Instruccions de desenvolupament
## Pas 0 - Configuració inicial
### Crear un entorn virtual
Permetrà les funcions de validació de tipus del vostre IDE de desenvolupament:
> [!NOTE]
> Aquest pas només caldrà executar-lo al moment de la inicialització.

```
python -m venv venv
```


> [!TIP]
> Si la IDE us pregunta si voleu establir la venv com a virtual environment, accepteu.
### Activar l'entorn
```bash
source ./venv/bin/activate
```
### Instal·lar els requisits
```bash
pip install -r requirements.txt
```
## Afegir servidors MCP
Cada servidor es defineix a tres punts diferents:

1. Té l'script corresponent a la carpeta `mcp_servers/`. Per exemple, `mcp_servers/viquipedia_mcp.py`.

    Aquí és on es determinarà el port que després cal afegir a l'endpoint del fitxer de configuració. El servidor al panell de control de FREC.

    Per desenvolupar el vostre servidor, trobareu la plantilla `template_mcp` dins la carpeta `mcp_servers/`.

2. Es configura dins del fitxer `frec-config.yaml`. Per exemple:
   ```yaml
    viquipedia:
    name: "Viquipedia"
    kind: mcp
    endpoint: http://mcp_viquipedia:8011/mcp```
   
3. Es declara el seu servei a `docker/docker-compose.yml`

Cal tenir en compte si el nou MCP serà autohostatjat o extern. Per als serveis
autohostatjats s'utilitzarà un `endpoint` que apunti dins la xarxa docker, com
`http://mcp_viquipedia:8011/mcp`. Per MCP externs, s'haurà d'introduir una URL vàlida que
apunti al vostre servidor.

> [!NOTE]
> Per motius de seguretat, FREC no permet utilitzar el protocol MCP via el transport *stdio*, només via *streamable-http*. Existeixen eines com [mcp-proxy](https://github.com/sparfenyuk/mcp-proxy) que permeten exposar servidors mcp *stdio* a través d'una connexió HTTP.

## Testejar servidors MCP
### En local
Per a testejar les eines ràpidament, hem habilitat la comanda:

```bash
python mcp_servers/template_mcp.py --test
```
on només caldrà canviar el nom de l'script del servidor per testejar l'eina que estiguem desenvolupant i que haurem posat allà on a la plantilla hi diu `print(tool_function_name.fn("concept"))`.

<details><summary> Veure alternativa: </summary>

En cas que no hagueu establert una funció de testatge al vostre MCP, una altra opció és comentar la crida al servidor, i imprimir el `return` de l'eina que esteu creant, p.ex.:

```python
if __name__ == "__main__":
    # mcp.run(transport="streamable-http", host="0.0.0.0", port=8011, path="/mcp")
    print(wikipedia.summary(wikipedia.random(pages=1))) # executa aquest codi
```
En aquest cas, la comanda:  

`python mcp_servers/viquipedia_mcp.py`  

retorna el contingut: 

> Francis Sowerby Macaulay   (Witney, 11 de febrer de 1862 - Cambridge, 9 de febrer de 1937) va ser un matemàtic anglès.

</details>

### FREC
Simplement inicieu una conversa normal després d'afegir la nova eina a l'aplicatiu, o d'actualitzar-la després de realitzar-hi canvis amb la comanda:

```bash
./run-docker.py up -d --force-recreate mcp_template
```

on `mcp_template` és el nom del contenidor al docker-compose
## Configurar proveïdor d'inferència
Definiu `LLM_PROVIDER` al fitxer `.env` amb un dels valors: `ollama`, `vllm`, `openai`.

Variables principals per cada proveïdor:

| Backend | Variables | Notes                                                                   |
|--------|----------|-------------------------------------------------------------------------|
| ollama | `OLLAMA_INFERENCE_HOST`, `OLLAMA_INFERENCE_MODEL` | Si no es defineix model, fa servir per defecte `PT_INFERENCE_MODEL`     |
| vllm | `VLLM_INFERENCE_HOST`, `VLLM_INFERENCE_TOKEN`, `VLLM_INFERENCE_MODEL` | Token opcional; per defecte: `PT_INFERENCE_MODEL`                       |
| openai | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | `OPENAI_BASE_URL` és opcional; per defecte `https://api.openai.com/v1`) |



### Configuració de l'accés a serveis locals (Ollama, vLLM a localhost)

Si Ollama i vLLM estan instal·lats al _host_, la configuració de docker compose del projecte permet accedir a aquest usant `host.docker.internal` com a nom del servidor. 

En una instal·lació típica d'Ollama, això vol dir que la variable d'entorn seria:

```
OLLAMA_INFERENCE_HOST="http://host.docker.internal:11434"
```

> [!WARNING]
> **MOLT IMPORTANT:** Per poder funcionar correctament, Ollama ha d'escoltar com a mínim les IPs de la xarxa docker. En una instal·lació típica, per defecte escolta només la 127.0.0.1 (localhost). Consulta la documentació d'Ollama per com fer que escolti totes les IPs (i.e. 0.0.0.0:11434).

### Configuració de l'accés a Ollama via Docker

És més senzill incorporar Ollama localment si s'afegeix com un servei més a docker compose:

```docker
ollama:
    image: ollama/ollama:0.16.3

    # This will enable the container to access the GPU[1]. It requires the
    # nvidia-container-toolkit[2] to be installed:
    #
    # [1]: https://docs.docker.com/engine/containers/resource_constraints/#gpu
    # [2]: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```
En aquest cas 
```
OLLAMA_INFERENCE_HOST="http://ollama:11434"
```

## Dades d'ús
Les dades d'interaccions prèvies s'emmagatzemen dins l'arxiu `database.db`, on podeu consultar segons conversa, missatge o crides a eines concretes, entre d'altres.

# Desplegament de FREC a producció
## Aprovisionament de la màquina

Els requisits de _hardware_ són petits. Cal una IP pública i un domini pel DNS.

Cal instal·lar-hi `docker` i `python`.

Per instal·lar docker, hi ha l'script `docker/provisioning.sh`

## Firewall

Cal obrir els ports 80 (HTTP), 22 (SSH) i 443 (HTTPS).

## Configuració

- Determineu quina configuració de FREC cal usar (per defecte s'usa `frec-config.yml`)
- Poseu el nom de domini a la variable `NGINX_SERVER_NAME` dins el fitxer `docker/frec-deploy.env.example` (copieu el fitxer `docker/frec-deploy.env.example` a `docker/frec-deploy.env` i modifiqueu-lo).
- Definiu `FREC_ADMIN_USERNAME` i `FREC_ADMIN_PASSWORD` a `docker/frec-deploy.env` per inicialitzar l'usuari administrador (obligatori en producció si la base de dades no té usuaris).
- Feu el mateix amb `.env.example`, copieu-lo a `.env` i completeu-lo.

## Execució

```bash
    $ run-docker.py --prod --conf <nom del fitxer de configuració, per defecte frec-config.yml> up
```
# Documentació addicional
Per col·laborar amb èxit al projecte, teniu també a disposició els següents manuals: 
* [Documentació de l'API REST del sistema FREC](https://github.com/projecte-frec/frec-server/blob/main/docs/rest_api.md)
* [Manual d'integració i proposta d'eines a FREC](https://github.com/projecte-frec/frec-server/blob/main/docs/manual_collaboracio.md)

# Agraïments
L'inici d'aquest projecte ha rebut l'impuls de:

![EUNextGen](./img/UE+Gobierno+Pla.png)

Amb el suport de:

![GenCat](./img/dept-empresa-i-treball.png)


