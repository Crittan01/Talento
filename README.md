# talento-ecopetrol — DEMO de automatización + agentic AI

Demo construida para sustentar la oferta técnica de NTT al RFP de **Ecopetrol** —
casos técnicos sobre la solución corporativa **TALENTO** (gestión de talento
humano, IaaS, 7x24, SOX-regulada).

## Frente de este repo

**Automatización + agentic AI**. La pieza de observabilidad pura la trabaja un
compañero (Application Insights + Log Analytics + ELK). La pieza de aplicación
demo "rota a propósito" la trabaja el equipo EAPS.

Lo que está aquí demuestra que un agente desplegado en **Azure AI Foundry**
puede:

1. Recibir una pregunta operativa en lenguaje natural.
2. Decidir **autónomamente** qué consultar contra el ecosistema de logs.
3. Ejecutar consultas KQL via un runtime de automatización.
4. Auto-corregirse si una consulta falla por desconocer el esquema.
5. Sintetizar una respuesta técnica estructurada (hallazgo + RCA + diagnóstico
   + acción) en español.

## Arquitectura del demo

```
  ┌─────────────┐    pregunta     ┌──────────────────────────┐
  │   Usuario   │ ──────────────► │  Azure AI Foundry        │
  └─────────────┘                 │  proj-foundry-is2        │
                                  │  └─ talento-triage-agent │
                                  │     (model: gpt-4o-mini) │
                                  └────────────┬─────────────┘
                                               │ function_call
                                               ▼
                                  ┌──────────────────────────┐
                                  │  bridge_l1.py (WSL)      │
                                  │  - DefaultAzureCredential│
                                  │  - OAuth2 client_creds   │
                                  └────────────┬─────────────┘
                                               │ KQL
                                               ▼
                                  ┌──────────────────────────┐
                                  │  Log Analytics workspace │
                                  │  9e0a97a6-...d1c320      │
                                  └──────────────────────────┘
```

## Niveles de madurez

| Nivel | Qué demuestra | Estado |
|---|---|---|
| L0  | Modelo desplegado, agente con instrucciones, responde texto | ✅ Hecho |
| L1  | Agente con custom function tool, ciclo completo a Log Analytics | ✅ Hecho |
| L2.0 | Segunda tool: AWX como ejecutor (smoke test hello-world) | ✅ Hecho |
| L2.1 | Playbook real: snapshot del workspace (no invasivo, archivado en AWX) | ✅ Hecho |
| L2.2 | Adaptive Card a Teams con resumen del snapshot | ✅ Hecho |
| L2.3 | Errors-analysis + SOX audit + Brute-force detector + payroll-slow | ✅ Hecho |
| **L2.5** | **Dashboard web "Operations Console" con paleta Ecopetrol** | **✅ Hecho** |
| L3  | Disparador automático: alerta de App Insights → conversación | ⏳ Después |
| L3.5 | Acción invasiva real: restart container (requiere SP perms en Azure) | ⏳ Después |

## Dashboard web (L2.5) — TALENTO Operations Console

Frontend visual para presentar el agente a gerencia y cliente final.
Envuelve `bridge_l2.py` sin re-escribir su lógica. Identidad visual oficial de
Ecopetrol Colombia ([manual de identidad](https://saaeuecpprdpecp.blob.core.windows.net/web/esp/manual-de-identidad/)).

### Levantar el dashboard (con make)

```bash
# Demo real (toca Foundry/AWX/Teams)
make demo

# Modo desarrollo (uvicorn --reload, iteración rápida)
make dev

# Modo mock — eventos pregrabados, NO toca infra externa
make mock
```

Browser: <http://localhost:8000>

### Las 6 cards del dashboard

| Card | JT | Para qué |
|---|---|---|
| 📊 Estado del Sistema | 48 | Inventario amplio del workspace |
| 🚨 Errores en Producción | 49 | Detección ERROR/WARN críticos |
| 🔐 Auditoría SOX | 50 | Logins, acciones privilegiadas, incidentes BD |
| 🛡️ Detección de Brute Force | 51 | Failed logins por usuario sobre umbral |
| ⏱️ Lentitud Cierre Nómina | 49 (ventana 4h) | Errores tipicos de cierre de nómina |
| 🤖 Pregunta libre | varía | El agente decide qué tool usar |

Cada card lanza un ciclo que se reporta vía SSE: hops del agente, tool calls,
polling AWX, llegada de adaptive card a Teams, síntesis final estructurada.

### Operación con `make`

```bash
make help                # Lista todos los targets
make install             # Instala paquetes Python
make test                # Smoke tests (19 checks)
make pre-demo            # Checklist completo pre-demo
make awx-status          # Resumen ejecutivo de AWX
make awx-sync            # Re-sync project AWX desde Git
make cli Q=5             # Ejecuta bridge_l2 desde CLI (Q=1..5)
make inject-demo         # Inyecta failed logins sintéticos
make stop                # Mata proceso uvicorn
make clean               # Limpia __pycache__/
make repo-status         # Branch + commits pendientes
make rotate-secret-check # Recordatorio rotación de secrets
```

### Modo mock (`make mock`)

Reproduce eventos pregrabados con timings realistas. **NO toca** Foundry, AWX
ni Teams. Útil para:

- Ensayar la demo sin gastar tokens ni jobs reales.
- Demos en lugares sin conectividad estable.
- Fallback si Azure/AWX cae justo antes de la reunión.

Los 6 escenarios tienen mocks completos con artifacts realistas en
[webapp/mock_events.py](webapp/mock_events.py).

### Identidad visual Ecopetrol

Paleta oficial (manual público):

- **Primarios**: `#F7DB17` amarillo (Pantone 109C), `#CCD32A` verde lima (382C),
  `#004236` verde azulado oscuro (3308C — color institucional).
- **Complementarios**: `#00214D` azul marino, `#FF5F00` naranja, `#403833` marrón.
- **Tipografía**: **Verdana** (preferida según manual), Cambria para texto extenso.
- **Logo**: actualmente placeholder SVG en `webapp/static/img/logo-placeholder.svg`.
  Para producción, reemplazar con el SVG aprobado por Comunicaciones Ecopetrol
  (`catherine.villamil@ecopetrol.com.co`).

### Estructura del dashboard

```
webapp/
├── app.py              FastAPI + rutas (/, /api/scenarios, /api/run, /api/run/{id}/stream)
├── scenarios.py        Catálogo de 6 cards con prompts pre-canned
├── event_bus.py        asyncio.Queue thread-safe por run_id
├── bridge_runner.py    Wrapper que corre bridge_l2 en thread + filtra secrets
├── mock_events.py      Secuencias pregrabadas para ?mock=1 / FORCE_MOCK=1
├── templates/index.html
└── static/
    ├── css/ecp.css     Paleta Ecopetrol + componentes
    ├── js/ecp.js       EventSource + UI lifecycle
    ├── js/renderers.js 5 renderers (snapshot/errors/sox/brute-force/generic)
    └── img/logo-placeholder.svg
```

## Cómo correrlo (WSL Oracle Linux 9)

Prerequisitos validados en este entorno:
- Python 3.9.25
- `pip3 list`: `azure-ai-projects 2.1.0`, `azure-identity 1.25.3`, `openai 2.38.0`, `requests`
- `az` CLI instalado, `az login --use-device-code` ya ejecutado como usuario `ansible` (no sudo)
- `.env` en este directorio con: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID, LOG_ANALYTICS_WORKSPACE_ID, AWX_URL, AWX_TOKEN

### L1 (solo Log Analytics)

```bash
python3 bridge_l1.py        # pregunta 1 (default)
python3 bridge_l1.py 2      # pregunta 2
python3 bridge_l1.py 3      # pregunta 3
```

### L2 (Log Analytics + AWX)

```bash
python3 bridge_l2.py        # pregunta 1 (default) — usa ambas tools
python3 bridge_l2.py 2      # pregunta 2
python3 bridge_l2.py 3      # pregunta 3 — solo AWX smoke test
python3 bridge_l2.py --no-setup  # salta crear nueva versión del agente
```

Comandos:

```bash
cd /Ansible/pruebas_locales/talento-ecopetrol

# Pregunta 1 (errores) — default
python3 bridge_l1.py

# Pregunta 2 (Container Instances)
python3 bridge_l1.py 2

# Pregunta 3 (seguridad/riesgo)
python3 bridge_l1.py 3

# Pregunta libre
python3 bridge_l1.py "¿Cuántos AppRequests hubo en la última hora y cuál es la latencia P95?"

# Sin registrar nueva versión del agente (más rápido si ya está creada)
python3 bridge_l1.py --no-setup
```

## Estructura del proyecto

```
talento-ecopetrol/
├── README.md                       # este archivo
├── .env                            # credenciales (perm 600, no en git)
├── bridge_l1.py                    # demo principal — agente + function calling + LA
├── talento_log.yml                 # playbook: smoke test KQL contra LA
├── talento_listar_tablas.yml       # playbook: descubrimiento del workspace
├── docs/
│   └── demo-script.md              # guion para presentar a jefes
├── ai-foundry/                     # pendiente: docs propias del agente
├── playbooks/                      # pendiente: organización futura de playbooks
├── roles/                          # pendiente: role azure_auth reutilizable
└── group_vars/                     # pendiente: vars compartidas
```

## Limitaciones conocidas

### 1. Secrets visibles en `extra_vars` del job AWX

Por la arquitectura actual del demo, las credenciales Azure (`azure_tenant_id`,
`azure_client_id`, `azure_client_secret`, `log_analytics_workspace_id`) y la
URL del webhook Teams se pasan como `extra_vars` al lanzar el Job Template.
AWX **muestra esos `extra_vars` en claro** en la pestaña de detalle del job y
los persiste en su base de datos. Esto es **diseño de AWX**, no bug del demo.

**Mitigaciones activas hoy**:
- `no_log: true` en las tasks que consumen el secret (token OAuth2) → no aparecen
  en el `stdout` del job.
- Filtro anti-leak `_scrub()` en [webapp/bridge_runner.py](webapp/bridge_runner.py)
  → secrets no viajan a través del stream SSE al dashboard del browser.
- `.env` con permisos `600` + presente en `.gitignore`.

**Lo NO mitigable sin elevación de permisos**: el panel "Extra Variables" del job
detail en AWX UI. Solo lo ven quienes tienen lectura del AWX.

**Camino para producción**: el admin de AWX debe crear un **Custom Credential
Type** `talento-azure-sp` con los campos como `secret: true`, que inyecte
las variables al runner via env vars (no via extra_vars). El usuario actual
`admin_ecopetrol` (id=3) NO es superuser y por eso no puede crear ese
credential type. **Antes de pasar a producción esto es requisito**.

### 2. Resolución DNS intermitente desde el EE de AWX

Hosts externos (ej. `everisgroup.webhook.office.com`) ocasionalmente fallan
con `Errno -2 Name or service not known` desde el pod del Execution
Environment k3s. La task de notificación Teams en los 4 playbooks ahora
tiene `retries: 3, delay: 3, until: status in [200,202]` + `ignore_errors`
para tolerar este fallo intermitente sin romper el playbook completo.

Si persiste, el admin del cluster k3s debe revisar la configuración de DNS
del pod del EE (CoreDNS forwarders, `/etc/resolv.conf` del container, etc.).

## Recursos Azure usados (NTT DATA Colombia IS)

| Recurso | Identificador |
|---|---|
| Hub Foundry | `aifoundry-is2` (rg-central-is2) |
| Project Foundry | `proj-foundry-is2` |
| Endpoint Project | `https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2` |
| Modelo desplegado | `talento-gpt4o-mini` (Global Standard, version 2024-07-18) |
| Agente | `talento-triage-agent` (tipo: prompt) |
| Log Analytics workspace | `9e0a97a6-6839-4507-aae4-e4d706d1c320` |

## Documentación oficial de referencia

- [Deploy Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai)
- [Function calling con Foundry agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling)
- [Foundry Agent Service overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)
- [Azure Monitor Log Analytics REST API](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/overview)
# Talento
