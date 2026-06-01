# function-app — TALENTO Agent on Azure Function

Azure Function (Python 3.11, Flex Consumption) que hostea el agente IA de TALENTO
para diagnóstico y remediación. Reemplaza el dashboard FastAPI local — pensado
para producción event-driven.

## Arquitectura

```
ELK / Azure Monitor / fuente HTTP
        ↓ HTTP POST con alerta o scenario
fa-solucion-talento.azurewebsites.net (Azure Function)
        ↓ function_app.py recibe webhook
        ↓ bridge_l2.run_cycle() invoca al agente
Azure AI Foundry (proj-foundry-is2)
        ├─ tool query_log_analytics → Log Analytics (KQL)
        └─ tool run_awx_job_template → AWX Azure (172.210.65.202)
                ↓ ejecuta playbook Ansible
            Azure ARM API / Log Analytics / Teams webhook
        ↓ síntesis del agente
respuesta JSON al caller
```

## Endpoints

| Path | Auth | Función |
|---|---|---|
| `GET /api/health` | anonymous | Healthcheck — devuelve agent_name + jt_ids_count |
| `GET /api/agent/info` | function key | Devuelve config completa del agente + JT IDs + scenarios |
| `POST /api/run` | function key | Invoca al agente con payload |

## Payloads aceptados en `/api/run`

```json
{ "scenario": "infra-health-check" }       // pre-canned (recomendado)
{ "user_question": "texto libre..." }       // raw
{ "alert": { "source": "elk", ... } }       // de ELK/Monitor
```

## Scenarios disponibles (no invasivos)

- `infra-health-check` — orchestrator ACI+AppService+SQL (JT 39)
- `container-state` — estado del ACI (JT 36)
- `appservice-state` — estado App Service (JT 37)
- `sql-health` — estado SQL (JT 38)
- `system-status` — workspace snapshot (JT 32)
- `errors-production` — análisis errores (JT 33)
- `sox-audit` — auditoría SOX (JT 34)
- `brute-force` — detector brute force (JT 35)

**No expuestos por defecto**: scenarios de remediación (restart/stop/start).
Los JTs existen (40-43) y los playbooks tienen `dry_run=true` por defecto, pero
no están en el dict SCENARIO_PROMPTS para evitar invocación accidental.

## Auth

Usa **System Assigned Managed Identity** del Function App.
- Principal ID: `35764226-3c7f-4221-82ee-de9463775e21`
- App ID: `77048d7a-0783-44b4-9bc0-113466ce323c`
- Roles asignados:
  - `Azure AI Administrator` @ proj-foundry-is2
  - `AzureML Data Scientist` @ proj-foundry-is2
  - `Contributor` @ rg-central-solucion-talento
  - `Cognitive Services User` @ proj-foundry-is2
  - `Azure AI Developer` @ proj-foundry-is2

> **Nota**: existe también una User Assigned MI `mi-soluciontalento`
> (`7fee0205-...`) attached al Function App pero **sin uso actual** — se mantiene
> attached por si se decide migrar a User Assigned en el futuro.

## Application Settings requeridos

```
AZURE_TENANT_ID                  # tenant de Ecopetrol
AZURE_CLIENT_ID                  # SP logssolution (auth a Azure ARM desde playbooks)
AZURE_CLIENT_SECRET              # secret del SP
AZURE_SUBSCRIPTION_ID            # subscription
LOG_ANALYTICS_WORKSPACE_ID       # workspace id

AWX_URL                          # http://172.210.65.202.nip.io
AWX_TOKEN                        # token de AWX Azure
AWX_ORG_ID                       # 4
AWX_USER_ID                      # 4

# Mapeo JT IDs en AWX Azure (32-43)
AWX_JT_WORKSPACE_SNAPSHOT=32
AWX_JT_ERRORS_ANALYSIS=33
AWX_JT_SOX_AUDIT=34
AWX_JT_BRUTE_FORCE=35
AWX_JT_ACI_STATE=36
AWX_JT_APPSERVICE_STATE=37
AWX_JT_SQL_HEALTH=38
AWX_JT_FULL_HEALTH_CHECK=39
AWX_JT_ACI_RESTART=40           # invasivo (dry_run=true)
AWX_JT_ACI_STOP=41               # invasivo (dry_run=true)
AWX_JT_ACI_START=42              # invasivo (dry_run=true)
AWX_JT_APPSERVICE_RESTART=43     # invasivo (dry_run=true)

TEAMS_WEBHOOK_URL                # adaptive cards de playbooks
```

**NO requiere** `AZURE_MI_CLIENT_ID` — al estar vacío, usa System Assigned MI.

## Deploy

```bash
# Construir zip
cd function-app/
zip -r /tmp/talento-function.zip . -x "__pycache__/*" "*.log"

# Desplegar
az functionapp deployment source config-zip \
  -n fa-solucion-talento \
  -g rg-central-solucion-talento \
  --src /tmp/talento-function.zip
```

Esperar ~30s post-deploy para warm-up.

## Smoke test

```bash
FUNC_KEY=$(az functionapp keys list -n fa-solucion-talento -g rg-central-solucion-talento --query "functionKeys.default" -o tsv)
BASE="https://fa-solucion-talento-akdhbnczhvaxfde0.centralus-01.azurewebsites.net"

# Health (sin auth)
curl "$BASE/api/health"

# Info del agente
curl "$BASE/api/agent/info?code=$FUNC_KEY"

# Run scenario diagnóstico (no invasivo)
curl -X POST "$BASE/api/run?code=$FUNC_KEY" \
  -H "Content-Type: application/json" \
  -d '{"scenario": "infra-health-check"}'
```

## Próximos pasos para producción

1. **Definir la fuente real de eventos** (ELK / Azure Monitor / Grafana / etc.)
   y configurar su webhook hacia `/api/run`.
2. **Reemplazar function key por auth más robusta** (Entra ID app registration
   con OAuth2, o IP allowlist) si la fuente es interna.
3. **Application Insights instrumentado** desde la app TALENTO (pedido a EAPPS).
4. **Migrar de System Assigned a User Assigned MI** si se quiere portabilidad
   (re-asignar todos los roles a `mi-soluciontalento` y volver a setear
   AZURE_MI_CLIENT_ID).
