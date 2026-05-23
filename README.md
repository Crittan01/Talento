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
| L2.1 | Playbook real: snapshot del workspace (no invasivo, archivado en AWX) | ⏳ Necesita repo Git |
| L2.2 | Playbook real: restart container + adaptive card Teams | ⏳ Necesita SP perms + webhook |
| L3  | Disparador automático: alerta de App Insights → conversación | ⏳ Después |

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
