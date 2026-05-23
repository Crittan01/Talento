#!/usr/bin/env python3
"""
bridge_l1.py — DEMO L1 del proyecto talento-ecopetrol.

Cierra el ciclo: pregunta -> agente Foundry -> function_call -> bridge ejecuta
KQL contra Log Analytics -> resultado de vuelta al agente -> respuesta sintetizada.

Uso:
  python3 bridge_l1.py                  # corre con la pregunta por defecto (Q1)
  python3 bridge_l1.py 2                # corre la pregunta de demo Q2
  python3 bridge_l1.py 3                # corre la pregunta de demo Q3
  python3 bridge_l1.py "tu pregunta"    # corre con una pregunta libre
  python3 bridge_l1.py --no-setup       # salta la creacion de version del agente

Prereqs:
  - az login realizado (sin sudo) en el usuario actual
  - .env en el mismo directorio con: AZURE_TENANT_ID, AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET, LOG_ANALYTICS_WORKSPACE_ID
  - Paquetes: azure-ai-projects, azure-identity, openai, requests

Referencias oficiales:
  - Function calling con Foundry agents:
    https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling
  - Log Analytics REST API:
    https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/overview
"""

import json
import sys
import time
from pathlib import Path

import requests
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

# ============================================================================
# Configuración
# ============================================================================
PROJECT_ENDPOINT = "https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2"
MODEL_DEPLOYMENT = "talento-gpt4o-mini"
AGENT_NAME = "talento-triage-agent"

ENV_PATH = Path(__file__).parent / ".env"

# Preguntas de demo (referenciables por número: 1, 2, 3)
DEMO_QUESTIONS = {
    "1": (
        "¿Hay errores recientes en el workspace de Log Analytics de TALENTO? "
        "Detalla los tipos predominantes y los 3 mensajes más frecuentes en "
        "las últimas 24 horas."
    ),
    "2": (
        "Resúmeme la actividad reciente de Container Instances en el workspace "
        "de TALENTO durante las últimas 24 horas. ¿Hay patrones que sugieran "
        "problemas operativos?"
    ),
    "3": (
        "¿Detectas patrones inusuales o de riesgo operativo en los registros de "
        "contenedores de TALENTO en las últimas 24 horas? Identifica los más "
        "críticos y explica por qué te preocupan desde la perspectiva de "
        "continuidad del servicio y cumplimiento SOX."
    ),
}
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
# Ejecución de KQL contra Log Analytics (reutiliza patrón del playbook)
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
    """Ejecuta KQL y devuelve dict legible. Limita a 100 filas si no hay take/top."""
    if "| take " not in query.lower() and "| top " not in query.lower():
        query = query.rstrip() + " | take 100"

    token = get_la_token()
    resp = requests.post(
        f"https://api.loganalytics.azure.com/v1/workspaces/{ENV['LOG_ANALYTICS_WORKSPACE_ID']}/query",
        json={"query": query},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
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
            "hint": (
                "Si el error es SemanticError o por columna inexistente, vuelve "
                "a intentar PRIMERO con '<tabla> | getschema' para conocer las "
                "columnas reales antes de construir queries complejas."
            ),
        }

    data = resp.json()
    if not data.get("tables") or not data["tables"][0].get("rows"):
        return {"rows": 0, "data": [], "query_used": query}

    table = data["tables"][0]
    columns = [c["name"] for c in table["columns"]]
    rows = [dict(zip(columns, row)) for row in table["rows"]]
    return {
        "rows": len(rows),
        "columns": columns,
        "data": rows,
        "query_used": query,
    }


# ============================================================================
# Setup del agente (idempotente — crea nueva versión cada vez, no rompe nada)
# ============================================================================
SYSTEM_INSTRUCTIONS = (
    "Eres un asistente experto en análisis de incidentes IT, especializado en "
    "la solución corporativa TALENTO: sistema de gestión de talento humano, "
    "IaaS, operación 7x24, regulado por SOX, con componentes en Azure (App "
    "Service, Azure SQL, Container Instances, Application Insights, Log "
    "Analytics) y aplicaciones OnPremise (Windows Server 2019, Oracle 12c, "
    "NAS/SAN).\n\n"
    "PROTOCOLO OBLIGATORIO para cada pregunta operativa:\n\n"
    "1. DESCUBRIMIENTO PRIMERO (siempre como primer hop): ejecuta la query\n"
    "   'union withsource=Tabla * | where TimeGenerated > ago(24h) "
    "| summarize count() by Tabla | order by count_ desc'\n"
    "   para conocer qué tablas tienen datos en las últimas 24 horas. NO "
    "asumas que una tabla tiene datos sin verificarlo.\n\n"
    "2. SELECCIÓN: con la lista de tablas pobladas, elige la(s) más "
    "relevantes a la pregunta. Si la pregunta es sobre errores y "
    "AppExceptions está vacía pero ContainerInstanceLog_CL tiene datos, "
    "los logs de contenedor son la fuente válida.\n\n"
    "3. ESQUEMA: si no conoces las columnas reales de la tabla elegida, "
    "ejecuta '<tabla> | getschema' antes de construir queries complejas. "
    "Las columnas con sufijo _s, _d, _b son habituales en tablas _CL.\n\n"
    "4. CONSULTA FINAL: construye la KQL específica para responder. Si "
    "falla con SemanticError, lee el hint del error y reintenta con el "
    "esquema correcto.\n\n"
    "5. RESPUESTA FINAL: SIEMPRE en español, estructurada así:\n"
    "   - Hallazgo (qué encontraste, con números concretos)\n"
    "   - Hipótesis de causa raíz (1-3 ordenadas por probabilidad)\n"
    "   - Pasos de diagnóstico (qué validar a continuación)\n"
    "   - Acción correctiva concreta (qué hacer ahora)\n\n"
    "Sé técnico y conciso. No inventes datos: si las tablas relevantes "
    "están vacías, dilo y propón ampliar el rango de tiempo o revisar la "
    "ingestión de telemetría."
)

FUNCTION_TOOL_QUERY_LA = FunctionTool(
    name="query_log_analytics",
    description=(
        "Ejecuta una consulta KQL contra el workspace de Log Analytics de la "
        "solución TALENTO. Úsala SIEMPRE que la respuesta requiera datos "
        "reales del sistema. Primer hop SIEMPRE: descubrimiento de tablas "
        "pobladas con 'union withsource=Tabla *'. Después: getschema si no "
        "conoces columnas. Devuelve hasta 100 filas en JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "KQL válida. Tablas conocidas pueden incluir: "
                    "AppExceptions, AppRequests, AppTraces, AppDependencies, "
                    "ContainerInstanceLog_CL, ContainerEvent_CL — pero no "
                    "todas tendrán datos. Para descubrir tablas pobladas: "
                    "'union withsource=Tabla * | where TimeGenerated > ago(24h) "
                    "| summarize count() by Tabla | order by count_ desc'"
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)


def setup_agent_version(project: AIProjectClient) -> object:
    """Crea una nueva versión del agente con la tool registrada."""
    return project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT,
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[FUNCTION_TOOL_QUERY_LA],
        ),
    )


# ============================================================================
# Procesamiento de respuestas (multi-hop, formato visual limpio)
# ============================================================================
def process_response_items(response, hop: int) -> tuple:
    """Devuelve (text_acumulado, lista_function_outputs)."""
    text_chunks = []
    fn_outputs = []
    for item in response.output:
        itype = getattr(item, "type", None)
        if itype == "function_call":
            args = json.loads(item.arguments)
            kql = args.get("query", "")
            print(f"\n  🤖 hop {hop} → llama tool: {item.name}")
            print(f"     KQL: {kql}")
            if item.name == "query_log_analytics":
                t0 = time.time()
                result = execute_kql(args["query"])
                elapsed = time.time() - t0
                if "error" in result:
                    err_detail = json.dumps(result["details"], ensure_ascii=False)
                    print(f"     ⚠️  KQL ERROR ({elapsed:.1f}s): {result['error']}")
                    print(f"     {err_detail[:200]}")
                else:
                    print(f"     ✓ KQL OK ({elapsed:.1f}s): {result['rows']} filas")
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


def run_cycle(project: AIProjectClient, agent_name: str, user_question: str, max_hops: int = 6):
    openai_client = project.get_openai_client()
    conversation = openai_client.conversations.create()

    print(f"\n  👤 Usuario: {user_question}")

    t_total = time.time()
    response = openai_client.responses.create(
        input=user_question,
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
    )

    final_text = ""
    for hop in range(1, max_hops + 1):
        text, fn_outputs = process_response_items(response, hop)
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
        print(f"\n  ⚠️  Limite de {max_hops} hops alcanzado sin respuesta final.")

    if not final_text:
        final_text = getattr(response, "output_text", "") or "[sin respuesta de texto]"

    elapsed = time.time() - t_total
    print("\n" + "═" * 78)
    print("  🤖 RESPUESTA FINAL DEL AGENTE")
    print("═" * 78)
    print(final_text)
    print("═" * 78)
    print(f"  ⏱  Tiempo total del ciclo: {elapsed:.1f}s")


# ============================================================================
# Entry point con CLI simple
# ============================================================================
def parse_args():
    """Args muy simples: número de pregunta, texto libre, o --no-setup."""
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
    print("│  bridge_l1.py — DEMO L1 talento-ecopetrol" + " " * 34 + "│")
    print("│  Agente: talento-triage-agent  |  Modelo: talento-gpt4o-mini" + " " * 15 + "│")
    print("└" + "─" * 76 + "┘")

    print("\n► Conectando a Foundry...")
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    agent_name = AGENT_NAME
    if not no_setup:
        print("► Registrando función query_log_analytics en nueva versión del agente...")
        agent = setup_agent_version(project)
        print(f"  ✓ Versión activa: {agent.name}:{agent.version}")
        agent_name = agent.name
    else:
        print("► (--no-setup) Usando la última versión existente del agente")

    print("\n► Iniciando ciclo conversacional...")
    run_cycle(project, agent_name, question)


if __name__ == "__main__":
    main()
