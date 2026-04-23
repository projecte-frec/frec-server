# Documentació de l'API REST del sistema FREC

En aquest document es recull la documentació de la API REST del sistema FREC, que permet
comunicar-se amb el sistema d'inferència i clients MCP de la mateixa manera que ho fa la
versió web.

El mecanisme principal de comunicació és la creació d'una conversa, en estil xat, entre
usuari i assistent, similar a APIs com la d'OpenAI. En aquest cas, però, el sistema FREC
és capaç d'executar algunes accions als seus servidors i retornarà una seqüència de
missatges després de cada interacció.

El fluxe de comunicació segueix la següent estructura, on el client és l'aplicació usuaria
de FREC i el servidor és el mateix FREC:

1. El client inicia una nova conversa, cridant a l'endpoint `/start-chat`.
2. El client envia un primer missatge a la conversa, utilitzant l'endpoint
     `/send-message`.
3. El servidor respon amb una llista dels missatges generats per l'assistent en resposta
     al missatge enviat. Aquesta llista, a més, contindrà la raó per la qual la generació
     s'ha aturat, que podria indicar que s'espera un nou missatge de l'usuari
     (`awaiting_next_message`) o que cal confirmar l'execució d'alguna eina
     (`pending_tool_confirm`).
4. El client decideix com mostrar aquests missatges a l'usuari, i en funció del motiu
     d'aturada, envia una nova acció en consequència, amb endpoints com `/send-message` o
     `/tool-consent`, esperant una nova resposta del servidor.

Aquest procés es repeteix indefinidament mentre el client segueixi enviant informació.

## Format de dades

L'API realitza tota la seva comunicació utilitzant JSON. Tant els paràmetres d'entrada com
les respostes de sortida es codificaràn com a documents JSON, excepte quan la documentació
d'un endpoint indiqui el contrari.

## Autenticació

L'autenticació d'aquesta API es fa mitjançant un `token`. La forma d'especificar aquest token és mitjançant un header HTTP amb el següent format:
```
Authentication: Bearer <el_meu_token>
```
Per exemple:
```
Authentication: Bearer ftk9166bb41-66d5-4201-bcbf-aafd3d3532f8
```
Per crear nous tokens, és necessari accedir al client web de FREC amb les nostres credencials, dirigir-nos a l'apartat d'opcions, i crear un nou token.

## Manca de mode *streaming*

La API actualment és síncrona i no disposa d'un mode streaming. Quan s'envia un missatge a l'assistent, la crida HTTP es bloquejarà fins que s'hagi generat tota la resposta, que s'enviarà de cop.

Tot i així, el sistema sí que s'ha dissenyat des de zero per a facilitar l'streaming de
les respostes. Així que si hi ha necessitat, aquesta funcionalitat es podria inforporar en
una futura versió.

## Errors

Quan es produeix una resposta satisfactòria, la API respondrà amb un estat HTTP 200 (OK).
En cas contrari, ho indicarà amb el codi HTTP més adient (401 - Unauthorized, 422 -
Unprocessable Content, ...). Sempre que es produeixi un error el cos de la resposta
contindrà un text explicatiu amb més informació. És important accedir a aquest text si es
vol entendre l'error ja que molts clients per defecte l'amaguen.

**NOTA**: El sistema segueix en desenvolupament. Existeixen casos d'error en els que el
sistema podria deixar una resposta pendent i respondria amb un error 504 (Gateway
timeout). Aquests errors no són part de l'especificació de la API i s'han de comunicar com
a bugs.

## Ús d'eines i sistema de permisos

Els agents de FREC tenen accés a eines, que es poden habilitar i deshabilitar des del
portal web. Actualment hi ha suport per als següents tipus d'eines:

- Eines MCP
- Eines Locals

Les eines disponibles es troben definides al fitxer de configuració `frec-config.md` del
teu deployment. A més, des del panell de configuració a l'apartat de "Settings" del portal
web de FREC, es poden configurar els permisos per cada eina en una de les tres opcions:

- Off: Aquesta eina no és visible per a l'agent i no la podrà executar
- Ask: L'agent demanarà consentiment cada vegada abans de fer servir una eina.
- Auto: L'agent executarà aquesta eina sempre que la vulgui fer servir sense demanar permís.

És important assegurar-se de definir uns permisos que garanteixin el bon ús del sistema i
minimitzin els riscos d'utilizar agents basats en LLM. Per qualsevol acció que pugui comportar
perill, és recomanable mantenir l'eina en mode "Ask" i validar cada crida amb l'endpoint 
`/api/tool-consent` després d'haver-la inspeccionat.

## Eines locals

Les eines locals (també anomenades eines externes) permeten donar capacitats d'interacció
a l'agent amb eines externes a l'ecosistema FREC. L'execució d'aquestes eines va a càrrec
del client, que és el responsable d'executar l'acció, i comunicar-ne el resultat
mitjançant l'endpoint `/api/external-tool-output`.

Per detectar que el sistema espera la resposta d'una eina local, ho comunicarà amb un
`stop_reason` de valor `awaiting_external_tool`.
    
## Endpoints

El sistema actualment disposa dels següents endpoints. La llista s'anirà ampliant conforme
evolucionin els requisits

### GET `/version`

Retorna la versió de la API.

**Paràmetres:** Cap

**Exemple de sortida:**
```
0.1.0
```

### POST `/start-chat`

Inicia una nova conversa. Cada conversa correspon a un únic fil amb l'assistent, amb un historial persistent.

**Paràmetres:** Cap

**Exemple de sortida:**
```json
{"conversation_id": "f360eee8-3910-42c3-aa70-f085e467c9dc"}
```

### POST `/send-message`

Envia un missatge a una conversa existent

**Paràmetres**:

- `conversation_id`: *string*  - L'identificador de conversa, retornat per `/start-chat` 
- `content`: *string* - El contingut del missatge que es vol enviar a l'assistent

**Notes de funcionament**:

El valor del camp `stop_reason` de la sortida indica quin és el següent pas que s'espera
per part del client.

Aquest endpoint només es pot cridar quan s'acaba d'iniciar una conversa o després que
l'assistent respongui amb un `stop_reason` de `awaiting_next_message`.

No està permès fer crides simultànies a aquest endpoint pel mateix `conversation_id`.

S'inclouen dos camps addicionals a la sortida:

- `tools_pending_consent`: En cas que l'assistent respongui amb un `stop_reason` de
  `pending_tool_confirm`, inclou informació de les eines a confirmar. Aquesta informació
  és duplicada de les eines dins el missatge corresponent.
- `tools_pending_external`: En el cas d'un `stop_reason` de `awaiting_external_tool`,
  inclou els identificadors de les eines per les quals el sistema espera una resposta a
  una eina externa.

**Exemples de sortida**:

*L'assistent respon demanant executar una eina per la que es requereix aprovació*
```json
{
    'stop_reason': 'pending_tool_confirm',
    'new_messages': [
        {
            'id': '56e06aa0-c195-4281-8e2e-cfa71a7010ce',
            'role': 'user',
            'content': 'Quin temps fa per sabadell?',
            'tool_calls': []
        },
        {
            'id': '41f24fb3-c8e6-49cb-9f8b-de3481fe01c9',
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {
                    'id': 'af030877-6661-49fd-ba52-8ee8baa2d77d',
                    'status': 'PendingConfirm',
                    'toolset_name': 'Weather',
                    'tool_name': 'get_weather_city',
                    'tool_args': {'city': 'Martorell'},
                    'tool_answer': None
                }
            ]
        }
    ],
    "tools_pending_consent": [
        {
            'id': 'af030877-6661-49fd-ba52-8ee8baa2d77d',
            'status': 'PendingConfirm',
            'toolset_name': 'Weather',
            'tool_name': 'get_weather_city',
            'tool_args': {'city': 'Martorell'},
            'tool_answer': None
        }
    ]
}
```

*L'assistent respon després que s'accepti l'execució d'una eina*
```json
{
    'stop_reason': 'awaiting_next_message',
    'new_messages': [
        {
            'id': 'f360eee8-3910-42c3-aa70-f085e467c9dc',
            'role': 'assistant',
            'content': 'A Sabadell actualment fa **13,2°C**, és de dia. El vent bufa a **6,7 km/h** amb una direcció de **54 graus** (aproximadament nord-est). El cel està clar, sense pluges ni condicions adverses.\n\nSi vols més detalls o previsions per a més endavant, digues-ho! 😊',
            'tool_calls': []
        }
    ]
}
```

### POST `/tool-consent`

Envia informació de consentiment pel que fa a una o més crides d'eines que estiguin pendents de ser processades.

**Paràmetres**:

- `conversation_id`: *string*  - L'identificador de conversa, retornat per `/start-chat` 
- `tool_consents`: *dict[string, bool]* - Per cada eina a confirmar, el valor cert si es vol confirmar l'execució o fals si es vol denegar.


**Notes de funcionament**:

Aquest endpoint només es pot cridar després que l'assistent respongui amb un `stop_reason`
de `pending_tool_confirm`.

S'ha de cridar aquest endpoint tant si es permet l'execució de l'eina com si no (amb el valor que correspongui, en cada cas) abans d'enviar un nou missatge.

Si s'envia confirmació per crides a eines inexistents, ja confirmades o que no tenen un
status de `PendingConfirm`, el sistema retornarà error.

**Sortida**

El format de sortida d'aquest endpoint és el mateix que amb les crides a `/start-message`.


### POST `/external-tool-output`

Envia la sortida d'eines locals després de la seva execució. Veure secció "Eines Locals"
per més informació.

**Paràmetres**

- `conversation_id`: *string*  - L'identificador de conversa, retornat per `/start-chat` 
- `tool_consents`: *dict[string, object[success: bool, output: str]]* - Per cada eina pendent d'execució local, un objecte JSON indicant si l'eina ha completat correctament (success), així com la sortida de l'eina que veurà el model.

**Notes de funcionament**:

Aquest endpoint només es pot cridar després que l'assistent respongui amb un `stop_reason`
de `awaiting_external_tool`.

Després de rebre l'stop reason, el client haurà d'executar les eines de manera local de la
manera que cregui convenient, i per cada eina marcada amb l'estat `PendingExternalResult`
a l'últim dels missatges retornats per l'assistent, haurà de comunicar una resposta.

Si s'envia la sortida per eines inexistents, ja confirmades o que no tenen un status de
`PendingExternalResult`, el sistema retornarà error.

**Sortida**

El format de sortida d'aquest endpoint és el mateix que amb les crides a `/start-message`.
