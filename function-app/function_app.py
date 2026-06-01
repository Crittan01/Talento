"""function_app.py — Entry point de Azure Function para el agente TALENTO.

HTTP trigger que recibe webhooks (de ELK, Azure Monitor, dashboard, o
cualquier fuente externa) y dispara al agente Foundry para diagnostico +
remediacion.

Endpoints expuestos:
  POST /api/run         — invoca al agente con un user_question o scenario
  GET  /api/health      — healthcheck (sin auth)
  GET  /api/agent/info  — devuelve el AGENT_NAME y JT_IDS activos

Payload esperado para POST /api/run:
  {
    "user_question": "texto libre que el agente procesa"   ← opcion A: texto crudo
  }
o
  {
    "scenario": "infra-health-check" | "system-status" | ...  ← opcion B: scenario id
  }
o
  {
    "alert": {
      "source": "elk|azuremonitor|grafana|...",
      "severity": "high|medium|low",
      "metric": "error_rate",
      "context": {...}
    }
  }                                                          ← opcion C: alerta cruda
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import azure.functions as func

# Asegurar que el directorio actual está en path para importar bridge_l2
sys.path.insert(0, str(Path(__file__).parent))

import bridge_l2

logger = logging.getLogger("talento-agent.function")
logger.setLevel(logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ============================================================================
# Mapeo scenario -> user_question (mismo que en webapp/scenarios.py)
# ============================================================================
SCENARIO_PROMPTS = {
    "infra-health-check": (
        "Ejecuta directamente el job template id={jt_full_health_check} "
        "(talento-full-health-check) con extra_vars_json='{{}}' para obtener "
        "panorama de salud de la infraestructura TALENTO. Sintetiza: estado "
        "de cada capa (ACI, App Service, SQL), veredicto global (HEALTHY/"
        "DEGRADED/CRITICAL) y recomendacion concreta."
    ),
    "container-state": (
        "Ejecuta el job template id={jt_aci_state} (talento-aci-state) con "
        "extra_vars_json='{{}}'. Sintetiza estado del Container Instance."
    ),
    "appservice-state": (
        "Ejecuta el job template id={jt_appservice_state} (talento-appservice-state) "
        "con extra_vars_json='{{}}'. Sintetiza estado del App Service."
    ),
    "sql-health": (
        "Ejecuta el job template id={jt_sql_health} (talento-sql-health) con "
        "extra_vars_json='{{}}'. Sintetiza estado del SQL Server + databases."
    ),
    "system-status": (
        "Ejecuta el job template id={jt_workspace_snapshot} (talento-workspace-snapshot) "
        "con extra_vars_json='{{\"time_range_hours\": 24}}'. Sintetiza tablas "
        "pobladas y top mensajes."
    ),
    "errors-production": (
        "Ejecuta el job template id={jt_errors_analysis} (talento-errors-analysis) "
        "con extra_vars_json='{{\"time_range_hours\": 24}}'. Sintetiza errores/warnings."
    ),
    "sox-audit": (
        "Ejecuta el job template id={jt_sox_audit} (talento-sox-audit) con "
        "extra_vars_json='{{\"time_range_hours\": 24}}'. Sintetiza auditoria SOX."
    ),
    "brute-force": (
        "Ejecuta el job template id={jt_brute_force} (talento-brute-force-detector) "
        "con extra_vars_json='{{\"time_range_hours\": 24, \"failed_threshold\": 5}}'. "
        "Sintetiza usuarios sospechosos."
    ),
}


def resolve_prompt(scenario: str) -> Optional[str]:
    template = SCENARIO_PROMPTS.get(scenario)
    if not template:
        return None
    return template.format(**bridge_l2.JT_IDS)


# ============================================================================
# Helpers para normalizar el payload
# ============================================================================
def normalize_payload(body: dict) -> Optional[str]:
    """Convierte cualquier formato de payload en un user_question para el agente.

    Soporta:
      - {"user_question": "..."}  (raw)
      - {"scenario": "..."}        (pre-canned)
      - {"alert": {...}}           (de ELK/Monitor — convierte a pregunta)
    """
    if "user_question" in body and body["user_question"]:
        return body["user_question"]

    if "scenario" in body and body["scenario"]:
        return resolve_prompt(body["scenario"])

    if "alert" in body and isinstance(body["alert"], dict):
        alert = body["alert"]
        source = alert.get("source", "monitoring")
        severity = alert.get("severity", "unknown")
        metric = alert.get("metric", "?")
        ctx = alert.get("context", {})
        return (
            f"Alerta recibida desde {source} con severidad {severity}. "
            f"Metrica disparada: {metric}. Contexto: {json.dumps(ctx)}. "
            f"Ejecuta full-health-check (JT id={bridge_l2.JT_IDS['jt_full_health_check']}) "
            f"para diagnosticar TALENTO y sintetiza si la alerta corresponde a "
            f"un problema real. Si la severidad es alta y hay degradacion, propon "
            f"accion de remediacion en dry-run."
        )

    return None


def ensure_agent_ready(project) -> str:
    """Verifica que el agente Foundry con AGENT_NAME actual exista.
    Si no existe, lo crea con instructions + tools actualizadas."""
    try:
        versions = list(project.agents.list_versions(name=bridge_l2.AGENT_NAME))
    except Exception:
        versions = []
    if versions:
        logger.info(f"Agente '{bridge_l2.AGENT_NAME}' ya existe ({len(versions)} version(es))")
        return bridge_l2.AGENT_NAME
    logger.info(f"Agente '{bridge_l2.AGENT_NAME}' no existe — creando...")
    agent = bridge_l2.setup_agent_version(project)
    logger.info(f"Agente creado: name={agent.name}")
    return agent.name


# ============================================================================
# Endpoints
# ============================================================================
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def healthcheck(req: func.HttpRequest) -> func.HttpResponse:
    """Healthcheck simple — sin auth, para validar que la Function arranca."""
    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "agent_name": bridge_l2.AGENT_NAME,
            "jt_ids_count": len(bridge_l2.JT_IDS),
        }),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="agent/info", methods=["GET"])
def agent_info(req: func.HttpRequest) -> func.HttpResponse:
    """Devuelve la config actual del agente (JT IDs, agent name)."""
    return func.HttpResponse(
        json.dumps({
            "agent_name": bridge_l2.AGENT_NAME,
            "project_endpoint": bridge_l2.PROJECT_ENDPOINT,
            "model_deployment": bridge_l2.MODEL_DEPLOYMENT,
            "jt_ids": bridge_l2.JT_IDS,
            "scenarios_available": list(SCENARIO_PROMPTS.keys()),
        }, indent=2),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="run", methods=["POST"])
def run_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Invoca al agente Foundry con el payload recibido."""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body invalido — debe ser JSON"}),
            mimetype="application/json",
            status_code=400,
        )

    user_question = normalize_payload(body)
    if not user_question:
        return func.HttpResponse(
            json.dumps({
                "error": "Payload sin formato reconocido",
                "expected_keys": ["user_question", "scenario", "alert"],
            }),
            mimetype="application/json",
            status_code=400,
        )

    logger.info(f"Run iniciado | question_len={len(user_question)}")

    try:
        from azure.ai.projects import AIProjectClient
        project = AIProjectClient(
            endpoint=bridge_l2.PROJECT_ENDPOINT,
            credential=bridge_l2.get_azure_credential(),
        )
        agent_name = ensure_agent_ready(project)

        # Captura los eventos del bridge para devolverlos en la respuesta
        events = []

        def collect_emit(event):
            events.append(event)

        # bridge_l2.run_cycle imprime a stdout y dispara emit() para eventos SSE.
        # Aqui ejecutamos sync y devolvemos resultado consolidado.
        result = bridge_l2.run_cycle(
            project=project,
            agent_name=agent_name,
            user_question=user_question,
            max_hops=4,
            emit=collect_emit,
        )

        # Extraer el texto final del agente de los eventos
        final_text = None
        for ev in events:
            if ev.get("type") == "agent.final":
                final_text = ev.get("text")
                break

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "agent_name": agent_name,
                "final_text": final_text,
                "events_count": len(events),
                "result": result if isinstance(result, (dict, list, str, int, float, type(None))) else str(result),
            }),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as exc:
        logger.exception("Run fallo")
        return func.HttpResponse(
            json.dumps({
                "error": str(exc),
                "type": type(exc).__name__,
            }),
            mimetype="application/json",
            status_code=500,
        )
