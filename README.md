# OneNote + To Do + Outlook Calendar Sync

Servicio que sincroniza automáticamente tareas de **Microsoft To Do** con páginas de **OneNote** y eventos de **Outlook Calendar**, usando la **Microsoft Graph API**.

Funciona en dos modos:
- **Local**: daemon en macOS via `launchd`, polling cada 30 segundos, cache en SQLite
- **Azure Functions**: timer trigger cada 1 minuto, cache en Azure Table Storage, token en Blob Storage

---

## Tabla de Contenidos

- [Cómo Funciona](#cómo-funciona)
- [Arquitectura](#arquitectura)
- [Requisitos Previos](#requisitos-previos)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Configuración](#configuración)
- [Ejecución Local](#ejecución-local)
- [Despliegue en Azure Functions](#despliegue-en-azure-functions)
- [Sistema de Reglas](#sistema-de-reglas)
- [Componentes Internos](#componentes-internos)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)

---

## Cómo Funciona

### Flujo Principal

1. El servicio monitorea 3 listas de Microsoft To Do: **Hoy**, **Esta semana**, **En espera**
2. En cada ciclo de sincronización:
   - Obtiene todas las tareas de cada lista via Graph API
   - Compara con el estado cacheado para detectar tareas nuevas, modificadas o eliminadas
   - Para cada **tarea nueva**: evalúa su complejidad con un sistema de scoring
   - Tareas complejas → crea página en OneNote con plantilla estructurada y enlaza desde To Do
   - Tareas con fecha de vencimiento → crea evento en Outlook Calendar
   - Tareas simples → solo se cachean para tracking
   - Tareas completadas → marca el evento de calendario como `[Completada]`
   - Tareas eliminadas → borra el evento de calendario y limpia el cache
3. Verifica si debe crear un evento de **revisión semanal** (configurable)

### Flujo de Datos

```
Microsoft To Do (3 listas)
        │
        ▼
   SyncEngine ──── TaskEvaluator (scoring)
    │  │  │
    │  │  └──► OneNote (crear página con plantilla)
    │  │          │
    │  │          └──► To Do (agregar link de OneNote al body)
    │  │
    │  └──────► Outlook Calendar (crear/actualizar evento)
    │
    └──────► Cache (SQLite local o Azure Table Storage)
```

### Ejemplo Concreto

Si creas esta tarea en la lista "Hoy" de To Do:

> **Investigar opciones de migración a la nube para el proyecto de facturación**

El sistema:
1. Detecta keywords positivos: "investigar", "proyecto" (+4 puntos)
2. Título largo >= 8 palabras (+1 punto)
3. Score total = 5, supera threshold de 2 → **necesita OneNote**
4. Crea página en OneNote con secciones: Objetivo, Notas, Próximas Acciones
5. Agrega link de OneNote al body de la tarea en To Do
6. Si tiene fecha de vencimiento, crea evento en Calendar: `[To Do] Investigar opciones...`

---

## Arquitectura

### Modo Local (macOS)

```
launchd (com.zulunity.onenote-todo-sync.plist)
  │
  └── python src/main.py
        │
        ├── AuthManager (MSAL device code flow)
        │     └── Token cache: ~/.onenote-todo-sync/token_cache.json
        │
        ├── GraphClient (requests.Session + retry)
        │
        ├── SyncEngine.run() ── loop con polling_interval
        │     ├── TodoService    → /me/todo/lists/*/tasks
        │     ├── OneNoteService → /me/onenote/sections/*/pages
        │     └── CalendarService → /me/events
        │
        ├── SyncCache (SQLite)
        │     └── ~/.onenote-todo-sync/sync_cache.db
        │
        └── Logs: ~/Library/Logs/OneNoteTodoSync/sync.log
```

### Modo Azure Functions

```
Azure Functions (Consumption Plan, Timer cada 1 min)
  │
  ├── function_app.py → SyncEngine.run_once()
  │
  ├── AzureAuthManager (silent-only, NO device code)
  │     └── BlobTokenCacheBackend
  │           └── Azure Blob Storage: sync-data/token_cache.json
  │
  ├── TableSyncCache (Azure Table Storage)
  │     ├── SyncedTasks   (estado de tareas sincronizadas)
  │     ├── SyncLog       (log de auditoría)
  │     └── WeeklyReviews (revisiones semanales creadas)
  │
  └── Application Insights (monitoring + logs)
```

### Infraestructura Azure

| Recurso | Nombre | SKU |
|---------|--------|-----|
| Resource Group | `rg-onenote-sync` | -- |
| Storage Account | `stonenotesynczulu` | Standard_LRS |
| Function App | `func-onenote-sync` | Consumption (Y1), Linux, Python 3.11 |
| Application Insights | `ai-onenote-sync` | -- |

Costo estimado: **$0-3 USD/mes** (1,440 ejecuciones/día x ~5s cada una, dentro del free tier).

---

## Requisitos Previos

### Azure AD App Registration

Registrar una aplicación en [Azure Portal > App Registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) con:

- **Supported account types**: Personal Microsoft accounts only
- **Redirect URI**: no se necesita (usa device code flow)
- **API Permissions** (delegated):
  - `Tasks.ReadWrite` - Leer/escribir tareas de To Do
  - `Notes.ReadWrite` - Leer/escribir páginas de OneNote
  - `Calendars.ReadWrite` - Leer/escribir eventos de Calendar
  - `User.Read` - Leer perfil del usuario

### Software

- Python >= 3.9
- Azure CLI (para provisionar infraestructura y deployments)
- Git

---

## Estructura del Proyecto

```
.
├── function_app.py              # Entry point Azure Functions (timer trigger)
├── host.json                    # Configuración del host de Azure Functions
├── local.settings.json          # Settings de desarrollo local (gitignored)
├── config.yaml                  # Configuración de la aplicación
├── requirements.txt             # Dependencias Python
├── setup.sh                     # Script de setup para macOS
├── .funcignore                  # Archivos excluidos del deployment
├── com.zulunity.onenote-todo-sync.plist  # launchd daemon (macOS)
│
├── src/
│   ├── main.py                  # Entry point local (CLI)
│   ├── auth.py                  # Autenticación MSAL (local + Azure)
│   ├── graph_client.py          # Cliente HTTP para Microsoft Graph API
│   │
│   ├── services/
│   │   ├── sync_engine.py       # Motor de sincronización (orquestador)
│   │   ├── todo_service.py      # Operaciones de Microsoft To Do
│   │   ├── onenote_service.py   # Operaciones de OneNote
│   │   └── calendar_service.py  # Operaciones de Outlook Calendar
│   │
│   ├── rules/
│   │   └── evaluator.py         # Evaluador de complejidad de tareas
│   │
│   ├── cache/
│   │   ├── local_cache.py       # Cache SQLite (modo local)
│   │   └── table_cache.py       # Cache Azure Table Storage (modo Azure)
│   │
│   └── utils/
│       └── logger.py            # Configuración de logging
│
├── scripts/
│   ├── upload_token_cache.py    # Subir token cache a Blob Storage
│   └── migrate_sqlite_to_table.py  # Migrar datos SQLite → Table Storage
│
└── tests/                       # 95 tests
    ├── conftest.py              # Fixtures compartidos
    ├── mocks/
    │   └── graph_responses.py   # Datos mock de Graph API
    ├── test_auth.py
    ├── test_blob_auth.py
    ├── test_graph_client.py
    ├── test_local_cache.py
    ├── test_table_cache.py
    ├── test_function_app.py
    ├── test_sync_engine.py
    ├── test_evaluator.py
    ├── test_todo_service.py
    ├── test_onenote_service.py
    ├── test_calendar_service.py
    └── test_integration.py
```

---

## Configuración

### Variables de Entorno (.env)

```bash
CLIENT_ID=tu-azure-app-client-id
CLIENT_SECRET=tu-client-secret
TENANT_ID=tu-tenant-id
# Solo necesario para scripts de Azure:
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
```

### config.yaml

```yaml
# Notebook de OneNote donde se crean las páginas
notebook_name: "My Notebook"

# Listas de To Do a monitorear
monitored_lists:
  - "Hoy"
  - "Esta semana"
  - "En espera"

# Intervalo de polling en modo local (segundos)
polling_interval_seconds: 30

# Mapeo lista → sección de OneNote
list_to_section_map:
  "Hoy": "Hoy"
  "Esta semana": "Esta semana"
  "En espera": "En espera"

# Reglas de evaluación de complejidad
rules:
  positive_keywords:    # +2 puntos por match
    - "preparar"
    - "diseñar"
    - "investigar"
    - "organizar"
    - "resolver"
    - "planear"
    - "propuesta"
    - "presentación"
    - "proyecto"
    - "analizar"
    - "evaluar"
    - "documentar"
    - "estrategia"
  negative_keywords:    # -2 puntos por match
    - "pagar"
    - "comprar"
    - "llamar"
    - "enviar"
    - "mandar"
    - "imprimir"
    - "agendar"
    - "recordar"
  force_onenote_prefix: "#onenote"   # Forzar creación de página
  force_skip_prefix: "#simple"       # Forzar NO crear página
  min_words_for_complex: 8           # Títulos largos = +1 punto
  score_threshold: 2                 # Score mínimo para crear página

# Revisión semanal automática
weekly_review:
  enabled: true
  day: "sunday"
  time: "18:00"
  duration_minutes: 30

# Logging
logging:
  level: "INFO"
  file_path: "~/Library/Logs/OneNoteTodoSync/sync.log"
  max_file_size_mb: 10
  backup_count: 5
```

---

## Ejecución Local

### Setup Rápido

```bash
# 1. Clonar el repositorio
git clone https://gitlab.com/zulunity/internal/oneNote_toDo_managment_tool.git
cd oneNote_toDo_managment_tool

# 2. Crear .env con tus credenciales
cat > .env << 'EOF'
CLIENT_ID=tu-client-id
CLIENT_SECRET=tu-client-secret
TENANT_ID=tu-tenant-id
EOF

# 3. Ejecutar setup (crea venv, instala deps, autentica, corre tests, instala servicio)
chmod +x setup.sh
./setup.sh
```

### Setup Manual

```bash
# Crear virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Autenticar (abre browser para device code flow)
python src/main.py --auth

# Un solo ciclo de sincronización
python src/main.py --once

# Daemon (loop continuo, se detiene con Ctrl+C)
python src/main.py
```

### Controlar el Servicio launchd

```bash
# Ver estado
launchctl list | grep onenote-todo-sync

# Detener
launchctl unload ~/Library/LaunchAgents/com.zulunity.onenote-todo-sync.plist

# Iniciar
launchctl load ~/Library/LaunchAgents/com.zulunity.onenote-todo-sync.plist

# Ver logs
tail -f ~/Library/Logs/OneNoteTodoSync/sync.log
```

### Rutas de Archivos Locales

| Archivo | Ruta |
|---------|------|
| Token cache | `~/.onenote-todo-sync/token_cache.json` |
| SQLite cache | `~/.onenote-todo-sync/sync_cache.db` |
| Log | `~/Library/Logs/OneNoteTodoSync/sync.log` |
| launchd plist | `~/Library/LaunchAgents/com.zulunity.onenote-todo-sync.plist` |

---

## Despliegue en Azure Functions

### 1. Provisionar Infraestructura

```bash
# Login en Azure
az login

# Registrar resource providers
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Web
az provider register --namespace Microsoft.Insights
az provider register --namespace microsoft.operationalinsights

# Crear resource group
az group create --name rg-onenote-sync --location eastus

# Crear storage account
az storage account create \
  --name stonenotesynczulu \
  --resource-group rg-onenote-sync \
  --location eastus \
  --sku Standard_LRS

# Crear Application Insights
az monitor app-insights component create \
  --app ai-onenote-sync \
  --resource-group rg-onenote-sync \
  --location eastus \
  --kind web \
  --application-type web

# Crear Function App
az functionapp create \
  --name func-onenote-sync \
  --resource-group rg-onenote-sync \
  --storage-account stonenotesynczulu \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --os-type Linux \
  --functions-version 4 \
  --app-insights ai-onenote-sync

# Configurar CLIENT_ID
az functionapp config appsettings set \
  --name func-onenote-sync \
  --resource-group rg-onenote-sync \
  --settings "CLIENT_ID=tu-client-id"
```

### 2. Subir Token Cache

El servicio usa **delegated permissions** con cuenta personal. Azure Functions no puede ejecutar device code flow, así que se autentica localmente una vez y se sube el refresh token:

```bash
# Asegurar que tenemos un token fresco
python src/main.py --auth

# Obtener connection string
az storage account show-connection-string \
  --name stonenotesynczulu \
  --resource-group rg-onenote-sync -o tsv

# Agregar a .env
echo "AZURE_STORAGE_CONNECTION_STRING=<connection-string>" >> .env

# Subir token cache a Blob Storage
python scripts/upload_token_cache.py
```

El refresh token se renueva automáticamente cada vez que se usa (ventana deslizante de 90 días). Como la función corre cada minuto, el token nunca expira.

### 3. Migrar Datos (Opcional)

Si ya tienes datos en el SQLite local:

```bash
python scripts/migrate_sqlite_to_table.py
```

### 4. Deploy

```bash
# Crear zip excluyendo archivos innecesarios
zip -r /tmp/func-deploy.zip . \
  -x "tests/*" ".venv/*" "venv/*" ".env" "*.db" ".git/*" \
     ".gitignore" ".pytest_cache/*" "__pycache__/*" "*/__pycache__/*" \
     "*.pyc" "*.pyo" "setup.sh" "local.settings.json" \
     ".claude/*" ".funcignore" "scripts/*" \
     "com.zulunity.onenote-todo-sync.plist"

# Deploy con remote build
az functionapp deployment source config-zip \
  --name func-onenote-sync \
  --resource-group rg-onenote-sync \
  --src /tmp/func-deploy.zip \
  --build-remote true
```

### 5. Verificar

```bash
# Verificar estado
az functionapp show --name func-onenote-sync \
  --resource-group rg-onenote-sync \
  --query "{state:state, runtime:siteConfig.linuxFxVersion}" -o table

# Ver logs recientes en Application Insights
az monitor app-insights query \
  --app ai-onenote-sync \
  --resource-group rg-onenote-sync \
  --analytics-query "traces | where message contains 'Sync cycle' | order by timestamp desc | take 5 | project timestamp, message"
```

### Cómo Funciona la Autenticación en Azure

```
1. Localmente: device code flow → genera token_cache.json (con refresh token)
2. upload_token_cache.py → sube a Blob Storage (sync-data/token_cache.json)
3. Azure Function arranca:
   a. BlobTokenCacheBackend.load() → descarga cache desde Blob
   b. AzureAuthManager.get_token() → llama acquire_token_silent()
   c. MSAL usa el refresh token para obtener nuevo access token
   d. BlobTokenCacheBackend.save() → sube cache actualizado a Blob
4. El refresh token se renueva con cada uso (ventana deslizante de 90 días)
5. Si acquire_token_silent() falla → RuntimeError (NO device code flow)
```

---

## Sistema de Reglas

El `TaskEvaluator` decide si una tarea necesita una página de OneNote usando un sistema de scoring:

| Criterio | Puntos | Ejemplo |
|----------|--------|---------|
| Keyword positivo en título | +2 c/u | "**investigar** opciones..." |
| Keyword negativo en título | -2 c/u | "**pagar** luz" |
| Titulo largo (>= 8 palabras) | +1 | "Preparar presentación para el comité de..." |
| Titulo corto (< 4 palabras) | -1 | "Comprar leche" |
| Body con contenido | +1 | Tarea con notas adjuntas |

**Threshold**: score >= 2 → se crea página en OneNote.

### Overrides Manuales

Agregar un prefijo al título de la tarea para forzar el comportamiento:

- `#onenote Revisar notas del sprint` → **siempre** crea página (ignora score)
- `#simple Investigar algo rápido` → **nunca** crea página (ignora score)

### Ejemplos

| Tarea | Score | OneNote? |
|-------|-------|----------|
| "Pagar luz" | -2 (keyword) -1 (corta) = -3 | No |
| "Comprar pan" | -2 (keyword) -1 (corta) = -3 | No |
| "Investigar opciones de migración a la nube para el proyecto" | +2+2 (keywords) +1 (larga) = 5 | Si |
| "Preparar presentación de resultados trimestrales" | +2+2 (keywords) +1 (larga) = 5 | Si |
| "Revisar correos" | -1 (corta) = -1 | No |
| "#onenote Tarea simple" | override | Si |
| "#simple Investigar algo" | override | No |

---

## Componentes Internos

### `AuthManager` / `AzureAuthManager` (`src/auth.py`)

Maneja la autenticación con Microsoft Graph API usando MSAL.

- **Local (`AuthManager`)**: Usa device code flow para la primera autenticación. Persiste el token cache en disco (`~/.onenote-todo-sync/token_cache.json`). En ejecuciones siguientes usa `acquire_token_silent()` para renovar tokens sin intervención del usuario.
- **Azure (`AzureAuthManager`)**: Solo usa `acquire_token_silent()`. Si falla, lanza `RuntimeError` en lugar de pedir device code flow (que bloquearía indefinidamente). El token cache se lee/escribe en Azure Blob Storage via `BlobTokenCacheBackend`.

Scopes solicitados:
- `Tasks.ReadWrite` - Microsoft To Do
- `Notes.ReadWrite` - OneNote
- `Calendars.ReadWrite` - Outlook Calendar
- `User.Read` - Perfil del usuario

### `GraphClient` (`src/graph_client.py`)

Cliente HTTP para Microsoft Graph API (`https://graph.microsoft.com/v1.0`) con:

- **Retry automático**: Reintentos con exponential backoff en errores 5xx y errores de conexión
- **Rate limiting**: Respeta el header `Retry-After` en respuestas 429
- **Token refresh en 401**: En modo local, limpia la cuenta MSAL y reintenta. En Azure Functions, solo reintenta sin limpiar la cuenta (para no caer a device code flow)
- **Paginación automática**: `get_all()` sigue `@odata.nextLink` hasta obtener todos los resultados

### `SyncEngine` (`src/services/sync_engine.py`)

El orquestador principal. Dos modos de ejecución:

- **`run()`**: Loop de polling bloqueante con manejo de SIGTERM/SIGINT (modo local)
- **`run_once()`**: Un solo ciclo de sincronización (Azure Functions y testing)

Cada ciclo:
1. Inicializa: descubre notebook, secciones y IDs de listas de To Do
2. Para cada lista monitoreada: compara tareas remotas vs cache
3. Maneja tareas nuevas, modificadas y eliminadas
4. Verifica si corresponde crear evento de revisión semanal

### `TodoService` (`src/services/todo_service.py`)

Wrapper sobre la API de Microsoft To Do:
- `get_lists()` / `find_list_by_name()` - Obtener listas
- `get_tasks()` / `get_task()` - Obtener tareas
- `update_task_body()` - Agregar link de OneNote al body
- `mark_task_completed()` - Marcar tarea como completada

### `OneNoteService` (`src/services/onenote_service.py`)

Wrapper sobre la API de OneNote:
- `get_notebook()` - Buscar notebook por nombre
- `ensure_section()` - Obtener o crear sección
- `create_page()` - Crear página con plantilla HTML (Objetivo, Notas, Próximas Acciones)
- `get_page_link()` - Obtener URL web de una página

### `CalendarService` (`src/services/calendar_service.py`)

Wrapper sobre la API de Outlook Calendar:
- `create_event()` - Crear evento (timezone: America/Mexico_City)
- `update_event()` - Actualizar evento (ej. marcar como `[Completada]`)
- `delete_event()` - Eliminar evento
- `create_weekly_review()` - Crear evento de revisión semanal con resumen de tareas pendientes

### `TaskEvaluator` (`src/rules/evaluator.py`)

Evalúa si una tarea necesita página de OneNote usando scoring configurable. Ver [Sistema de Reglas](#sistema-de-reglas).

### `SyncCache` / `TableSyncCache` (`src/cache/`)

Ambas implementaciones exponen la misma interfaz para que `SyncEngine` funcione sin cambios:

| Método | Descripción |
|--------|-------------|
| `get_task(task_id)` | Obtener tarea por ID |
| `get_all_tasks()` | Obtener todas las tareas |
| `get_tasks_by_list(list_name)` | Filtrar tareas por lista |
| `upsert_task(task_data)` | Insertar o actualizar tarea |
| `delete_task(task_id)` | Eliminar tarea |
| `log_action(action, task_id, details, success)` | Log de auditoría |
| `get_weekly_review(week_start)` | Verificar si existe revisión semanal |
| `save_weekly_review(event_id, week_start)` | Guardar revisión semanal |
| `close()` | Cerrar conexión |

**`SyncCache`** (local): SQLite con 3 tablas (`synced_tasks`, `sync_log`, `weekly_reviews`).

**`TableSyncCache`** (Azure): Azure Table Storage con 3 tablas. Mapea entre PascalCase (Azure) y snake_case (Python) automáticamente.

| Tabla Azure | PartitionKey | RowKey | Uso |
|-------------|-------------|--------|-----|
| `SyncedTasks` | `list_name` | `task_id` | Estado de tareas |
| `SyncLog` | `"log"` | reverse timestamp | Auditoría |
| `WeeklyReviews` | `"review"` | `week_start` | Revisiones semanales |

### Logger (`src/utils/logger.py`)

- **Modo local**: `RotatingFileHandler` (10 MB, 5 backups) + console
- **Modo Azure**: Solo console (Application Insights captura los logs automáticamente)
- Detecta el modo via la variable de entorno `AZURE_FUNCTIONS_ENVIRONMENT`

---

## Tests

95 tests en 12 archivos, ejecutados con pytest:

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

| Archivo | Tests | Qué cubre |
|---------|-------|-----------|
| `test_auth.py` | 6 | AuthManager: silent token, device code flow, errores |
| `test_blob_auth.py` | 9 | BlobTokenCacheBackend + AzureAuthManager |
| `test_graph_client.py` | 9 | GET, POST, PATCH, DELETE, retry, rate limit, 401 handling |
| `test_local_cache.py` | 9 | SyncCache (SQLite): CRUD, logging, weekly reviews |
| `test_table_cache.py` | 11 | TableSyncCache: CRUD, logging, weekly reviews, field mapping |
| `test_sync_engine.py` | 9 | Inicialización, new/modified/removed tasks, signals |
| `test_evaluator.py` | 11 | Scoring, keywords, prefixes, edge cases |
| `test_todo_service.py` | 8 | Listas y tareas de To Do |
| `test_onenote_service.py` | 8 | Notebooks, secciones, páginas |
| `test_calendar_service.py` | 7 | Eventos de calendario, revisión semanal |
| `test_function_app.py` | 3 | Timer trigger, past due, propagación de errores |
| `test_integration.py` | 1 | Ciclo completo end-to-end (mocked) |

Todos los tests usan mocks/fakes (no requieren conexión a Azure ni Graph API).

---

## Troubleshooting

### El token expiró en Azure Functions

Si la función deja de autenticarse (ej. no se ejecutó por >90 días):

```bash
# Re-autenticar localmente
python src/main.py --auth

# Re-subir token cache
python scripts/upload_token_cache.py
```

### La función no aparece en Azure Portal

Después de un deploy, la función puede tardar 1-2 minutos en aparecer (cold start de Consumption plan). Verificar en Application Insights:

```bash
az monitor app-insights query --app ai-onenote-sync --resource-group rg-onenote-sync \
  --analytics-query "requests | order by timestamp desc | take 5 | project timestamp, name, success, duration"
```

### Errores de "SubscriptionNotFound" al provisionar

Registrar los resource providers necesarios:

```bash
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Web
az provider register --namespace Microsoft.Insights
az provider register --namespace microsoft.operationalinsights
```

### Ver logs en Azure

```bash
# Últimos traces
az monitor app-insights query --app ai-onenote-sync --resource-group rg-onenote-sync \
  --analytics-query "traces | where message contains 'onenote_todo_sync' | order by timestamp desc | take 20 | project timestamp, message"

# Excepciones
az monitor app-insights query --app ai-onenote-sync --resource-group rg-onenote-sync \
  --analytics-query "exceptions | order by timestamp desc | take 10 | project timestamp, type, outerMessage"

# Invocaciones de la función
az monitor app-insights query --app ai-onenote-sync --resource-group rg-onenote-sync \
  --analytics-query "requests | order by timestamp desc | take 10 | project timestamp, name, success, duration"
```

---

## Dependencias

| Paquete | Uso |
|---------|-----|
| `msal` | Autenticación con Microsoft Identity Platform |
| `requests` | Cliente HTTP |
| `python-dotenv` | Carga de variables `.env` |
| `pyyaml` | Parsing de `config.yaml` |
| `azure-functions` | Runtime de Azure Functions |
| `azure-data-tables` | Azure Table Storage SDK |
| `azure-storage-blob` | Azure Blob Storage SDK |
| `pytest` | Framework de testing |
| `pytest-cov` | Cobertura de tests |
