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

import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests
import urllib3
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

# Suprime warning por el cert autofirmado del AWX nip.io local
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# Configuracion
# ============================================================================
PROJECT_ENDPOINT = "https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2"
MODEL_DEPLOYMENT = "talento-gpt4o-mini"
AGENT_NAME = "talento-triage-agent"

ENV_PATH = Path(__file__).parent / ".env"

DEMO_QUESTIONS = {
    "1": (
        "Realiza un health check operativo de TALENTO: primero diagnostica si "
        "hay errores recientes en el workspace, luego ejecuta el smoke test "
        "del runtime de automatizacion AWX (template_id=47) para verificar "
        "que tenemos via de remediacion disponible. Reporta los dos resultados."
    ),
    "2": (
        "Ejecuta un snapshot completo del workspace de TALENTO via el job "
        "template AWX talento-workspace-snapshot (template_id=48) con rango "
        "de 24 horas. Cuando termine, sintetiza los hallazgos del snapshot."
    ),
    "3": (
        "Lanza el job template id 47 en AWX como prueba de cable agente <-> "
        "runtime de automatizacion. Reporta job_id, status y resumen del "
        "stdout."
    ),
    "4": (
        "¿Tenemos errores o warnings significativos en TALENTO en las "
        "ultimas 24 horas? Lanza el analisis especifico de errores via AWX "
        "(template_id=49) y sintetiza los hallazgos: cuantos eventos "
        "criticos, que containers estan afectados, y cuales son los top "
        "mensajes recurrentes. Indica el nivel de severidad global."
    ),
    "5": (
        "TALENTO es un sistema regulado por SOX. Necesito una auditoria de "
        "actividad de las ultimas 24 horas: que usuarios han accedido, que "
        "acciones privilegiadas se ejecutaron (aprobaciones, rol=LIDER, "
        "consultas masivas), y si hay incidentes de seguridad a nivel BD "
        "(failed logins SQL, exceptions). Ejecuta el job template 50 "
        "(talento-sox-audit) y reporta los hallazgos con el audit_status."
    ),
}

# Templates AWX que requieren credenciales Azure inyectadas como extra_vars
# (porque AWX no nos deja crear custom credential types sin superuser).
# 48 = talento-workspace-snapshot
# 49 = talento-errors-analysis
# 50 = talento-sox-audit
# 51 = talento-brute-force-detector
TEMPLATES_NEEDING_AZURE_CREDS = {48, 49, 50, 51}
DEFAULT_QUESTION_KEY = "1"


# ============================================================================
# Carga del .env
# ============================================================================
def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_PATH)


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
) -> dict:
    """Lanza un job template en AWX, polea hasta completar, devuelve resultado.
    Inyecta automaticamente las Azure creds como extra_vars si el template
    las requiere (ver TEMPLATES_NEEDING_AZURE_CREDS).
    Si emit esta definido, emite eventos de polling para SSE."""
    base = ENV["AWX_URL"].rstrip("/")
    headers = {"Authorization": f"Bearer {ENV['AWX_TOKEN']}"}
    extra_vars = dict(extra_vars or {})

    # Inyectar creds Azure si el JT lo requiere (workaround por falta de
    # superuser en AWX que impide crear custom credential types)
    if template_id in TEMPLATES_NEEDING_AZURE_CREDS:
        extra_vars.setdefault("azure_tenant_id", ENV.get("AZURE_TENANT_ID", ""))
        extra_vars.setdefault("azure_client_id", ENV.get("AZURE_CLIENT_ID", ""))
        extra_vars.setdefault("azure_client_secret", ENV.get("AZURE_CLIENT_SECRET", ""))
        extra_vars.setdefault("log_analytics_workspace_id", ENV.get("LOG_ANALYTICS_WORKSPACE_ID", ""))
        # Default time_range si el agente no lo pasa (evita recursion en defaults Jinja)
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
SYSTEM_INSTRUCTIONS = (
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
    "   template en AWX. Para ACCIONES operativas. Templates HOY:\n"
    "   - id=47 talento-smoke-test (hello world, sin efecto real)\n"
    "   - id=48 talento-workspace-snapshot (inventario amplio: tablas + "
    "     schema + muestra. Para 'que hay en los logs').\n"
    "   - id=49 talento-errors-analysis (FOCO en ERROR/WARN: severidad, top "
    "     mensajes, containers afectados. Para 'que problemas tenemos').\n"
    "   - id=50 talento-sox-audit (FOCO en SOX/seguridad: logins por usuario, "
    "     acciones privilegiadas con rol, incidentes de seguridad a nivel BD. "
    "     Para 'auditoria de accesos', 'quien hizo que', 'cumplimiento SOX', "
    "     'actividad sospechosa'). Devuelve audit_status SECURITY_INCIDENT/"
    "     AUDIT_REVIEW/NORMAL.\n"
    "   - id=51 talento-brute-force-detector (FOCO en patrones de brute "
    "     force: failed logins agrupados por usuario con umbral. Para "
    "     'detectar brute force', 'intentos de login fallidos', 'ataques de "
    "     fuerza bruta'). Devuelve bruteforce_severity HIGH/MEDIUM/LOW. "
    "     extra_vars opcionales: {\"time_range_hours\": <int>, "
    "     \"failed_threshold\": <int>}.\n"
    "   Todos los JTs 48, 49, 50 y 51 envian adaptive card a Teams "
    "   automaticamente (color segun severidad).\n"
    "   extra_vars opcional para 48/49/50/51: {\"time_range_hours\": <int>} "
    "   default 24.\n\n"
    "PROTOCOLO:\n"
    "A) Para preguntas operativas: primero descubrimiento con "
    "   'union withsource=Tabla * | where TimeGenerated > ago(24h) | "
    "   summarize count() by Tabla | order by count_ desc'.\n"
    "B) Si necesitas el esquema de una tabla, '<tabla> | getschema' antes de "
    "   queries complejas.\n"
    "C) Si el usuario pide ejecutar una accion o validar el runtime de "
    "   automatizacion, usa run_awx_job_template con el template_id apropiado.\n"
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

TOOL_RUN_AWX = FunctionTool(
    name="run_awx_job_template",
    description=(
        "Lanza un Job Template en AWX y espera a que termine. Usala para "
        "EJECUTAR acciones operativas: smoke tests, snapshots, remediaciones. "
        "Devuelve job_id, status, elapsed_seconds, stdout_tail y artifacts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "integer",
                "description": (
                    "ID del job template. Disponibles: "
                    "47 (talento-smoke-test, hello world), "
                    "48 (talento-workspace-snapshot, inventario amplio), "
                    "49 (talento-errors-analysis, foco en ERROR/WARN), "
                    "50 (talento-sox-audit, foco en SOX/accesos/auditoria), "
                    "51 (talento-brute-force-detector, foco en intentos de login fallidos)."
                ),
            },
            "extra_vars_json": {
                "type": "string",
                "description": (
                    "JSON string con variables extra opcionales. Para template "
                    "48 puedes pasar '{\"time_range_hours\": 12}'. Si no aplica "
                    "envia '{}'. NO incluyas credenciales aqui — el bridge las "
                    "inyecta solo."
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
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[TOOL_QUERY_LA, TOOL_RUN_AWX],
        ),
    )


# ============================================================================
# Procesamiento de respuestas (multi-hop)
# ============================================================================
def process_response_items(
    response,
    hop: int,
    emit: Optional[Callable[[dict], None]] = None,
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
                print(f"     AWX template_id={tpl}  extra_vars={ev}")
                _emit(emit, {
                    "type": "tool.call",
                    "hop": hop,
                    "tool": "run_awx_job_template",
                    "args": {"template_id": tpl, "extra_vars": ev},
                })
                t0 = time.time()
                result = run_awx_job_template(tpl, extra_vars=ev, emit=emit)
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
        text, fn_outputs = process_response_items(response, hop, emit=emit)
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
    # Importante: exclude_environment_credential=True fuerza a usar el az login
    # del usuario. Si no se excluye, DefaultAzureCredential toma las vars
    # AZURE_CLIENT_ID/SECRET/TENANT_ID del .env y las usa como SP — pero ese
    # SP solo tiene rol Log Analytics Reader, no tiene acceso a Foundry. El
    # usuario que hizo `az login` SÍ tiene acceso a Foundry.
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(exclude_environment_credential=True),
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
