---
name: sesion-2026-06-04-talento
description: Sesion de trabajo del 2026-06-04 sobre TALENTO Ecopetrol — preparacion demo, modularizacion ACI, App Insights bridge, dual correlation routing, validacion SOX, diagnostico AWX
metadata:
  type: session-log
  date: 2026-06-04
  project: talento-ecopetrol
related:
  - talento-ecopetrol-rfp.md
  - feedback-docs-over-assumptions.md
---

# Sesion 2026-06-04 — TALENTO Ecopetrol

Sesion larga (~2 dias de trabajo continuo, compactada 1 vez). Objetivo: dejar la demo lista con observabilidad real, modularizacion productiva y datos vivos. Cierre: 8 de 11 escenarios operativos sin AWX; SOX validado empiricamente con `nvivas` produciendo risk score 26.3% HIGH.

## Estado al cierre

| Capa | Estado |
|---|---|
| Foundry agent v30 | ✓ smokes 2/2 PASS (UUID Spring Boot + OperationId AI) |
| Bridge L2 (function-app) | ✓ catalog v20-correlation-dual desplegado local |
| ACI 2 runtime (`aci-centralecopetrol2`) | ✓ data viva, ~250 eventos / 3h, helper ARM directo |
| App Insights bridge (Camino B) | ✓ `lookup_app_insights` consulta componente AI Classic directo |
| Workspace 2 (`law-central-soluciontalento2`) | ✓ tablas App* pobladas, customerId `14135f7a-c66a-492c-8c8b-124cdea16c2d` |
| Workspace 1 (`9e0a97a6-...`) | ⚠ vacio de eventos nuevos, legacy |
| Sidebar webapp | ✓ 9 primary, 0 pending |
| Teams cards | ✓ catalogo TLNT + Action.OpenUrl + auto-trigger desde bridge |
| AWX local (192.168.250.20) | ✗ no alcanzable desde shell Claude (WSL2 sin ruta) — verificar desde shell user |
| AWX Azure (172.210.65.202) | ✗ timeout desde shell Claude — posible whitelisting o down |
| Commit 4b685c6 | ✓ pushed origin/develop |

## Decisiones arquitectonicas tomadas

### 1. Modularizacion ACI/RG/AppService/SQL via `.env`

Eliminado todo hardcoded de nombres en bridge y playbooks. `.env` es la unica fuente. Variables nuevas: `ACI_NAME`, `ACI_RESOURCE_GROUP`, `APPSERVICE_NAME`, `APPSERVICE_RESOURCE_GROUP`, `SQL_SERVER_NAME`, `SQL_RESOURCE_GROUP`, `APP_INSIGHTS_NAME`, `APP_INSIGHTS_RESOURCE_GROUP`.

Razon: usuario explicito *"Para cualquier persona o actor el ACI es transparente, solo internamente sabemos que existe una version 2 o el dia de mañana 3"*. Cambio de target sin tocar codigo.

### 2. Migracion TODO a ACI 2 (`aci-centralecopetrol2` en `rg-central-solucion-talento2`)

ACI 1 deprecado para propositos de la demo. Helper `_get_aci_client()` + `fetch_aci_runtime_logs()` apunta a ACI 2 via ARM directo (no via Log Analytics).

### 3. Application Insights — Camino B (bridge directo al componente)

Microsoft requiere migracion de Classic a workspace-based antes Feb 2027. Mientras tanto, plataforma no convierte tablas viejas → nuevas. Solucion: `lookup_app_insights` consulta el componente AI directo via `LogsQueryClient.query_resource(componente_resource_id, ...)` con 6 modos: `top_endpoints`, `latency_p95`, `errors_5xx`, `slow_deps`, `top_exceptions`, `throughput`.

### 4. Dual correlation_id routing

Detectado empiricamente: Spring Boot UUID con guiones != App Insights OperationId hex 32 sin guiones. Handler `lookup_correlation_id` ramificado por formato:

- UUID con guiones → KQL legacy contra workspace 1 + fallback al runtime buffer ACI 2 si 0 filas
- Hex 32 chars sin guiones → KQL union de `AppRequests`/`AppDependencies`/`AppExceptions`/`AppTraces` contra workspace 2 (`14135f7a-...`, hardcoded)

### 5. Threshold brute-force propagado end-to-end UI → tool

Coordinado en 5 capas: aggregator firma, handler propaga, tool schema, scenario `accepts_filters: ["failed_threshold"]`, prompt interpola `{failed_threshold}`. Antes era hardcoded 3.

### 6. Cards Teams con catalogo TLNT + auto-trigger desde bridge

Catalogo compartido `vars/tlnt_catalog.yml` (15 codigos TLNT-001 → TLNT-015) consumido por playbooks Ansible y por el bridge Python. Helper `notify_teams_finding()` con auto-trigger desde `lookup_runtime_logs` para SOX y Brute Force (no solo desde AWX). Role Ansible `teams_card` parametrizado con template Jinja, badge severidad HIGH/MEDIUM/LOW/OK/INFO, FactSet, Action.OpenUrl.

### 7. Sidebar curada 11 → 9 escenarios

Removidos duplicados (tlnt-explorer + top-codigos fusionados), reactivados SOX/Brute Force/User Activity/Performance a `tier=primary`, Health Check con selector de scope (`completo`/`container`/`appservice`/`sql`). Ocultas 3 info cards (solo Agente IA + Historial Runs visibles).

## Issues y workarounds

| Issue | Diagnostico | Workaround / Fix |
|---|---|---|
| Cards Teams no llegaban | SSL CERTIFICATE_VERIFY_FAILED contra Power Platform | `validate_certs: no` en 8 playbooks (webhook SAS-auth, seguro para demo) |
| ENV_PATH bug en bridge_l2.py | Path apuntaba a `function-app/` en vez de raiz | `Path(__file__).parent.parent / ".env"` |
| JT 33 vs JT 49 | Agent v26 tenia tool description con JT IDs Azure por timing setup | Force agent v27 con JT IDs locales via `setup_agent_version()` |
| `make demo-local` port 8000 in use | uvicorn de sesion previa en background | `pkill -f "uvicorn webapp.app"` |
| AWX inalcanzable desde Claude shell | WSL2 sin ruta a 192.168.250.0/24; AWX Azure tambien timeout | Pendiente: usuario verifica desde su terminal |

## Datos vivos confirmados (para demo)

### Usuarios SOX

- **`nvivas`** → 95 eventos / 25 errores / 26.3% risk → **HIGH**. Codigos TLNT-001, 012, 013, 014. Modulos: CalamidadController, IncapacidadController, CumpleanioController, etc. Validado 2026-06-04 15:00.
- **`cmedina`** → risk MEDIUM (de pruebas previas)
- **`jtorres`** → risk LOW (de pruebas previas)

### Correlation IDs

- Spring Boot UUID (con guiones): `b8be1659-bc5b-49e5-8e0c-d8fc51f33956` (validado v30)
- App Insights OperationId (hex 32): pendiente capturar uno vivo del workspace 2

### Workspaces y recursos

- `LOG_ANALYTICS_WORKSPACE_ID` (legacy): `9e0a97a6-6839-4507-aae4-e4d706d1c320` — workspace 1
- `WORKSPACE_ID_APPINSIGHTS` (vivo): `14135f7a-c66a-492c-8c8b-124cdea16c2d` — workspace 2
- SP `logssolution`: `bbd498f7-caed-4daa-a236-f12fd3a13461` con Contributor sobre ambos RGs
- AI Component: `ai-central-ecopetrol2` en `rg-central-solucion-talento2` (modo Classic)

## Archivos criticos del proyecto

- [bridge_l2.py](../../function-app/bridge_l2.py) — catalog `v20-correlation-dual`, 7 tools registradas
- [scenarios.py](../../webapp/scenarios.py) — 9 primary, 0 pending
- [tlnt_catalog.yml](../../vars/tlnt_catalog.yml) — 15 codigos compartido
- [roles/teams_card/](../../roles/teams_card/) — role Ansible reusable
- [talento-errors-analysis.yml](../../playbooks/talento-errors-analysis.yml) — playbook con `include_role: teams_card`
- [index.html](../../webapp/templates/index.html) — 3 info cards ocultas
- [ecp.js](../../webapp/static/js/ecp.js) — handler tool.call ramificado por nombre
- [requirements.txt](../../function-app/requirements.txt) — agregados `azure-mgmt-containerinstance>=10.0.0`, `azure-monitor-query>=1.2.0`

## Constraints del usuario (preservar verbatim)

- "siempre bajo documentacion y no suposiciones" → ver [feedback-docs-over-assumptions.md](feedback-docs-over-assumptions.md)
- "Es una demo, no lo roto hasta nueva orden" (re Azure secret rotation)
- "No ejecutes playbooks de autoremediacion"
- "El conocimiento va en file_search, no en system_instructions"
- ".env is gitignored — never commit secrets"
- "no macheteos, todo 100% arquitectonico"
- "no vayas a ser invasivo"
- "Para cualquier persona o actor el ACI es transparente, solo internamente sabemos que existe una version 2"
- `validate_certs: no` aplicado SOLO en webhook Teams (webhook SAS-auth, no produccion)
- Commits con `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`

## TODO list al cierre

1. [completed] lookup_correlation_id dual: UUID Spring Boot (legacy + fallback runtime) + OperationId AI (workspace 2)
2. [completed] Agent v30 + smokes 2/2 PASS para ambos formatos
3. [completed] Commit 4b685c6 pushed (ya en origin/develop)
4. [in_progress] Lista final correlation_ids consultables (ambos formatos)

## Pendientes futuros (no urgentes)

- Migrar componente AI Classic → workspace-based (Microsoft deadline Feb 2027)
- Determinar causa raiz del AWX inalcanzable (VM K3s apagada vs whitelisting vs ambas down)
- Capturar un OperationId AI vivo del workspace 2 para listo-de-demo
- Eval Runner Phase 1 (b) — refactor arquitectonico pendiente, plan en `~/.claude/plans/estaba-pensando-si-creamos-buzzing-rabin.md`

## Diagnostico de red (cierre)

```
Mi shell (Claude WSL2):
  eth0: 172.29.228.85/20
  gateway: 172.29.224.1
  default route: solo Internet publico, sin ruta a 192.168.250.0/24

Tests:
  ifconfig.me HTTPS:           HTTP 200 < 1s   ✓
  github.com HTTPS:             HTTP 200 < 1s   ✓
  AWX Azure (172.210.65.202):  HTTP 000 5s     ✗ timeout — posible whitelisting/down
  AWX local (192.168.250.20):   HTTP 000 5s     ✗ no enrutable desde mi WSL2
  192.168.250.20:22 (SSH):      CERRADO         ✗ confirma no-ruta o VM apagada
```

Verificacion pendiente desde shell del usuario:
```bash
curl -sk -I --max-time 5 https://192.168.250.20.nip.io/api/v2/ping/
curl -sk -I --max-time 5 http://172.210.65.202.nip.io/api/v2/ping/
```

## Como mostrar la demo sin AWX

8 escenarios operativos sin AWX (van por Foundry → workspace / AI Classic / runtime ACI 2 directo):

1. **Auditoria SOX por Usuario** — validado con `nvivas` → HIGH 26.3%
2. **Health Check** — scope selector (`completo`/`container`/`appservice`/`sql`)
3. **Top Codigos TLNT / TLNT Explorer** — unificado
4. **User Activity**
5. **Errores Recientes** (datos, no remediacion)
6. **Brute Force** con threshold parametrizable
7. **Investigar Correlation ID** — dual UUID/OperationId
8. **App Insights** — 6 modos

Pierden funcionalidad sin AWX los 3 escenarios de remediacion: Restart ACI / Stop ACI / Start ACI.
