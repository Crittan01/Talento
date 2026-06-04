---
name: talento-ecopetrol-rfp
description: Caso de uso talento-ecopetrol — RFP corporativo Ecopetrol con 3 casos técnicos donde el usuario debe entregar DEMOs en nube de pruebas para los frentes de observabilidad y automatización
metadata: 
  node_type: memory
  type: project
  originSessionId: 29bc6332-372a-456f-8211-b22061d864ec
---

Caso "talento-ecopetrol": el usuario está respondiendo (o apoyando la respuesta a) un RFP corporativo de Ecopetrol con 3 casos técnicos. Debe construir **DEMOs en una nube de pruebas** que respalden los planteamientos de los frentes de **observabilidad** y **automatización** mencionados en los documentos del RFP.

**Why:** Sustento de propuesta competitiva — las DEMOs apoyan la postura técnica que se presenta al cliente. El usuario pidió explícitamente que se hagan preguntas y se aterrice el alcance ANTES de generar cualquier propuesta de solución. No saltar a tecnologías sin haber unificado posturas.

**How to apply:** Antes de proponer arquitectura/tecnologías/PoC, validar: rol del usuario, naturaleza exacta del DEMO, audiencia, qué caso(s) técnico(s) cubre, ambos frentes o uno, restricciones de herramientas/cloud, tiempos. La pieza ya validada (playbook AWX → Azure Log Analytics en /Ansible/pruebas_locales/talento_log.yml) es building block directo de la pieza de observabilidad sobre Azure.

## Los 3 casos técnicos del RFP

**4.1 Administración, Operación y Soporte (máx 15 pág) — sistema TALENTO**
- Solución HR crítica, IaaS, 7x24, alta volumetría, regulada por SOX
- Stack heterogéneo: apps OnPremise (Win Svr 2019, Oracle 12c, NAS/SAN, server de licencias) + apps SaaS + app IaaS TALENTO
- Esquema de soporte multi-empresa: Asistia (mesa de ayuda), Soportica (N2), Talenia (N3, proveedor app), Infraxis (infra), Getalia (líder funcional)
- Problemas reportados: lentitud generalizada especialmente en cierres de nómina sin causa raíz clara, objetos no autorizados creados en BD OnPremise (usuarios con acceso directo a BD), vulnerabilidades en servidores de app y de licencias, obsolescencia de componentes críticos
- 10 entregables solicitados; los más alineados con los frentes son: **(5) Estrategia de monitoreo** y **(9) Estrategia de uso de IA para mejora continua**

**4.2 Ejecución de proyectos e iniciativas (máx 20 pág) — reconstrucción TALENTO**
- Proyecto aprobado para reconstruir TALENTO desde cero (UX moderna, alto rendimiento, SOX-compliant)
- Pide DOS planteamientos paralelos: marco Ágil y marco PMBOK/Tradicional
- Ambos cubren desde inception → go-live → operación → estabilización; deben incluir ejemplos, metodologías, documentos de diseño
- Menos directamente ligado a observabilidad/automatización pero puede tocar capacidades modernas (SRE, DevOps, CI/CD) que se demuestran con DEMOs

**4.3 Caso específico del segmento — EasyGO (máx 10 pág)**
- Solución microservicios en AKS de Azure
- Arquitectura: RG-AEU-ECP-{DEV,QA,PRD}-SHARED + RG-AEU-ECP-{DEV,QA,PRD}-EasyGO. Componentes: API Management, AKS (microservicios Notificaciones/Usuarios/EasyGO/...), Ingress + LoadBalancer, Azure Data Factory, SQL Managed Instance, Key Vault, Redis Cache, Storage Accounts, Cosmos DB, Container Registry, Pipelines
- Integraciones: SuccessFactors, SAP-FI (SAP Cloud), Sistema de Salud, Active Directory via REST + colas (EDA)
- Problemas: cambios directos en BD por fallos de orquestación, reinyección manual a SAP por mensajes perdidos en colas, reinicios de PODs sin autoescalado, probes readiness/liveness mal configuradas, fugas de memoria, lentitud en picos sin diagnóstico (contención, falta de caching, afinidad de PODs, saturación de nodos)
- 4 entregables; el más alineado es **(4) Propuesta de estrategia de monitoreo**. La pieza (1) Diagnóstico y (2)(3) Propuestas de solución/mejoras también pueden demostrarse con automatización

## Pieza de observabilidad ya validada

Playbook funcional en `/Ansible/pruebas_locales/talento_log.yml`: AWX → Azure AD (OAuth2 client_credentials) → Log Analytics workspace. Es la base de conectividad probada para la DEMO de observabilidad sobre Azure — encaja directo en 4.3 (EasyGO sobre Azure) y potencialmente en 4.1 si TALENTO publica logs hacia Azure Monitor.

## Restricciones / pistas conocidas

- Ubicación destino del proyecto: `/Ansible/pruebas_locales/talento-ecopetrol` (carpeta a crear cuando arranque la implementación)
- Cliente final del RFP: **Ecopetrol** (petrolera colombiana)
- Tenant Azure de la DEMO: **NTT DATA Colombia (IS)** — confirmado, es el ambiente donde se construye la DEMO completa
- Reglas técnicas del RFP exigen certificaciones (CMMI 3/4/5), alianzas (Microsoft Silver/Gold, Oracle Gold/Platinum) y prácticas de ciberincidentes

## Alcance y reparto definidos (sesión actual)

- **Caso a cubrir primero**: 4.1 TALENTO (admin/operación). Otros vendrán después.
- **Audiencia**: primero interna (equipo técnico + gerencial), luego cliente Ecopetrol.
- **Frentes en juego**: observabilidad + automatización + agentic AI, integrados.
- **Reparto multi-equipo**:
  - **EAPS**: construye y "rompe" una app demo simulando TALENTO (Static Web App + App Service B2 + Container Instances + SQL DB) con errores e incidentes inyectados.
  - **Compañero (observabilidad)**: monta la pieza de observabilidad sobre los logs/telemetría de la app demo.
  - **Usuario (automatización + agente)**: este es **mi foco** — debe construir la pieza de agente (Azure AI Foundry) + automatización (AWX sobre k3s) que consume las señales de observabilidad, analiza y ejecuta acciones.
- **Urgencia**: alta.

## Stack provisionado en Azure (NTT DATA IS) para la DEMO

| Capa | Servicio | SKU | RG | Dueño |
|---|---|---|---|---|
| App demo (simula TALENTO) | Azure Static Web App | Free/Standard | rg-central-solucion-talento | EAPS |
| App demo | Azure App Service | B2 Standard | rg-central-solucion-talento | EAPS |
| App demo | Azure Container Instances | 1 vCPU / 1.5 GB | rg-central-solucion-talento | EAPS |
| App demo | Azure SQL Database | Standard S2 | rg-central-solucion-talento | EAPS |
| Observabilidad | Application Insights | Basic | rg-central-solucion-talento | Compañero OBS |
| Observabilidad | Log Analytics Workspace | Free | rg-central-solucion-talento | Compañero OBS |
| Observabilidad complementaria | ELK | (en VM RH8 según contexto) | rg-central-obs-is | Compañero OBS |
| Automatización | AWX sobre k3s (VM) | Standard D2ds v4 | rg-is-demo-claro-eus-03 | **Usuario** |
| Observabilidad host (Linux) | VM Red Hat 8 | Standard D4as v5 | rg-central-obs-is | Compañero OBS |
| Agente IA | Server agentes IA (Azure AI Foundry) | — | rg-central-is2 | **Usuario** |

## L1 certificado (22-mayo-2026)

`bridge_l1.py` ejecuta el ciclo completo: pregunta → agente Foundry (`talento-triage-agent:2`) → function_call → KQL contra Log Analytics → resultado → síntesis. Validado contra el workspace real (`9e0a97a6-6839-4507-aae4-e4d706d1c320`). El modelo `gpt-4o-mini` se auto-corrige ante errores de schema si el bridge devuelve un `hint`. Decisiones técnicas que cuajaron:

- **Endpoint Foundry usado**: `https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2` (con `.services.`, no como dice la doc clásica — confirmado contra el portal del usuario).
- **Auth**: `DefaultAzureCredential` con `az login` del usuario (no sudo). Para Log Analytics seguimos usando el Service Principal del `.env` (camino validado en el playbook original).
- **Loop multi-hop obligatorio**: function calling necesita procesar items en bucle hasta que el modelo deje de pedir tools. Sin loop, respuesta vacía.
- **Tool registration solo vía SDK/REST**: el portal de Foundry no permite añadir custom function tools (doc lo dice literal). Por eso L1 necesitó Python.
- **Camino para AWX**: descartado openapi tool directo porque AWX está en HTTP. El Python bridge se convierte naturalmente en el bridge para AWX cuando entremos en L2.

**Dato relevante para el equipo**: el workspace de Log Analytics ya tiene tráfico real interesante — failed logins SQL del usuario `sqlserver-ecopetrol-admin` (error 18456). Confirmar con EAPS si es tráfico inyectado para la demo o residuo de otra prueba.

**Estado real del workspace (validado en runs)**: la app demo de EAPS aún no instrumenta Application Insights — `AppExceptions`, `AppRequests`, `AppTraces`, `AppDependencies` están vacías. Los datos viven en `ContainerInstanceLog_CL` (1467 eventos/24h) y `ContainerEvent_CL` (30 eventos/24h). Hallazgos detectados por el agente que sirven de narrativa al cliente: 10× "Authentication failed" en envío de correo del container `aci-centralecopetrol`, 6 BackOff de reinicio, 6 Terminating con exit code 1, errores de Hibernate `SQLStateConversionDelegate` apuntando a conectividad con BD Oracle.

**Patrón clave del system prompt** (iterado tras ver fallos en Q1/Q3): obligar al agente a hacer **descubrimiento como primer hop** con `union withsource=Tabla * | where TimeGenerated > ago(24h) | summarize count() by Tabla`. Sin este paso, el modelo asumía tablas (típicamente AppExceptions) y respondía "0 datos" cuando la verdadera fuente era otra. Con el descubrimiento, el agente se adapta dinámicamente al estado real del workspace.

## L2 certificado (22-mayo-2026)

`bridge_l2.py` extiende L1 con una segunda function tool: `run_awx_job_template(template_id)`. El agente ahora coordina dos tools: **diagnóstico** (Log Analytics) + **acción** (AWX). Validado contra AWX local del usuario:

- **AWX URL**: `https://192.168.250.20.nip.io/` (VM K3s local, cert nip.io — bridge usa `verify=False` por ahora)
- **Auth**: PAT en `.env` como `AWX_TOKEN`. Recordatorio: rotar tras demo (token expuesto en chat).
- **Recursos AWX bootstrapped vía API**:
  - Organization "Ecopetrol" (id=3, preexistente)
  - Inventory "Talento Inventory" (id=4) con localhost
  - Project `talento-automation-source` (id=46) — hoy apunta a `github.com/ansible/ansible-tower-samples` para bootstrap; se moverá al repo Git de talento-ecopetrol cuando el usuario lo cree
  - Job Template `talento-smoke-test` (id=47) — playbook `hello_world.yml`
  - Execution Environment AWX EE latest (id=3)
- **Test pasado**: agente recibe pregunta → query_log_analytics (descubrimiento) → run_awx_job_template(47) → respuesta sintetizada combinando ambos resultados, 23s total.

**L2.1 certificado**: snapshot real funcionando vía el agente. Repo Git: `github.com/Crittan01/Talento` branch `develop`. AWX project 46 apunta al repo con credencial SCM "PAT Eco" (id=4). Job Template `talento-workspace-snapshot` (id=48) ejecuta el playbook `playbooks/talento-workspace-snapshot.yml`. Agente lo invoca con extra_vars `{"time_range_hours": N}` y bridge inyecta automáticamente las credenciales Azure (workaround: `TEMPLATES_NEEDING_AZURE_CREDS={48}` en bridge_l2.py porque AWX no permite a non-superuser crear custom credential types).

**Lecciones aprendidas durante la construcción**:
- `community.general.dict` no estaba disponible en el EE — reescrito el playbook con filtros built-in (`first`, `length`, `default`). Lección: mantener playbooks portables con filtros estándar.
- GitHub Push Protection bloqueó el primer push porque `.env` con `AZURE_CLIENT_SECRET` estaba en el commit. Resuelto reescribiendo historia y limpiando reflog. **Usuario declinó rotar el secret (es demo)**, así que sigue expuesto en chat history + git reflog inicial.
- Usuario `admin_ecopetrol` (id=3) NO es superuser en AWX → no puede crear `credential_type`s. Para producción, alguien con superuser debe crear un custom credential type "talento-azure-readonly".

**Estado de la cuenta GitHub**: el secret de Azure (`njQ8Q~...l~cDv`) fue detectado por GitHub Secret Scanning en el primer intento. El evento queda registrado en su panel de Security aunque el commit nunca llegó al repo.

## L2.2 certificado (22-mayo-2026) — Teams Adaptive Card

El playbook `talento-workspace-snapshot.yml` ahora termina con una task que envía una **Adaptive Card al canal Teams** vía Incoming Webhook configurado en `TEAMS_WEBHOOK_URL` del `.env` y propagado al JT 48 vía extra_vars. La card incluye:

- Header verde (good) si hay tablas con datos, naranja (warning) si no.
- FactSet con: rango analizado, tablas pobladas, top tabla, filas, columnas del schema, muestra recuperada.
- Lista de tablas detectadas con sus counts.

Webhook URL pertenece a tenant `everisgroup.webhook.office.com` (NTT/everis). Recordatorio: rotable después del demo.

**Hallazgo durante el sample query**: la app TALENTO simulada por EAPS es una **app Spring Boot real** que está procesando lógica de HR — logs muestran: "Días disponibles recuperados para empleado 401005: 14", "Listando todos los días de cumpleaños", "Solicitud de login para usuario 'nvivas'", "Intentando aprobar día cumpleaños", "Validando días disponibles para incapacidad". Esto le da al demo una narrativa muy concreta y creíble.

**Pendiente para L2.3 (acción invasiva real — restart container)**: el SP `bbd498f7-...` sigue sin permisos sobre `aci-centralecopetrol`. Necesita rol `Container Instance Contributor` o equivalente. Hasta tener eso, L2 cierra en "diagnóstico + snapshot + notificación", no en remediación real.

## Segundo flujo agregado (22-mayo-2026) — Errors Analysis

JT 49 `talento-errors-analysis` añadido al catálogo. Es un segundo playbook no-invasivo, **focalizado en eventos críticos**, complementario al snapshot genérico:

- **Diferencia conceptual**: snapshot (JT 48) responde "qué hay en el workspace", errors-analysis (JT 49) responde "qué problemas tenemos".
- **KQL clave**: clasifica severidad por heurística (`Message contains " ERROR "`, etc.), produce top-5 mensajes y lista de containers afectados.
- **Salida**: `set_stats` con `total_errors`, `total_warnings`, `severity_status` (CRITICAL/WARN/OK), `top_messages`, `affected_containers`.
- **Adaptive card a Teams**: color `attention` (rojo) si hay errores, `warning` (naranja) si solo warnings, `good` (verde) si limpio.
- **Hallazgo en test**: 114 errores + 77 warnings en 24h, todos del container `aci-centralecopetrol`. Top mensajes son stack traces de Hibernate + SQL Server (los failed logins SQL ya conocidos).

**Validación importante del modelo**: ante la pregunta Q4 ("¿qué errores tenemos?"), el agente eligió correctamente JT 49 en lugar de JT 48. La descripción de los tools en el system prompt es suficientemente clara para que el modelo discrimine. Patrón replicable: cada nuevo Job Template solo necesita una buena descripción para integrarse al catálogo del agente — no requiere reentrenamiento ni cambios estructurales.

**Estado AWX actual**:
- JT 47 talento-smoke-test (hello world)
- JT 48 talento-workspace-snapshot (inventario + card verde/naranja)
- JT 49 talento-errors-analysis (eventos críticos + card roja/naranja/verde)
- JT 50 talento-sox-audit (auditoría SOX + card roja/naranja/verde)
- Total 5 playbooks en el repo (3 nuevos + 2 originales referenciados)

## Tercer flujo agregado (22-mayo-2026) — SOX Security Audit

JT 50 `talento-sox-audit` añadido. Cierra el catálogo del demo con la palabra-clave del RFP de Ecopetrol (SOX).

**Diferencia conceptual con los otros**:
- snapshot (48) responde "QUÉ" (qué hay en logs)
- errors-analysis (49) responde "QUÉ PROBLEMAS" (severidad)
- **sox-audit (50) responde "QUIÉN HIZO QUÉ"** (actores, acciones privilegiadas, incidentes BD)

**KQL clave**:
- Logins por usuario con `extract(@"usuario\s+'?([A-Za-z0-9._-]+)'?", 1, Message)` y clasificación SUCCESS/REQUEST/FAILURE
- Acciones privilegiadas detectando `rol=`, `Intentando aprobar/denegar`, `Listando todas`
- Incidentes seguridad BD: `Login failed for user`, `SQLServerException`, `Authentication failed`

**Hallazgos validados en producción del demo**:
- Usuario único auditado: `nvivas` (11 REQUEST + 11 SUCCESS en 24h)
- 27 acciones privilegiadas: 10 APROBAR con rol LIDER + 17 CONSULTA_MASIVA
- 40 incidentes de seguridad BD incluyendo failed logins de `sqlserver-ecopetrol-admin` con ClientConnectionId específicos (auditables)
- audit_status: SECURITY_INCIDENT (card roja)

**Bug encontrado y arreglado**: el patrón `time_range_hours: "{{ time_range_hours | default(24) }}"` causa recursion infinita si la var no viene de extra_vars. Fix aplicado en el bridge (no en el playbook): siempre inyecta `time_range_hours=24` por default cuando llama a JT 48/49/50, así el patrón funciona consistente.

## Catálogo final del demo (5 preguntas)

```
python3 bridge_l2.py 1  # Health check (LA + smoke test)
python3 bridge_l2.py 2  # Snapshot workspace via JT 48
python3 bridge_l2.py 3  # Solo AWX smoke test
python3 bridge_l2.py 4  # Errors analysis via JT 49
python3 bridge_l2.py 5  # SOX audit via JT 50  ← cierra con la keyword del RFP
```

**Patrón de extensibilidad confirmado**: cada nuevo flujo solo necesita (1) playbook en el repo, (2) JT en AWX vía API, (3) ~5 líneas en la descripción de tool del agente, (4) opcional: añadir al set `TEMPLATES_NEEDING_AZURE_CREDS`. El agente discrimina correctamente entre JTs basándose en la descripción.

## L2.5 certificado (23-mayo-2026) — Dashboard "Operations Console"

Dashboard FastAPI + SSE + Vanilla HTML/CSS/JS con identidad visual oficial Ecopetrol. Envuelve `bridge_l2.py` sin reescribir su lógica. Validado end-to-end real con 6 escenarios pre-canned + pregunta libre.

**Estructura**: `webapp/` (app.py + event_bus + bridge_runner + scenarios + mock_events + templates + static). Refactor mínimo de `bridge_l2.py`: `emit` callback opcional, cero regresión CLI.

**Tech stack** (todo ya instalado, cero deps nuevas): FastAPI + uvicorn + Jinja2 + Vanilla JS + EventSource (SSE). Streaming: thread-per-request + asyncio.Queue + call_soon_threadsafe.

**Paleta usada** (oficial): `#004236` verde institucional, `#F7DB17` amarillo, `#CCD32A` lima, Verdana. Logo placeholder hasta tener uno aprobado.

**Modo mock** (`FORCE_MOCK=1` o `?mock=1`): eventos pregrabados con timings realistas, NO toca Foundry/AWX/Teams. Safety net para demos críticos.

**Makefile** (14 targets): help, install, dev, demo, mock, cli Q=N, test, awx-sync, awx-status, inject-demo, stop, clean, repo-status, rotate-secret-check, pre-demo. `make test` corre 19 smoke checks.

**Nuevo JT en AWX**: `talento-brute-force-detector` (id=51). Detector enfocado de failed logins por usuario con umbral configurable. Severidad HIGH/MEDIUM/LOW. Card roja a Teams cuando HIGH.

**Bugs encontrados y corregidos durante validación final**:
1. `DefaultAzureCredential` capturaba el SP del `.env` (solo Log Analytics Reader) en vez del `az login` del usuario (con acceso a Foundry). Fix: `exclude_environment_credential=True` en `bridge_l2.py` y `webapp/bridge_runner.py`. Resultado: ahora el bridge usa la identidad del usuario, que SÍ tiene acceso a Foundry, aunque las env vars del SP estén cargadas.
2. `TEMPLATES_NEEDING_AZURE_CREDS = {48,49,50}` no incluía JT 51 → playbook fallaba con "Faltan azure_* vars". Fix: añadir 51 al set.
3. Tool description del agente no listaba JT 51 → el modelo elegía JT 49 (errors-analysis) por proximidad semántica. Fix: actualizar SYSTEM_INSTRUCTIONS y tool.description, re-registrar `talento-triage-agent:9`.

**Test E2E real final (job 381)**: dashboard → POST /api/run brute-force → SSE → agente decide JT 51 → AWX corre en 12.9s → severity=HIGH, total_db_failed=15 → adaptive card roja a Teams → agente sintetiza 1517 chars. Ciclo total 24.1s.

**Repo en GitHub** `Crittan01/Talento` branch `develop`: 11 commits, ~3100 líneas de código nuevo (sin contar refactors). Sin secrets en historia (gitignore + filtros anti-leak en SSE).

## Corrección importante (23-mayo-2026, posterior a L2.5)

Diagnostiqué erróneamente que el **Incoming Webhook de Teams estaba deprecated** porque devolvía HTTP 200 pero el usuario reportó "no llegan cards". **El webhook SÍ funciona** — el usuario confirmó con screenshot que la card del JT 51 llegó correctamente al canal con título "🛡️ TALENTO Brute Force Detector". Las cards de las 4 JTs (48, 49, 50, 51) llegan al canal sin problemas. Lección: cuando algo "no llega", validar primero enviando una card de control con timestamp visible y pedir confirmación visual al usuario antes de pivotar arquitectura.

**Filtros configurables agregados (paleta visible para gerencia)**: filter bar entre header y grid con time_range (1h–7d) y umbral brute-force (3–20). Backend: `resolve_prompt(scenario_id, filters)` sustituye placeholders Python `{time_range_hours}` y `{failed_threshold}` en los prompts del scenarios.py. Cards muestran badge "usa filtros: X+Y" cuando aplica y se resaltan en lima cuando los filtros no son default. Aplica a JT 48/49/50/51; no aplica a free-text.

**UI/UX mejoras visibles**: connection status pills (Foundry/AWX/Teams con dots verde/amarillo/rojo en header), timeline vertical con conectores y animaciones (shake en error, bounce en final), progress bar con shimmer durante AWX polling, empty state con icono flotante + loading dots, severity badges con animación scale-in. Todo dentro del manual de identidad Ecopetrol.

## Pendientes para L2.1+ (acciones invasivas) y L2.2 (Teams)

- **L2.1 — Restart container**: necesita el SP `bbd498f7-...` con rol `Contributor` (o `Container Instance Contributor`) sobre `aci-centralecopetrol` o sobre `rg-central-solucion-talento`. Tiene `Log Analytics Reader` actualmente — insuficiente para `az container restart`.
- **L2.2 — Adaptive cards Teams**: necesita Teams Incoming Webhook URL (o Workflows URL — Microsoft está migrando). Pendiente que el usuario lo cree y lo añada como `TEAMS_WEBHOOK_URL` en `.env`.
- **Repo Git para playbooks reales**: el snapshot playbook ya está escrito localmente; espera repo del usuario para subirse y reemplazar la fuente actual del project en AWX.

## Necesidad concreta del usuario (sesión actual)

Diseñar **escenarios end-to-end** donde un agente (Azure AI Foundry y/o flujos AWX) pueda:
1. Acceder a información relevante (logs / métricas — ya hay conectividad probada con Log Analytics vía OAuth2).
2. Analizar esa información (LLM razonando sobre la telemetría).
3. Tomar acciones (vía AWX playbooks o llamadas a APIs Azure).
4. Reportar/cerrar el ciclo.

Estos escenarios deben aterrizar la "necesidad total" del caso 4.1 — es decir, abordar visiblemente los pain points de TALENTO (lentitud en cierres, accesos no autorizados a BD, vulnerabilidades, obsolescencia, fallos de soporte multi-nivel).

**How to apply (sesión actual):** Antes de proponer escenarios concretos al usuario, validar que cada uno (a) tiene un pain point del RFP que justifica, (b) puede ser disparado por algo que EAPS realmente puede inyectar en la app demo (no asumir capacidades de simulación que no existen), (c) genera telemetría que el equipo de OBS puede capturar y exponer al agente, y (d) la acción final pasa por AWX o un tool de AI Foundry (sin saltarse a los demás equipos).
