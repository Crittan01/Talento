#!/usr/bin/env python3
"""
bridge_l2.py — DEMO L2 del proyecto talento-ecopetrol.

Extiende L1 (Foundry agent + Log Analytics) anadiendo una segunda tool:
run_awx_job_template, que permite al agente disparar playbooks en AWX para
acciones de remediacion o snapshots.

Ciclo demostrado:
  pregunta -> agente Foundry
            -> tool 1: query_log_analytics (diagnostico)
            -> tool 2: run_awx_job_template (accion via AWX)
            -> respuesta sintetizada

Uso:
  python3 bridge_l2.py                  # corre la pregunta default
  python3 bridge_l2.py 1|2|3            # preguntas predefinidas
  python3 bridge_l2.py "tu pregunta"    # libre
  python3 bridge_l2.py --no-setup       # salta create_version

Prereqs:
  - L1 prereqs: az login + paquetes Python + .env con credenciales Azure
  - Adicionales en .env: AWX_URL, AWX_TOKEN

Referencias oficiales:
  - Function calling Foundry:
    https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling
  - AWX REST API:
    https://ansible.readthedocs.io/projects/awx/en/latest/rest_api/api_ref.html
"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests
import os
import urllib3
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

# Suprime warning por el cert autofirmado del AWX nip.io local
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# Configuracion
# ============================================================================
PROJECT_ENDPOINT = "https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2"
MODEL_DEPLOYMENT = "talento-gpt4o-mini"

ENV_PATH = Path(__file__).parent / ".env"


# ============================================================================
# Carga del .env si existe (modo local). En Azure Function, leer de os.environ
# (Application Settings).
# ============================================================================
def load_env(path: Path) -> dict:
    """Carga vars del .env si existe (modo local) y las merge con os.environ.
    En Azure Function el .env no esta presente; todo viene de Application
    Settings, que viven en os.environ."""
    env = dict(os.environ)  # baseline: variables del entorno (Function settings)
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_PATH)


# ============================================================================
# Credencial Azure: detecta si estamos en Function (usa User Assigned MI) o
# en local (usa az login via DefaultAzureCredential).
# ============================================================================
def get_azure_credential():
    """Devuelve la credencial apropiada segun el entorno.

    - En Azure Function CON AZURE_MI_CLIENT_ID: User Assigned MI (con client_id).
    - En Azure Function SIN AZURE_MI_CLIENT_ID: System Assigned MI (default).
    - En local: az login del usuario.
    """
    in_function = bool(os.environ.get("FUNCTIONS_WORKER_RUNTIME"))
    if in_function:
        mi_client_id = os.environ.get("AZURE_MI_CLIENT_ID", "").strip()
        if mi_client_id:
            # User Assigned MI con client_id explicito
            return ManagedIdentityCredential(client_id=mi_client_id)
        # System Assigned MI (default cuando no se pasa client_id)
        return ManagedIdentityCredential()
    # Local dev
    return DefaultAzureCredential(exclude_environment_credential=True)


# ============================================================================
# Mapeo Job Templates (configurable via .env, cambia automaticamente al
# alternar entre AWX local y AWX Azure).
# ============================================================================
JT_IDS = {
    # Auditoria + analisis (los 4 originales)
    "jt_workspace_snapshot": int(ENV.get("AWX_JT_WORKSPACE_SNAPSHOT", 32)),
    "jt_errors_analysis":    int(ENV.get("AWX_JT_ERRORS_ANALYSIS", 33)),
    "jt_sox_audit":          int(ENV.get("AWX_JT_SOX_AUDIT", 34)),
    "jt_brute_force":        int(ENV.get("AWX_JT_BRUTE_FORCE", 35)),
    # Diagnosticos no invasivos (Azure ARM API)
    "jt_aci_state":          int(ENV.get("AWX_JT_ACI_STATE", 52)),
    "jt_appservice_state":   int(ENV.get("AWX_JT_APPSERVICE_STATE", 53)),
    "jt_sql_health":         int(ENV.get("AWX_JT_SQL_HEALTH", 54)),
    "jt_full_health_check":  int(ENV.get("AWX_JT_FULL_HEALTH_CHECK", 55)),
    # Remediaciones invasivas (dry_run=true por defecto a nivel playbook)
    "jt_aci_restart":        int(ENV.get("AWX_JT_ACI_RESTART", 56)),
    "jt_aci_stop":           int(ENV.get("AWX_JT_ACI_STOP", 57)),
    "jt_aci_start":          int(ENV.get("AWX_JT_ACI_START", 58)),
    "jt_appservice_restart": int(ENV.get("AWX_JT_APPSERVICE_RESTART", 59)),
}
TEMPLATES_NEEDING_AZURE_CREDS = set(JT_IDS.values())


def _agent_name_for_config() -> str:
    """AGENT_NAME derivado del hash de los JT IDs. Al cambiar de AWX cambia
    automaticamente el nombre, forzando un agente nuevo en Foundry con los
    instructions actuales (sin caching cross-config)."""
    ids = ",".join(str(v) for v in sorted(JT_IDS.values()))
    h = hashlib.sha256(ids.encode()).hexdigest()[:6]
    return f"talento-triage-agent-{h}"


AGENT_NAME = _agent_name_for_config()


DEMO_QUESTIONS = {
    "1": (
        "Realiza un health check operativo de TALENTO: primero diagnostica si "
        "hay errores recientes en el workspace, luego ejecuta el snapshot del "
        f"runtime de automatizacion AWX (template_id={JT_IDS['jt_workspace_snapshot']}) "
        "para verificar que tenemos via de diagnostico activa. Reporta los "
        "dos resultados."
    ),
    "2": (
        "Ejecuta un snapshot completo del workspace de TALENTO via el job "
        f"template AWX talento-workspace-snapshot (template_id={JT_IDS['jt_workspace_snapshot']}) "
        "con rango de 24 horas. Cuando termine, sintetiza los hallazgos del "
        "snapshot."
    ),
    "3": (
        f"Lanza el job template id {JT_IDS['jt_workspace_snapshot']} en AWX como prueba "
        "de cable agente <-> runtime de automatizacion. Reporta job_id, "
        "status y resumen del stdout."
    ),
    "4": (
        "¿Tenemos errores o warnings significativos en TALENTO en las "
        "ultimas 24 horas? Lanza el analisis especifico de errores via AWX "
        f"(template_id={JT_IDS['jt_errors_analysis']}) y sintetiza los hallazgos: "
        "cuantos eventos criticos, que containers estan afectados, y cuales "
        "son los top mensajes recurrentes. Indica el nivel de severidad global."
    ),
    "5": (
        "TALENTO es un sistema regulado por SOX. Necesito una auditoria de "
        "actividad de las ultimas 24 horas: que usuarios han accedido, que "
        "acciones privilegiadas se ejecutaron (aprobaciones, rol=LIDER, "
        "consultas masivas), y si hay incidentes de seguridad a nivel BD "
        f"(failed logins SQL, exceptions). Ejecuta el job template {JT_IDS['jt_sox_audit']} "
        "(talento-sox-audit) y reporta los hallazgos con el audit_status."
    ),
}

DEFAULT_QUESTION_KEY = "1"


# ============================================================================
# Emit helper — para webapp/SSE, no afecta CLI
# ============================================================================
def _emit(emit: Optional[Callable[[dict], None]], event: dict) -> None:
    """Llama emit(event) si esta definido. No-op si emit is None (modo CLI)."""
    if emit is not None:
        try:
            emit(event)
        except Exception:
            # No bloqueamos el bridge por fallo del emit (e.g., queue cerrada)
            pass


# ============================================================================
# Tool 1: Log Analytics (heredado de L1)
# ============================================================================
def get_la_token() -> str:
    resp = requests.post(
        f"https://login.microsoftonline.com/{ENV['AZURE_TENANT_ID']}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": ENV["AZURE_CLIENT_ID"],
            "client_secret": ENV["AZURE_CLIENT_SECRET"],
            "resource": "https://api.loganalytics.io",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def execute_kql(query: str) -> dict:
    if "| take " not in query.lower() and "| top " not in query.lower():
        query = query.rstrip() + " | take 100"
    token = get_la_token()
    resp = requests.post(
        f"https://api.loganalytics.azure.com/v1/workspaces/{ENV['LOG_ANALYTICS_WORKSPACE_ID']}/query",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=60,
    )
    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:2000]}
        return {
            "error": f"HTTP {resp.status_code}",
            "details": body,
            "query_used": query,
            "hint": "Si SemanticError, ejecuta '<tabla> | getschema' primero.",
        }
    data = resp.json()
    if not data.get("tables") or not data["tables"][0].get("rows"):
        return {"rows": 0, "data": [], "query_used": query}
    table = data["tables"][0]
    columns = [c["name"] for c in table["columns"]]
    rows = [dict(zip(columns, row)) for row in table["rows"]]
    return {"rows": len(rows), "columns": columns, "data": rows, "query_used": query}


# ============================================================================
# Tool 2: AWX Job Template
# ============================================================================
def run_awx_job_template(
    template_id: int,
    extra_vars: dict = None,
    emit: Optional[Callable[[dict], None]] = None,
    force_extra_vars: dict = None,
) -> dict:
    """Lanza un job template en AWX, polea hasta completar, devuelve resultado.
    Inyecta automaticamente las Azure creds como extra_vars si el template
    las requiere (ver TEMPLATES_NEEDING_AZURE_CREDS).
    force_extra_vars: dict de valores que SOBRESCRIBEN lo que el LLM paso.
    Util para que la UI (filtros del usuario) sea la fuente de verdad sin
    depender de que el modelo respete el prompt al pie de la letra.
    Si emit esta definido, emite eventos de polling para SSE."""
    base = ENV["AWX_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {ENV['AWX_TOKEN']}"}
    extra_vars = dict(extra_vars or {})

    # Sobrescribir lo que el LLM paso con los valores forzados (filtros UI)
    if force_extra_vars:
        extra_vars.update(force_extra_vars)

    # Inyectar creds Azure si el JT lo requiere (workaround por falta de
    # superuser en AWX que impide crear custom credential types)
    if template_id in TEMPLATES_NEEDING_AZURE_CREDS:
        extra_vars.setdefault("azure_tenant_id", ENV.get("AZURE_TENANT_ID", ""))
        extra_vars.setdefault("azure_client_id", ENV.get("AZURE_CLIENT_ID", ""))
        extra_vars.setdefault("azure_client_secret", ENV.get("AZURE_CLIENT_SECRET", ""))
        # subscription_id necesario para los JTs ARM (aci-*, appservice-*, sql-*)
        extra_vars.setdefault("azure_subscription_id", ENV.get("AZURE_SUBSCRIPTION_ID", ""))
        extra_vars.setdefault("log_analytics_workspace_id", ENV.get("LOG_ANALYTICS_WORKSPACE_ID", ""))
        # Default time_range si NI el LLM NI force_extra_vars lo trajeron
        extra_vars.setdefault("time_range_hours", 24)
        # Teams webhook para adaptive card al final del playbook (opcional)
        if ENV.get("TEAMS_WEBHOOK_URL"):
            extra_vars.setdefault("teams_webhook_url", ENV["TEAMS_WEBHOOK_URL"])

    # Launch
    launch_resp = requests.post(
        f"{base}/api/v2/job_templates/{template_id}/launch/",
        headers={**headers, "Content-Type": "application/json"},
        json={"extra_vars": extra_vars},
        verify=False,
        timeout=30,
    )
    if launch_resp.status_code not in (200, 201, 202):
        return {
            "error": f"Launch fallo: HTTP {launch_resp.status_code}",
            "details": launch_resp.text[:500],
            "template_id": template_id,
        }
    launched = launch_resp.json()
    job_id = launched.get("id") or launched.get("job")
    if not job_id:
        return {"error": "Sin job_id en respuesta del launch", "details": launched}

    awx_url = f"{base}/#/jobs/playbook/{job_id}"
    _emit(emit, {
        "type": "tool.awx.launched",
        "template_id": template_id,
        "job_id": job_id,
        "awx_url": awx_url,
    })

    # Poll status (max ~120s)
    final_job = None
    poll_start = time.time()
    for attempt in range(40):
        time.sleep(3)
        s = requests.get(
            f"{base}/api/v2/jobs/{job_id}/",
            headers=headers,
            verify=False,
            timeout=30,
        )
        if s.status_code != 200:
            continue
        job = s.json()
        elapsed_polling = time.time() - poll_start
        _emit(emit, {
            "type": "tool.awx.polling",
            "job_id": job_id,
            "status": job.get("status"),
            "elapsed_seconds": round(elapsed_polling, 1),
        })
        if job["status"] in ("successful", "failed", "error", "canceled"):
            final_job = job
            break
    if final_job is None:
        _emit(emit, {"type": "tool.awx.timeout", "job_id": job_id})
        return {"error": "Timeout (~120s) esperando job", "job_id": job_id}

    # Stdout (tail)
    so = requests.get(
        f"{base}/api/v2/jobs/{job_id}/stdout/?format=txt",
        headers=headers,
        verify=False,
        timeout=30,
    )
    stdout = so.text if so.status_code == 200 else "[stdout no disponible]"

    return {
        "job_id": job_id,
        "status": final_job["status"],
        "elapsed_seconds": final_job.get("elapsed"),
        "started": final_job.get("started"),
        "finished": final_job.get("finished"),
        "artifacts": final_job.get("artifacts", {}),
        "stdout_tail": stdout[-2000:],
        "awx_url": f"{base}/#/jobs/playbook/{job_id}",
    }


# ============================================================================
# Setup del agente — 2 tools registradas
# ============================================================================
def build_system_instructions() -> str:
    """Construye las instrucciones del agente con los JT IDs activos
    (leidos de .env). Llamar en cada create_version() para que Foundry
    reciba siempre los IDs vigentes."""
    j = JT_IDS
    return (
        "Eres un asistente experto en analisis y remediacion de incidentes IT, "
        "especializado en la solucion corporativa TALENTO: sistema de gestion de "
        "talento humano, IaaS, operacion 7x24, regulado por SOX. Componentes en "
        "Azure (App Service, Azure SQL, Container Instances, Application Insights, "
        "Log Analytics) y aplicaciones OnPremise (Windows Server 2019, Oracle 12c, "
        "NAS/SAN).\n\n"
        "Tienes DOS tools:\n\n"
        "1. query_log_analytics(query): consulta KQL contra el workspace de Log "
        "   Analytics. Para DIAGNOSTICO y verificacion de estado.\n\n"
        "2. run_awx_job_template(template_id, extra_vars_json): ejecuta un job "
        "   template en AWX. Templates disponibles agrupados por proposito:\n\n"
        "   === ANALISIS DE LOGS (no invasivos) ===\n"
        f"   - id={j['jt_workspace_snapshot']} talento-workspace-snapshot: inventario amplio "
        "     (tablas + schema + muestra). Para 'que hay en los logs'.\n"
        f"   - id={j['jt_errors_analysis']} talento-errors-analysis: ERROR/WARN agrupados, "
        "     top mensajes, containers afectados. Para 'que problemas tenemos'.\n"
        f"   - id={j['jt_sox_audit']} talento-sox-audit: SOX/seguridad — logins por usuario, "
        "     acciones privilegiadas, incidentes BD. Devuelve audit_status.\n"
        f"   - id={j['jt_brute_force']} talento-brute-force-detector: failed logins agrupados "
        "     por usuario con umbral. extra_vars: failed_threshold, time_range_hours.\n\n"
        "   === DIAGNOSTICO DE INFRAESTRUCTURA (no invasivos, leen ARM API) ===\n"
        f"   - id={j['jt_aci_state']} talento-aci-state: estado actual del Container Instance "
        "     (Running/Terminated/...), restartCount, eventos. Para 'esta vivo?'.\n"
        f"   - id={j['jt_appservice_state']} talento-appservice-state: estado del App Service "
        "     (Running/Stopped), availability, host. Para 'la API responde?'.\n"
        f"   - id={j['jt_sql_health']} talento-sql-health: estado SQL Server + DBs (Online/...), "
        "     tier. Para 'la BD esta sana?'.\n"
        f"   - id={j['jt_full_health_check']} talento-full-health-check: orchestrator de los 3 "
        "     anteriores. Devuelve overall_severity HEALTHY/DEGRADED/CRITICAL + "
        "     recomendacion. Usalo cuando el usuario pida 'health check completo'.\n\n"
        "   === REMEDIACION (INVASIVOS — dry_run=true por defecto) ===\n"
        f"   - id={j['jt_aci_restart']} talento-aci-restart: reinicia el container.\n"
        f"   - id={j['jt_aci_stop']} talento-aci-stop: detiene el container.\n"
        f"   - id={j['jt_aci_start']} talento-aci-start: inicia el container.\n"
        f"   - id={j['jt_appservice_restart']} talento-appservice-restart: reinicia App Service.\n"
        "     IMPORTANTE: para los 4 invasivos, en dry_run NO se ejecuta nada (solo "
        "     simula). Para ejecutar de verdad pasar extra_vars_json='{\"dry_run\": false}'. "
        "     SIEMPRE explica al usuario que estas en dry-run y pide confirmacion antes "
        "     de ejecutar real.\n\n"
        "PROTOCOLO:\n"
        "A) Para preguntas operativas: primero descubrimiento KQL si aplica.\n"
        "B) Si el usuario pide 'estado/salud': usa los JTs de diagnostico (52-55). "
        "   Prefiere full-health-check si el alcance es amplio.\n"
        "C) Si el usuario pide remediacion (restart/stop/start): primero diagnostica, "
        "   luego propon la accion en dry-run. NUNCA ejecutes real sin confirmacion.\n"
        "D) Tras una accion AWX, verifica con query_log_analytics si los datos "
        "   reflejan el cambio (cuando aplique).\n\n"
        "RESPUESTA FINAL siempre en espanol, estructurada:\n"
        "- Hallazgo (datos concretos)\n"
        "- Hipotesis (1-3 ordenadas por probabilidad)\n"
        "- Pasos de diagnostico (que validar)\n"
        "- Accion correctiva (que se hizo / que hacer)\n\n"
        "Tecnico, conciso. No inventes datos. Si una tool falla, lee el hint y "
        "reintenta."
    )

TOOL_QUERY_LA = FunctionTool(
    name="query_log_analytics",
    description=(
        "Ejecuta una consulta KQL contra el workspace de Log Analytics de "
        "TALENTO. Usala para diagnostico, descubrimiento de tablas pobladas, "
        "y verificacion de estado tras una accion. Primer hop SIEMPRE: "
        "descubrimiento con 'union withsource=Tabla *'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "KQL valida. Tablas conocidas: ContainerInstanceLog_CL, "
                    "ContainerEvent_CL (con datos), AppExceptions/AppRequests/"
                    "AppTraces/AppDependencies (pueden estar vacias). "
                    "Descubre primero, luego getschema, luego query final."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)

def build_tool_run_awx() -> FunctionTool:
    """Tool spec con descripcion construida con los JT IDs activos."""
    j = JT_IDS
    return FunctionTool(
        name="run_awx_job_template",
        description=(
            "Lanza un Job Template en AWX y espera a que termine. Usala para "
            "EJECUTAR acciones operativas: analisis de logs, diagnostico de "
            "infraestructura, o remediaciones (restart/stop/start). Devuelve "
            "job_id, status, elapsed_seconds, stdout_tail y artifacts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "integer",
                    "description": (
                        "ID del job template. Categorias:\n"
                        "Analisis logs: "
                        f"{j['jt_workspace_snapshot']} (workspace-snapshot), "
                        f"{j['jt_errors_analysis']} (errors-analysis), "
                        f"{j['jt_sox_audit']} (sox-audit), "
                        f"{j['jt_brute_force']} (brute-force-detector). "
                        "Diagnostico infra: "
                        f"{j['jt_aci_state']} (aci-state), "
                        f"{j['jt_appservice_state']} (appservice-state), "
                        f"{j['jt_sql_health']} (sql-health), "
                        f"{j['jt_full_health_check']} (full-health-check). "
                        "Remediacion (dry_run=true por defecto): "
                        f"{j['jt_aci_restart']} (aci-restart), "
                        f"{j['jt_aci_stop']} (aci-stop), "
                        f"{j['jt_aci_start']} (aci-start), "
                        f"{j['jt_appservice_restart']} (appservice-restart)."
                    ),
                },
                "extra_vars_json": {
                    "type": "string",
                    "description": (
                        "JSON string con variables extra opcionales. Ejemplos:\n"
                        f"- Para analisis logs (template {j['jt_workspace_snapshot']}-{j['jt_brute_force']}): "
                        "'{\"time_range_hours\": 12}'.\n"
                        f"- Para diagnostico infra ({j['jt_aci_state']}-{j['jt_full_health_check']}): '{{}}' suele bastar.\n"
                        f"- Para remediacion ({j['jt_aci_restart']}-{j['jt_appservice_restart']}): "
                        "'{\"dry_run\": false}' para ejecutar de verdad (sin esa flag NO ejecuta). "
                        "Tambien acepta '{\"reason\": \"texto descriptivo\"}'.\n"
                        "NO incluyas credenciales — el bridge las inyecta solo."
                    ),
                },
            },
            "required": ["template_id", "extra_vars_json"],
            "additionalProperties": False,
        },
        strict=True,
    )


def setup_agent_version(project: AIProjectClient):
    return project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT,
            instructions=build_system_instructions(),
            tools=[TOOL_QUERY_LA, build_tool_run_awx()],
        ),
    )


# ============================================================================
# Procesamiento de respuestas (multi-hop)
# ============================================================================
def process_response_items(
    response,
    hop: int,
    emit: Optional[Callable[[dict], None]] = None,
    force_extra_vars: dict = None,
):
    text_chunks = []
    fn_outputs = []
    for item in response.output:
        itype = getattr(item, "type", None)
        if itype == "function_call":
            args = json.loads(item.arguments)
            print(f"\n  🤖 hop {hop} → llama tool: {item.name}")
            if item.name == "query_log_analytics":
                kql = args.get("query", "")
                print(f"     KQL: {kql}")
                _emit(emit, {
                    "type": "tool.call",
                    "hop": hop,
                    "tool": "query_log_analytics",
                    "args": {"query": kql},
                })
                t0 = time.time()
                result = execute_kql(args["query"])
                elapsed = time.time() - t0
                if "error" in result:
                    print(f"     ⚠️  KQL ERROR ({elapsed:.1f}s): {result['error']}")
                    _emit(emit, {
                        "type": "tool.kql.error",
                        "hop": hop,
                        "error": result.get("error"),
                        "elapsed_seconds": round(elapsed, 1),
                    })
                else:
                    print(f"     ✓ KQL OK ({elapsed:.1f}s): {result['rows']} filas")
                    _emit(emit, {
                        "type": "tool.kql.done",
                        "hop": hop,
                        "rows": result.get("rows", 0),
                        "elapsed_seconds": round(elapsed, 1),
                    })
                fn_outputs.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                })
            elif item.name == "run_awx_job_template":
                tpl = args.get("template_id")
                # extra_vars_json viene como string JSON desde el agente
                ev_raw = args.get("extra_vars_json", "{}")
                try:
                    ev = json.loads(ev_raw) if ev_raw and ev_raw.strip() else {}
                except json.JSONDecodeError:
                    ev = {}
                # Si hay filtros forzados del usuario, anunciarlo en el log
                # para que sea visible en el timeline
                effective_ev = dict(ev)
                if force_extra_vars:
                    effective_ev.update(force_extra_vars)
                print(f"     AWX template_id={tpl}  extra_vars(efectivo)={effective_ev}")
                _emit(emit, {
                    "type": "tool.call",
                    "hop": hop,
                    "tool": "run_awx_job_template",
                    "args": {"template_id": tpl, "extra_vars": effective_ev},
                })
                t0 = time.time()
                result = run_awx_job_template(
                    tpl, extra_vars=ev, emit=emit, force_extra_vars=force_extra_vars,
                )
                elapsed = time.time() - t0
                if "error" in result:
                    print(f"     ⚠️  AWX ERROR ({elapsed:.1f}s): {result['error']}")
                    _emit(emit, {
                        "type": "tool.awx.error",
                        "hop": hop,
                        "error": result.get("error"),
                        "elapsed_seconds": round(elapsed, 1),
                    })
                else:
                    print(f"     ✓ AWX {result['status']} en {result.get('elapsed_seconds','?')}s")
                    print(f"       job_id={result['job_id']}  ({result.get('awx_url','')})")
                    _emit(emit, {
                        "type": "tool.awx.done",
                        "hop": hop,
                        "job_id": result.get("job_id"),
                        "status": result.get("status"),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "awx_url": result.get("awx_url"),
                        "artifacts": result.get("artifacts", {}),
                    })
                fn_outputs.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                })
        elif itype == "message":
            content = getattr(item, "content", None)
            if content:
                for c in content:
                    text_val = getattr(c, "text", None)
                    if text_val:
                        text_chunks.append(text_val)
    return "\n".join(text_chunks), fn_outputs


def run_cycle(
    project,
    agent_name,
    user_question,
    max_hops=8,
    emit: Optional[Callable[[dict], None]] = None,
    force_extra_vars: dict = None,
):
    openai_client = project.get_openai_client()
    conversation = openai_client.conversations.create()

    print(f"\n  👤 Usuario: {user_question}")
    _emit(emit, {
        "type": "agent.received",
        "question": user_question,
        "agent": agent_name,
        "max_hops": max_hops,
    })
    t_total = time.time()

    response = openai_client.responses.create(
        input=user_question,
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
    )

    final_text = ""
    for hop in range(1, max_hops + 1):
        _emit(emit, {"type": "agent.hop", "hop": hop})
        text, fn_outputs = process_response_items(
            response, hop, emit=emit, force_extra_vars=force_extra_vars,
        )
        if text:
            final_text = text
        if not fn_outputs:
            break
        response = openai_client.responses.create(
            input=fn_outputs,
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        )
    else:
        print(f"\n  ⚠️  Limite de {max_hops} hops alcanzado.")
        _emit(emit, {"type": "agent.hop_limit", "max_hops": max_hops})

    if not final_text:
        final_text = getattr(response, "output_text", "") or "[sin respuesta de texto]"

    elapsed = time.time() - t_total
    print("\n" + "═" * 78)
    print("  🤖 RESPUESTA FINAL DEL AGENTE")
    print("═" * 78)
    print(final_text)
    print("═" * 78)
    print(f"  ⏱  Tiempo total: {elapsed:.1f}s")
    _emit(emit, {
        "type": "agent.final",
        "text": final_text,
        "elapsed_seconds": round(elapsed, 1),
    })
    _emit(emit, {"type": "done"})


# ============================================================================
# Entry point
# ============================================================================
def parse_args():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    no_setup = "--no-setup" in flags
    if not args:
        question = DEMO_QUESTIONS[DEFAULT_QUESTION_KEY]
    elif args[0] in DEMO_QUESTIONS:
        question = DEMO_QUESTIONS[args[0]]
    else:
        question = " ".join(args)
    return question, no_setup


def main():
    question, no_setup = parse_args()

    print("┌" + "─" * 76 + "┐")
    print("│  bridge_l2.py — DEMO L2 talento-ecopetrol" + " " * 34 + "│")
    print("│  Tools: query_log_analytics + run_awx_job_template" + " " * 25 + "│")
    print("└" + "─" * 76 + "┘")

    print("\n► Conectando a Foundry...")
    # get_azure_credential() auto-selecciona: User Assigned MI en Function,
    # az login en local. Ver definicion arriba.
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=get_azure_credential(),
    )

    agent_name = AGENT_NAME
    if not no_setup:
        print("► Registrando 2 tools en nueva version del agente...")
        agent = setup_agent_version(project)
        print(f"  ✓ Version activa: {agent.name}:{agent.version}")
        agent_name = agent.name
    else:
        print("► (--no-setup) Usando ultima version existente del agente")

    print("\n► Iniciando ciclo conversacional...")
    run_cycle(project, agent_name, question)


if __name__ == "__main__":
    main()
