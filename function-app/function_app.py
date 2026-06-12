"""function_app.py — Entry point de Azure Function para el agente TALENTO (v21).

HTTP trigger que recibe webhooks (de ELK, Azure Monitor, Grafana, o cualquier
fuente externa) y dispara al agente Foundry para investigacion recursiva +
remediacion condicional.

FLUJO DE PRODUCCION:
  ELK (HUB de monitoreo)
    → regla dispara
      → POST /api/run {"alert": {...}}
        → normalize_payload convierte la alerta en una instruccion de
          investigacion versatil (no fuerza un playbook — deja que el agente
          decida el camino segun el tipo de metrica)
          → run_cycle: el agente investiga recursivamente con sus 9 tools
            (multi-hop hasta 8 saltos), correlaciona, y propone remediacion
            en dry-run si confirma un problema real de severidad alta
            → respuesta: hallazgo estructurado + acciones propuestas

Endpoints:
  POST /api/run         — invoca al agente (alert | scenario | user_question)
  POST /api/tool/exec   — ejecuta UN tool del bridge (para eval client)
  GET  /api/health      — healthcheck (sin auth)
  GET  /api/agent/info  — config activa del agente (tools, JTs)

Payload POST /api/run — tres formatos:
  {"user_question": "texto libre"}                     ← A: texto crudo
  {"scenario": "infra-health-check", "target_env": "v2"} ← B: pre-canned
  {"alert": {                                           ← C: alerta de ELK/Monitor
     "source": "elk",
     "severity": "high|medium|low",
     "metric": "error_rate|auth_failures|sql_dtu|latency_p95|container_restart|...",
     "resource": "talento-app|ecopetroldb2|aci-...",
     "context": {"value": 42, "threshold": 10, "window": "5m", ...},
     "target_env": "v2"
   }}
"""

import json
import logging
import os
import sys
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional

import azure.functions as func

sys.path.insert(0, str(Path(__file__).parent))
import bridge_l2

logger = logging.getLogger("talento-agent.function")
logger.setLevel(logging.INFO)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ============================================================================
# Deduplicacion de alertas (punto 3) — evita que el agente investigue la misma
# alerta repetidamente si ELK la re-dispara mientras la condicion persiste.
# Complementa el throttle de ELK con una segunda barrera del lado del agente.
# Cache en memoria con TTL; en cold start se resetea (comportamiento correcto).
# ============================================================================
_DEDUP_CACHE: dict = {}
_DEDUP_TTL_SECONDS = 300  # 5 min — alerta identica dentro de esta ventana se ignora


def _alert_signature(alert: dict) -> str:
    """Firma estable de una alerta: misma rule+metric+resource = misma alerta."""
    key = f"{alert.get('rule','')}|{alert.get('metric','')}|{alert.get('resource','')}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _is_duplicate(alert: dict) -> bool:
    """True si esta alerta ya se proceso dentro del TTL. Registra el timestamp."""
    sig = _alert_signature(alert)
    now = time.time()
    # limpiar entradas viejas
    for k in [k for k, ts in _DEDUP_CACHE.items() if now - ts > _DEDUP_TTL_SECONDS]:
        _DEDUP_CACHE.pop(k, None)
    if sig in _DEDUP_CACHE and now - _DEDUP_CACHE[sig] < _DEDUP_TTL_SECONDS:
        return True
    _DEDUP_CACHE[sig] = now
    return False


# ============================================================================
# Procesamiento en background (punto 2 — modo asincrono).
# Para alertas de ELK el endpoint responde 202 inmediato y el agente investiga
# en un thread aparte. ELK dispara y se olvida; el resultado se entrega por
# Teams (notify_teams_finding del bridge) y queda en los logs de la Function.
#
# NOTA produccion: en Azure Functions consumption plan el runtime puede reciclar
# el worker tras devolver la respuesta HTTP, cortando el thread. Para garantia
# total se recomienda un Queue trigger (HTTP encola → Queue procesa). En plan
# dedicado/Premium el thread completa sin problema. Este patron es suficiente
# para el volumen de alertas de TALENTO.
# ============================================================================
def _process_agent_background(user_question: str, target_env: str, elk_alert: Optional[dict] = None):
    """Ejecuta el ciclo del agente sin bloquear la respuesta HTTP."""
    try:
        from azure.ai.projects import AIProjectClient
        project = AIProjectClient(
            endpoint=bridge_l2.PROJECT_ENDPOINT,
            credential=bridge_l2.get_azure_credential(),
        )
        agent_name = ensure_agent_ready(project)
        events = []
        fev = {"target_env": target_env}
        if elk_alert:
            # Contexto para report_incident → Panel de Aprobacion (no viaja a AWX)
            fev["_elk_alert"] = elk_alert
            fev["_incident_id"] = f"INC-{int(time.time())}-{os.urandom(2).hex()}"
            fev["_t_start"] = time.time()
        bridge_l2.run_cycle(
            project=project,
            agent_name=agent_name,
            user_question=user_question,
            max_hops=8,
            emit=lambda ev: events.append(ev),
            force_extra_vars=fev,
        )
        final = next((e.get("text") for e in events if e.get("type") == "agent.final"), None)
        logger.info(f"[async] investigacion completa | hops={len([e for e in events if e.get('type')=='agent.hop'])} | final_len={len(final or '')}")
    except Exception:
        logger.exception("[async] procesamiento en background fallo")


# ============================================================================
# Scenarios pre-canned (v21) — usan TOOLS DIRECTAS, no playbooks de AWX.
# Mantenidos aqui (no importados de webapp/) porque en produccion la Function
# solo despliega function-app/. Espejo de webapp/scenarios.py.
# ============================================================================
SCENARIO_PROMPTS = {
    "infra-health-check": (
        "Health check completo de TALENTO. Llama lookup_infrastructure con "
        "mode='full' y lookup_sql para el estado de todas las capas (ACI, App "
        "Service, SQL, Storage, Quotas). Sintetiza veredicto global HEALTHY/"
        "DEGRADED/CRITICAL por capa. Si hay DEGRADED o CRITICAL, llama "
        "tlnt_explorer con codigo='' y time_range_hours=3 para identificar "
        "errores recientes que expliquen la degradacion."
    ),
    "container-state": (
        "Estado del Container Instance de TALENTO. Llama lookup_infrastructure "
        "con mode='aci'. Reporta state, restartCount y eventos recientes."
    ),
    "appservice-state": (
        "Estado del App Service de TALENTO. Llama lookup_infrastructure con "
        "mode='appservice'. Reporta state, availability y hostname."
    ),
    "sql-health": (
        "Estado de SQL de TALENTO. Llama lookup_sql. Reporta servidores, "
        "databases (status/tier/size). Si los diagnostic settings estan "
        "activos, analiza slow queries, bloqueos y deadlocks."
    ),
    "errors-production": (
        "Errores recientes de TALENTO. Llama tlnt_explorer con codigo='' y "
        "time_range_hours=24 para el ranking de codigos. Para los 3 mas "
        "frecuentes cita su definicion via file_search. Reporta severidad global."
    ),
    "sox-audit": (
        "Auditoria SOX de TALENTO. Llama lookup_runtime_logs con modo='user_audit' "
        "para la actividad reciente. Reporta usuarios, ratio de errores, codigos "
        "TLNT y veredicto de riesgo."
    ),
    "brute-force": (
        "Deteccion de brute force en TALENTO. Llama lookup_runtime_logs con "
        "modo='brute_force' y threshold=5. Reporta usuarios sospechosos con "
        "severidad. Si hay sospechosos, llama detect_anomalies metric_type="
        "'auth_failures' para confirmar si el patron es sistemico."
    ),
    "anomaly-scan": (
        "Escaneo de anomalias en TALENTO. Llama detect_anomalies para "
        "error_rate y auth_failures en las ultimas 24h. Si hay SPIKES, "
        "profundiza con tlnt_explorer o lookup_runtime_logs."
    ),
    "performance-analysis": (
        "Analisis de performance de TALENTO. Llama lookup_app_insights con "
        "modo='top_endpoints', luego 'latency_p95' y 'errors_5xx'. Si hay "
        "latencia anomala, usa 'slow_deps' para identificar dependencias lentas."
    ),
}


def resolve_prompt(scenario: str) -> Optional[str]:
    return SCENARIO_PROMPTS.get(scenario)


# ============================================================================
# Routing inteligente de alertas ELK → camino de investigacion sugerido.
# Mapea la metrica de la alerta a la primera tool que el agente deberia usar.
# NO fuerza un solo camino: el agente sigue siendo libre de profundizar con
# las tools que considere. Esto da el punto de partida correcto segun el tipo.
# ============================================================================
_METRIC_ROUTING = {
    # error / logs
    "error_rate":        "detect_anomalies (metric_type='error_rate') y luego tlnt_explorer para identificar codigos",
    "error_spike":       "detect_anomalies (metric_type='error_rate') y luego tlnt_explorer",
    "tlnt_errors":       "tlnt_explorer (codigo='') para ver el ranking de codigos de error",
    # seguridad / auth
    "auth_failures":     "lookup_runtime_logs (modo='brute_force') y detect_anomalies (metric_type='auth_failures')",
    "brute_force":       "lookup_runtime_logs (modo='brute_force') con threshold del contexto",
    "failed_login":      "lookup_runtime_logs (modo='brute_force')",
    # base de datos
    "sql_dtu":           "lookup_sql para estado y performance de las databases",
    "sql_connections":   "lookup_sql para verificar estado del servidor y databases",
    "database":          "lookup_sql",
    "deadlock":          "lookup_sql para revisar deadlocks y bloqueos recientes",
    # performance / app
    "latency_p95":       "lookup_app_insights (modo='latency_p95') y luego 'slow_deps'",
    "latency":           "lookup_app_insights (modo='latency_p95')",
    "http_5xx":          "lookup_app_insights (modo='errors_5xx')",
    "throughput":        "lookup_app_insights (modo='throughput')",
    "slow_dependency":   "lookup_app_insights (modo='slow_deps')",
    # infraestructura / compute
    "container_restart": "lookup_infrastructure (mode='aci') para restartCount y eventos",
    "container_state":   "lookup_infrastructure (mode='aci')",
    "appservice_down":   "lookup_infrastructure (mode='appservice')",
    "cpu":               "lookup_infrastructure (mode='quotas')",
    "memory":            "lookup_infrastructure (mode='aci')",
}


def _suggested_path(metric: str) -> str:
    """Devuelve el camino de investigacion sugerido para una metrica.
    Si la metrica no esta mapeada, sugiere un health check completo."""
    m = (metric or "").lower().strip()
    # match exacto o por substring (ELK puede enviar 'talento.error_rate.5m')
    for key, path in _METRIC_ROUTING.items():
        if key in m:
            return path
    return ("lookup_infrastructure (mode='full') y lookup_sql como punto de "
            "partida para un diagnostico amplio")


def normalize_payload(body: dict) -> Optional[str]:
    """Convierte cualquier formato de payload en un user_question para el agente.

    Para alertas (formato C), construye una instruccion de investigacion
    VERSATIL: da contexto rico, sugiere el punto de partida segun la metrica,
    e instruye investigacion recursiva + remediacion condicional en dry-run.
    """
    if body.get("user_question"):
        return body["user_question"]

    if body.get("scenario"):
        return resolve_prompt(body["scenario"])

    if isinstance(body.get("alert"), dict):
        alert = body["alert"]
        source   = alert.get("source", "monitoring")
        severity = str(alert.get("severity", "unknown")).lower()
        metric   = alert.get("metric", "?")
        resource = alert.get("resource", "TALENTO")
        ctx      = alert.get("context", {})
        path     = _suggested_path(metric)

        # Brute force: ELK tiene la evidencia de red (azure-eventhub.client_ip)
        # que el agente NO ve en Azure Log Analytics. Si la alerta trae source_ip,
        # confiar en ELK y proponer el bloqueo (no marcar falso positivo por no
        # verlo en Azure).
        src_ip_alert = str(ctx.get("source_ip", "") or "").strip()
        is_bruteforce = bool(src_ip_alert) and (
            "brute" in str(metric).lower() or "auth" in str(metric).lower())
        bruteforce_clause = ""
        if is_bruteforce:
            bruteforce_clause = (
                f"\n\nNOTA CRITICA — BRUTE FORCE YA DETECTADO POR ELK: el Watcher de "
                f"ELK detecto multiples fallos de login (HTTP 401) desde la IP "
                f"{src_ip_alert} en los logs de red (azure-eventhub). ESOS LOGS NO "
                f"ESTAN en Azure Log Analytics — tus tools de Azure NO los veran, y "
                f"eso es ESPERADO; NO lo interpretes como falso positivo. ELK ya tiene "
                f"la evidencia. ACCION REQUERIDA en report_incident: "
                f"requiere_remediacion=true, playbook='talento-nsg-block-ip', "
                f"categoria='seguridad', modulo_talento='login.autenticacion', "
                f"error_code='TLNT-009'. La IP a bloquear ({src_ip_alert}) ya viaja "
                f"en el contexto; el sistema la propaga al playbook automaticamente. "
                f"ANTES de reportar, ENRIQUECE el caso: llama lookup_elk(modo='ip_detail', "
                f"ip='{src_ip_alert}', window_min=43200) para obtener la GEOLOCALIZACION "
                f"(pais/ciudad) y el perfil de la IP, e INCLUYE esos datos en la "
                f"causa_raiz y la recomendacion (ej. 'IP de Cartagena, Colombia')."
            )

        # DDL no autorizado (dolor 5): correlacionar contra el registro de cambios
        # CHG. Si no hay ventana aprobada que cubra el objeto → cambio NO AUTORIZADO.
        _ml = str(metric).lower()
        ddl_obj = str(ctx.get("objeto", "") or ctx.get("object", "")).strip()
        ddl_user = str(ctx.get("usuario", "") or ctx.get("user", "")).strip()
        ddl_cmd = str(ctx.get("comando", "") or ctx.get("command", "")).strip()
        is_ddl = "ddl" in _ml
        ddl_clause = ""
        if is_ddl:
            ddl_clause = (
                f"\n\nNOTA CRITICA — DDL EN BASE DE DATOS DETECTADO (control SOX): se "
                f"ejecuto un comando DDL ({ddl_cmd or 'CREATE/ALTER/DROP'}) sobre el "
                f"objeto '{ddl_obj}' por el usuario '{ddl_user}' en la BD de TALENTO. "
                f"DEBES determinar si es AUTORIZADO: (1) llama "
                f"lookup_changes(ci_id='CI-SQL-V2', estado='aprobado') para ver las "
                f"ventanas de cambio CHG aprobadas; (2) verifica si el objeto coincide "
                f"con algun objeto_patron de una CHG cuya ventana (ventana_inicio.."
                f"ventana_fin) cubra el momento del evento. Si NO hay CHG que lo cubra "
                f"→ CAMBIO NO AUTORIZADO: en report_incident usa categoria='base_datos', "
                f"requiere_remediacion=true, playbook='talento-sql-revoke-ddl', y explica "
                f"en causa_raiz que el objeto se creo/modifico fuera de toda ventana de "
                f"cambio aprobada. Si SI hay CHG que lo cubra → requiere_remediacion=false "
                f"e informa que el cambio esta AUTORIZADO (cita la CHG correlacionada)."
            )

        # Acceso anomalo a BD / DAM (dolor 6): analogo al brute force aplicado a la BD.
        dam_user = str(ctx.get("usuario", "") or ctx.get("user", "")).strip()
        dam_ip = str(ctx.get("source_ip", "") or "").strip()
        is_dam = "acceso_db" in _ml or "dam" in _ml
        dam_clause = ""
        if is_dam:
            dam_clause = (
                f"\n\nNOTA CRITICA — ACCESO ANOMALO A BASE DE DATOS: acceso sospechoso "
                f"a la BD de TALENTO (usuario '{dam_user or 'desconocido'}', origen "
                f"'{dam_ip or 'desconocido'}'). Correlaciona: (1) "
                f"lookup_elk(modo='ip_detail', ip='{dam_ip}', window_min=43200) para "
                f"geolocalizar el origen; (2) user_activity para el patron del usuario; "
                f"(3) lookup_cmdb(ref='sqlserver-ecopetrol2') para el CI/owner. Si "
                f"confirmas acceso indebido (fuera de horario, origen no autorizado, "
                f"comando privilegiado) en report_incident usa categoria='seguridad', "
                f"requiere_remediacion=true y propon el playbook adecuado: "
                f"'talento-nsg-block-ip' si el vector es una IP de red, o "
                f"'talento-sql-disable-login' si hay que deshabilitar el login de BD. "
                f"Incluye geo y patron en la causa_raiz."
            )

        # Remediacion condicional segun severidad. Robusto a variantes en
        # espanol/mayusculas que mandan las reglas de Kibana (CRITICO, ALTA, etc.).
        # DDL/DAM habilitan remediacion sin importar severidad (seguridad/SOX).
        if is_ddl or is_dam or any(k in severity for k in ("high", "critic", "alta", "alto", "sever", "urgen")):
            remediation_clause = (
                "PASO FINAL — REMEDIACION: Si CONFIRMAS un problema real "
                "(no falso positivo) y la accion correctiva esta dentro del "
                "catalogo de playbooks (restart de container/appservice, "
                "habilitar diagnostics SQL, bloquear IP en NSG), PROPON la "
                "remediacion ejecutando el playbook correspondiente en "
                "dry_run=true. NUNCA ejecutes dry_run=false sin confirmacion "
                "explicita de un operador humano. Si la accion NO esta en el "
                "catalogo (ej. reiniciar SQL, cambiar permisos), escala al "
                "equipo correspondiente sin tocar AWX."
            )
        else:
            remediation_clause = (
                "Severidad {sev}: limita el alcance a diagnostico e informe. "
                "NO propongas remediacion automatica — solo registra el "
                "hallazgo y recomienda monitoreo.".format(sev=severity)
            )

        return (
            f"ALERTA DE MONITOREO recibida desde '{source}'.\n"
            f"  Severidad: {severity}\n"
            f"  Metrica disparada: {metric}\n"
            f"  Recurso afectado: {resource}\n"
            f"  Contexto: {json.dumps(ctx, ensure_ascii=False)}\n\n"
            f"PASO 1 — PUNTO DE PARTIDA: {path}.\n\n"
            f"PASO 2 — CORRELACION TOTAL MULTI-FUENTE (OBLIGATORIA): NO te quedes "
            f"con una sola tool. Para determinar la causa raiz REAL debes cruzar "
            f"TODAS las fuentes relevantes y contrastarlas entre si:\n"
            f"  • Errores conocidos (lookup_kedb): consulta PRIMERO por error_code/"
            f"regla/categoria — si el error ya esta en la KEDB, aplica la solucion "
            f"documentada y el playbook sugerido en vez de re-investigar desde cero.\n"
            f"  • CMDB (lookup_cmdb): identifica el CI afectado (servicio, owner_group, "
            f"criticidad, dependencias) por el recurso o el modulo TALENTO.\n"
            f"  • Infraestructura (lookup_infrastructure): estado de container/"
            f"AppService, restartCount, CPU/memoria.\n"
            f"  • Base de datos (lookup_sql): databases, performance, deadlocks.\n"
            f"  • Logs de aplicacion (lookup_runtime_logs, lookup_correlation_id, "
            f"tlnt_explorer): codigos TLNT, correlation_id, errores.\n"
            f"  • Performance (lookup_app_insights): latencia, 5xx, dependencias.\n"
            f"  • Anomalias (detect_anomalies): picos/caidas estadisticas.\n"
            f"  • RED (lookup_elk): IP real del cliente, geolocalizacion, HTTP logs "
            f"— Azure ENMASCARA la IP a 0.0.0.0, asi que para CUALQUIER tema de "
            f"seguridad/auth/errores HTTP, lookup_elk es la UNICA fuente de la IP.\n"
            f"Reconstruye la cadena causal cruzando capas (ej. spike de errores → "
            f"codigo TLNT → correlation_id → infra → red). No te detengas en el "
            f"primer dato. Lleva registro mental de QUE fuentes consultaste.\n\n"
            f"PASO 3 — VEREDICTO: determina si la alerta corresponde a un "
            f"problema REAL o es un FALSO POSITIVO. Justifica con los datos.\n\n"
            f"{remediation_clause}{bruteforce_clause}{ddl_clause}{dam_clause}\n\n"
            f"PASO FINAL OBLIGATORIO Y AUTOMATICO — report_incident: tu ULTIMA "
            f"accion en CADA alerta DEBE ser llamar a la tool report_incident. "
            f"NO es opcional, NO pidas confirmacion al usuario, NO preguntes "
            f"'¿apruebas el reporte?' — es el registro automatico del incidente. "
            f"Llamala SIEMPRE, incluso si es falso positivo (con requiere_remediacion=false). "
            f"Parametros: causa_raiz, confianza_pct (0-100), categoria "
            f"(infraestructura/aplicacion/base_datos/seguridad/red), modulo_talento "
            f"(del logger_name o codigo TLNT: login.autenticacion, nomina.liquidacion, "
            f"vacaciones.aprobacion, incapacidades.aprobacion, contrato.renovacion, "
            f"capacitacion.registro), error_code (TLNT-XXX si aplica), "
            f"requiere_remediacion (true solo si hay problema real con accion del "
            f"catalogo), playbook (talento-aci-restart/stop/start, "
            f"talento-appservice-restart, talento-sql-diagnostics-enable, "
            f"talento-nsg-block-ip, talento-sql-revoke-ddl, talento-sql-disable-login; "
            f"vacio si no aplica). Recien DESPUES de llamar "
            f"report_incident, escribe tu respuesta final en texto.\n\n"
            f"Responde estructurado: Hallazgo · Causa raiz · Veredicto · Accion propuesta."
        )

    return None


# ============================================================================
# Agent setup — una vez por cold start
# ============================================================================
_AGENT_SETUP_DONE = False


def ensure_agent_ready(project) -> str:
    """Crea una nueva version del agente UNA vez por instancia de Function."""
    global _AGENT_SETUP_DONE
    if _AGENT_SETUP_DONE:
        return bridge_l2.AGENT_NAME
    try:
        existing = list(project.agents.list_versions(agent_name=bridge_l2.AGENT_NAME))
        prev_count = len(existing)
    except Exception:
        prev_count = 0
    logger.info(f"Setup '{bridge_l2.AGENT_NAME}' — versiones previas: {prev_count}")
    agent = bridge_l2.setup_agent_version(project)
    logger.info(f"Nueva version: name={agent.name} version={getattr(agent,'version','?')}")
    _AGENT_SETUP_DONE = True
    return agent.name


# ============================================================================
# Endpoints
# ============================================================================
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def healthcheck(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "agent_name": bridge_l2.AGENT_NAME,
            "catalog_version": bridge_l2.CATALOG_VERSION,
            "jt_ids_count": len(bridge_l2.JT_IDS),
        }),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="agent/info", methods=["GET"])
def agent_info(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({
            "agent_name": bridge_l2.AGENT_NAME,
            "catalog_version": bridge_l2.CATALOG_VERSION,
            "project_endpoint": bridge_l2.PROJECT_ENDPOINT,
            "model_deployment": bridge_l2.MODEL_DEPLOYMENT,
            "jt_ids": bridge_l2.JT_IDS,
            "scenarios_available": list(SCENARIO_PROMPTS.keys()),
            "alert_metrics_routed": list(_METRIC_ROUTING.keys()),
        }, indent=2),
        mimetype="application/json",
        status_code=200,
    )


@app.route(route="tool/exec", methods=["POST"])
def tool_exec(req: func.HttpRequest) -> func.HttpResponse:
    """Ejecuta UN tool del bridge desde un cliente externo (eval/diagnostico)."""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body invalido — debe ser JSON"}),
            mimetype="application/json", status_code=400,
        )

    tool_name = body.get("tool")
    args = body.get("args") or {}
    target_env = body.get("target_env", "v2")

    try:
        if tool_name == "query_log_analytics":
            result = bridge_l2.execute_kql(args.get("query", ""))
        elif tool_name == "lookup_infrastructure":
            result = bridge_l2.lookup_infrastructure(
                mode=args.get("mode", "full"),
                resource_group=args.get("resource_group", ""),
                target_env=target_env,
            )
        elif tool_name == "lookup_sql":
            result = bridge_l2.lookup_sql(target_env=target_env)
        elif tool_name == "detect_anomalies":
            result = bridge_l2.detect_anomalies(
                metric_type=args.get("metric_type", "error_rate"),
                time_range_hours=int(args.get("time_range_hours", 24)),
                bin_minutes=int(args.get("bin_minutes", 10)),
                target_env=target_env,
            )
        elif tool_name == "run_awx_job_template":
            result = bridge_l2.run_awx_job_template(
                args.get("template_id"),
                extra_vars=args.get("extra_vars") or {},
            )
        else:
            return func.HttpResponse(
                json.dumps({"error": f"unknown tool: {tool_name}"}),
                mimetype="application/json", status_code=400,
            )
        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False),
            mimetype="application/json", status_code=200,
        )
    except Exception as exc:
        logger.exception("tool/exec fallo")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            mimetype="application/json", status_code=500,
        )


@app.route(route="run", methods=["POST"])
def run_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Invoca al agente Foundry con el payload recibido (alert | scenario | raw)."""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body invalido — debe ser JSON"}),
            mimetype="application/json", status_code=400,
        )

    is_alert = isinstance(body.get("alert"), dict)

    # Deduplicacion (punto 3): solo para alertas de ELK
    if is_alert and _is_duplicate(body["alert"]):
        logger.info(f"Alerta duplicada ignorada | sig={_alert_signature(body['alert'])}")
        return func.HttpResponse(
            json.dumps({
                "status": "deduplicated",
                "message": "Alerta identica procesada recientemente (dentro de 5 min). "
                           "Ignorada para evitar investigacion redundante.",
                "signature": _alert_signature(body["alert"]),
            }),
            mimetype="application/json", status_code=200,
        )

    user_question = normalize_payload(body)
    if not user_question:
        return func.HttpResponse(
            json.dumps({
                "error": "Payload sin formato reconocido",
                "expected_keys": ["user_question", "scenario", "alert"],
            }),
            mimetype="application/json", status_code=400,
        )

    # target_env: del payload directo, del alert, o default v2
    target_env = body.get("target_env") or \
        (body.get("alert", {}).get("target_env") if is_alert else None) or \
        "v2"

    # Modo asincrono (punto 2): las alertas de ELK responden 202 inmediato y
    # el agente investiga en background. ELK dispara y se olvida; el resultado
    # llega por Teams. scenario/user_question siguen sincronos (webapp/eval los
    # consumen esperando el resultado). Override con {"async": false} si se quiere
    # esperar el resultado de una alerta.
    async_mode = body.get("async", is_alert)

    if async_mode:
        elk_alert = dict(body["alert"]) if is_alert else None
        if elk_alert and "rule" not in elk_alert:
            elk_alert["rule"] = elk_alert.get("metric", "regla-sin-nombre")
        threading.Thread(
            target=_process_agent_background,
            args=(user_question, target_env, elk_alert),
            daemon=True,
        ).start()
        logger.info(f"Run aceptado (async) | env={target_env} | alert={is_alert}")
        return func.HttpResponse(
            json.dumps({
                "status": "accepted",
                "mode": "async",
                "message": "Alerta recibida. El agente investiga en background; "
                           "el resultado se notificara por Teams.",
                "target_env": target_env,
            }, ensure_ascii=False),
            mimetype="application/json", status_code=202,
        )

    logger.info(f"Run iniciado (sync) | env={target_env} | question_len={len(user_question)}")

    try:
        from azure.ai.projects import AIProjectClient
        project = AIProjectClient(
            endpoint=bridge_l2.PROJECT_ENDPOINT,
            credential=bridge_l2.get_azure_credential(),
        )
        agent_name = ensure_agent_ready(project)

        events = []
        def collect_emit(event):
            events.append(event)

        bridge_l2.run_cycle(
            project=project,
            agent_name=agent_name,
            user_question=user_question,
            max_hops=8,
            emit=collect_emit,
            force_extra_vars={"target_env": target_env},
        )

        # Extraer texto final + tools invocadas (para trazabilidad)
        final_text = None
        tools_used = []
        for ev in events:
            if ev.get("type") == "agent.final":
                final_text = ev.get("text")
            elif ev.get("type") == "tool.call":
                tools_used.append(ev.get("tool"))

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "agent_name": agent_name,
                "target_env": target_env,
                "final_text": final_text,
                "tools_used": tools_used,
                "hops": len([e for e in events if e.get("type") == "agent.hop"]),
                "events_count": len(events),
            }, ensure_ascii=False),
            mimetype="application/json", status_code=200,
        )
    except Exception as exc:
        logger.exception("Run fallo")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            mimetype="application/json", status_code=500,
        )


@app.route(route="elk/execute", methods=["POST"])
def elk_execute(req: func.HttpRequest) -> func.HttpResponse:
    """Opcion 2 — el panel llama aqui cuando el operador APRUEBA una remediacion.
    Ejecuta el playbook real en AWX (aprobacion = operator_confirmed) y escribe
    el cierre de vuelta al panel (estado=exitoso/fallido, job_id, mttr)."""
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body invalido — debe ser JSON"}),
            mimetype="application/json", status_code=400,
        )

    incident_id = body.get("incident_id", "")
    playbook = body.get("playbook", "")
    alert = body.get("alert") or {}
    dry_run = bool(body.get("dry_run", False))

    if bridge_l2._playbook_to_jt(playbook) is None:
        return func.HttpResponse(
            json.dumps({"error": f"playbook '{playbook}' no es del catalogo",
                        "valid": list(bridge_l2._PLAYBOOK_TO_JT_KEY.keys())}),
            mimetype="application/json", status_code=400,
        )

    try:
        result = bridge_l2.execute_approved_remediation(
            incident_id=incident_id, playbook=playbook,
            extra_vars=body.get("extra_vars"), dry_run=dry_run,
        )
        if result.get("blocked_by_guard"):
            return func.HttpResponse(json.dumps(result), mimetype="application/json", status_code=403)

        mttr = int(body.get("mttr_segundos") or result.get("elapsed_seconds") or 0)
        closure = bridge_l2.build_closure_payload(
            incident_id=incident_id, alert=alert, playbook=playbook,
            causa_raiz=body.get("causa_raiz", ""), modulo_talento=body.get("modulo_talento", ""),
            job_result=result, mttr_segundos=mttr, error_code=body.get("error_code", ""),
        )
        panel_resp = bridge_l2.post_incident_to_panel(closure)

        return func.HttpResponse(
            json.dumps({
                "status": "ok",
                "incident_id": incident_id,
                "playbook": playbook,
                "ejecucion": closure["automatizacion"]["estado"],
                "job_id": result.get("job_id"),
                "dry_run": dry_run,
                "cierre_index": panel_resp.get("index"),
                "mttr_segundos": mttr,
            }, ensure_ascii=False),
            mimetype="application/json", status_code=200,
        )
    except Exception as exc:
        logger.exception("elk/execute fallo")
        return func.HttpResponse(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            mimetype="application/json", status_code=500,
        )
