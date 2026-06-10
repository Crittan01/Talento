"""elk_alerts.py — Catálogo de alertas ELK demo para el dashboard interno.

Reproduce lo que ELK enviaría al endpoint /api/run en producción. Estas mismas
alertas viven en scripts/simulate-elk-alert.py; aquí se exponen a la webapp para
visualizar el flujo ELK → normalización → investigación del agente.

La función build_alert_prompt() replica la lógica de normalize_payload() del
function_app.py productivo — así el dashboard muestra EXACTAMENTE la instrucción
que el agente recibiría en producción.
"""
from __future__ import annotations
import json
from typing import Optional


# ============================================================================
# Catálogo de alertas — reglas típicas de ELK Watcher / Kibana Alerting
# ============================================================================
ELK_ALERTS = {
    "elk-error-rate": {
        "title": "Error Rate Alto",
        "icon": "📈",
        "subtitle": "ELK Watcher — tasa de ERROR superó umbral en 5 min",
        "rule": "talento-error-rate-watcher",
        "alert": {
            "source": "elk",
            "rule": "talento-error-rate-watcher",
            "severity": "high",
            "metric": "error_rate",
            "resource": "talento-app (aci-centralecopetrol2)",
            "context": {"value": 18, "threshold": 10, "unit": "errors/5min", "window": "5m", "index": "talento-logs-*"},
            "target_env": "v2",
        },
    },
    "elk-auth-failures": {
        "title": "Brute Force Sospechoso",
        "icon": "🛡️",
        "subtitle": "ELK Watcher — pico de fallos de autenticación",
        "rule": "talento-auth-bruteforce-watcher",
        "alert": {
            "source": "elk",
            "rule": "talento-auth-bruteforce-watcher",
            "severity": "high",
            "metric": "auth_failures",
            "resource": "talento-app login",
            "context": {"value": 23, "threshold": 5, "unit": "failed_logins/3min", "window": "3m", "tlnt_codes": ["TLNT-002", "TLNT-008", "TLNT-009"]},
            "target_env": "v2",
        },
    },
    "elk-sql-dtu": {
        "title": "SQL DTU Saturado",
        "icon": "🗄️",
        "subtitle": "Azure Monitor vía ELK — DTU alto en cierre de nómina",
        "rule": "talento-sql-dtu-watcher",
        "alert": {
            "source": "azuremonitor-via-elk",
            "rule": "talento-sql-dtu-watcher",
            "severity": "high",
            "metric": "sql_dtu",
            "resource": "sqlserver-ecopetrol2/ecopetroldb2",
            "context": {"value": 92, "threshold": 80, "unit": "DTU%", "window": "15m", "note": "coincide con cierre de nómina"},
            "target_env": "v2",
        },
    },
    "elk-latency": {
        "title": "Latencia Degradada",
        "icon": "⏱️",
        "subtitle": "ELK Watcher — P95 de endpoints sobre umbral",
        "rule": "talento-latency-watcher",
        "alert": {
            "source": "elk",
            "rule": "talento-latency-watcher",
            "severity": "medium",
            "metric": "latency_p95",
            "resource": "talento-app endpoints",
            "context": {"value": 2400, "threshold": 1000, "unit": "ms", "window": "10m", "affected_endpoints": ["/api/vacaciones", "/api/nomina"]},
            "target_env": "v2",
        },
    },
    "elk-container-restart": {
        "title": "Container Crash Loop",
        "icon": "📦",
        "subtitle": "ELK Watcher — reinicios repetidos del container",
        "rule": "talento-container-restart-watcher",
        "alert": {
            "source": "elk",
            "rule": "talento-container-restart-watcher",
            "severity": "critical",
            "metric": "container_restart",
            "resource": "aci-centralecopetrol2",
            "context": {"value": 4, "threshold": 2, "unit": "restarts/30min", "window": "30m"},
            "target_env": "v2",
        },
    },
}


# ============================================================================
# Routing de métrica → camino de investigación (espejo de function_app.py)
# ============================================================================
_METRIC_ROUTING = {
    "error_rate": "detect_anomalies (metric_type='error_rate') y luego tlnt_explorer para identificar codigos",
    "error_spike": "detect_anomalies (metric_type='error_rate') y luego tlnt_explorer",
    "tlnt_errors": "tlnt_explorer (codigo='') para ver el ranking de codigos de error",
    "auth_failures": "lookup_runtime_logs (modo='brute_force') y detect_anomalies (metric_type='auth_failures')",
    "brute_force": "lookup_runtime_logs (modo='brute_force') con threshold del contexto",
    "failed_login": "lookup_runtime_logs (modo='brute_force')",
    "sql_dtu": "lookup_sql para estado y performance de las databases",
    "sql_connections": "lookup_sql para verificar estado del servidor y databases",
    "database": "lookup_sql",
    "deadlock": "lookup_sql para revisar deadlocks y bloqueos recientes",
    "latency_p95": "lookup_app_insights (modo='latency_p95') y luego 'slow_deps'",
    "latency": "lookup_app_insights (modo='latency_p95')",
    "http_5xx": "lookup_app_insights (modo='errors_5xx')",
    "throughput": "lookup_app_insights (modo='throughput')",
    "slow_dependency": "lookup_app_insights (modo='slow_deps')",
    "container_restart": "lookup_infrastructure (mode='aci') para restartCount y eventos",
    "container_state": "lookup_infrastructure (mode='aci')",
    "appservice_down": "lookup_infrastructure (mode='appservice')",
    "cpu": "lookup_infrastructure (mode='quotas')",
    "memory": "lookup_infrastructure (mode='aci')",
}


def _suggested_path(metric: str) -> str:
    m = (metric or "").lower().strip()
    for key, path in _METRIC_ROUTING.items():
        if key in m:
            return path
    return "lookup_infrastructure (mode='full') y lookup_sql para un diagnostico amplio"


def build_alert_prompt(alert: dict) -> str:
    """Replica normalize_payload() del function_app — construye la instrucción
    versátil de investigación a partir de una alerta de ELK."""
    source   = alert.get("source", "monitoring")
    severity = str(alert.get("severity", "unknown")).lower()
    metric   = alert.get("metric", "?")
    resource = alert.get("resource", "TALENTO")
    ctx      = alert.get("context", {})
    path     = _suggested_path(metric)

    if severity in ("high", "critical", "alta", "critica"):
        remediation = (
            "PASO FINAL — REMEDIACION: Si CONFIRMAS un problema real (no falso "
            "positivo) y la accion correctiva esta en el catalogo de playbooks "
            "(restart de container/appservice, habilitar diagnostics SQL, "
            "bloquear IP en NSG), PROPON la remediacion en dry_run=true. NUNCA "
            "ejecutes dry_run=false sin confirmacion explicita de un operador. "
            "Si la accion NO esta en el catalogo, escala al equipo correspondiente."
        )
    else:
        remediation = (
            f"Severidad {severity}: limita el alcance a diagnostico e informe. "
            "NO propongas remediacion automatica — registra el hallazgo y "
            "recomienda monitoreo."
        )

    return (
        f"ALERTA DE MONITOREO recibida desde '{source}'.\n"
        f"  Severidad: {severity}\n"
        f"  Metrica disparada: {metric}\n"
        f"  Recurso afectado: {resource}\n"
        f"  Contexto: {json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"PASO 1 — PUNTO DE PARTIDA: {path}.\n\n"
        f"PASO 2 — INVESTIGACION RECURSIVA: a partir del primer hallazgo, "
        f"PROFUNDIZA con las tools que correspondan. Correlaciona entre capas: "
        f"si ves errores, busca su codigo TLNT y el correlation_id; si ves "
        f"degradacion de infra, revisa logs y anomalias; si ves fallos de auth, "
        f"verifica brute force. Reconstruye la causa raiz.\n\n"
        f"PASO 3 — VEREDICTO: determina si la alerta es un problema REAL o un "
        f"FALSO POSITIVO. Justifica con los datos.\n\n"
        f"{remediation}\n\n"
        f"PASO FINAL OBLIGATORIO — REPORTAR AL PANEL: llama UNA VEZ a "
        f"report_incident con tu conclusion: causa_raiz, confianza_pct (0-100), "
        f"categoria (infraestructura/aplicacion/base_datos/seguridad/red), "
        f"error_code (TLNT-XXX si aplica), requiere_remediacion (true solo si hay "
        f"problema real con accion correctiva), y playbook propuesto si aplica. "
        f"Registra el incidente en el Panel de Aprobacion AIOps. SIEMPRE reporta, "
        f"incluso si es falso positivo.\n\n"
        f"Responde estructurado: Hallazgo · Causa raiz · Veredicto · Accion propuesta."
    )


def list_elk_alerts() -> list:
    """Lista para el frontend — metadatos de cada alerta (sin el prompt)."""
    out = []
    for aid, spec in ELK_ALERTS.items():
        out.append({
            "id": aid,
            "title": spec["title"],
            "icon": spec["icon"],
            "subtitle": spec["subtitle"],
            "rule": spec["rule"],
            "severity": spec["alert"]["severity"],
            "metric": spec["alert"]["metric"],
            "resource": spec["alert"]["resource"],
            "payload": {"alert": spec["alert"]},
            "suggested_path": _suggested_path(spec["alert"]["metric"]),
        })
    return out


def get_elk_alert(alert_id: str) -> Optional[dict]:
    return ELK_ALERTS.get(alert_id)
