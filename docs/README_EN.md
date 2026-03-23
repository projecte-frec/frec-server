# Initial Setup
This version is a work in progress and may be outdated, for the latest version check the
[Official README](../README.md)
### Pas 0:
Clonar en local el repositori de git.
### Pas 1:
Establir les variables d'entorn. 
`cp env.example .env`
> [!IMPORTANT]
> Recordeu demanar el token a qui correspongui.
### Pas 2:
Compilar el servei
`./run-docker.py build` 
> [!NOTE]
> Aquest pas només caldrà executar-lo en el moment de la inicialització. Si calgués tornar-ho a fer, es notificarà quan correspongui.
### Pas 3:
Aixecar el servei
`./run-docker.py run`
### Pas 4:
Entrar a http://localhost:3000/ 
El primer usuari que inicïi sessió es considerarà l'Admin. Recomanació: posar una clau curta, ja que es farà servir molt.

# Guia d'ús de FREC:
## Configuració de les eines [tools]:
### Nova eina [Settings > New tool]
Les eines ja estan aixecades, però les connexions depenen de cada usuari i caldrà configurar-les.

|General Settings|Descripció|
|---|---|
|Name| El nom amb que l'usuari identificarà l'eina (p.ex.: Viquipèdia)|
|Tool kind| MCP ["Other" correspon a altres tipus d'eina que estan en desenvolupament]|
|Endpoint| http://[mcp server name]:[port de l'script corresponent][path (default: "/mcp")] `http://mcp_wikipedia:8010/mcp`|
|Custom Instructions| Add any custom instructions, or type "None" if none apply.|
### Gestió de permisos:
Cada eina es pot activar/Desactivar mitjançant l'interruptor *Enabled*.
Clicant sobre l'*Status* de l'eina es pot veure quines funcions té.
A la secció *Manage* es troba l'opció d'editar ✏️ i la d'eliminar 🗑️ l'eina.
✏️ Editar: Permet gestionar els permisos de cadascuna de les funcions de l'eina, entre *Off* (inactiva), *Ask* (requereix confirmació per part de l'usuari) i *Auto* (ús automàtic quan calgui).
🗑️ Eliminar: Elimina la connexió amb l'eina.
## Dades d´'ús:
(# TODO: info de la base de dades)

# Instruccions de desenvolupament:
## Pas 0: 
Crear un entorn virtual per permetre a la vostra IDE accés a l'entorn que heu aixecat dins el contenidor de docker.
`python -m venv venv`
[Si la IDE us pregunta si voleu establir la venv com a virtual environment, accepteu]
Activar l'entorn
`source ./venv/bin/activate`
instal·lar els requisits
`pip install -r requirements.txt`
## Afegir servidors mcp
Each mcp server has its script and its docker-compose service declaration. The mcp's port is required for adding it to the FREC web dashboard/application endpoint.
## Configure inference provider
Set `LLM_PROVIDER` in `.env` to one of: `pt`, `ollama`, `vllm`, `openai`.

Main variables by provider:
- `pt`: `PT_INFERENCE_HOST`, `PT_INFERENCE_TOKEN`, `PT_INFERENCE_MODEL`
- `ollama`: `OLLAMA_INFERENCE_HOST`, `OLLAMA_INFERENCE_MODEL` (fallback to `PT_INFERENCE_MODEL`)
- `vllm`: `VLLM_INFERENCE_HOST`, `VLLM_INFERENCE_TOKEN` (optional), `VLLM_INFERENCE_MODEL` (fallback to `PT_INFERENCE_MODEL`)
- `openai`: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` (optional, default `https://api.openai.com/v1`)
