"""scenarios — catalogo de los 6 escenarios pre-canned del dashboard.

Cada escenario define:
- id: identificador para la API
- title, icon, subtitle: lo que ve el usuario en la card
- prompt: instruccion al agente Foundry. Acepta placeholders Python str.format:
  - {time_range_hours}, {failed_threshold} (filtros de usuario)
  - {jt_workspace_snapshot}, {jt_errors_analysis}, {jt_sox_audit},
    {jt_brute_force} (JT IDs leidos de .env — config modular)
- expected_jt: id de Job Template esperado (derivado de JT_IDS)
- renderer: que renderer del frontend se usa
- pain_point: a que pain point del RFP responde
- free_text: True si el usuario puede sustituir el prompt
- accepts_filters: lista de filtros aplicables ['time_range_hours', 'failed_threshold']
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


# Defaults globales si el filtro no viene del cliente
DEFAULT_FILTERS = {
    "time_range_hours": 24,
    "failed_threshold": 5,
}


# ---------------------------------------------------------------------------
# JT IDs configurables via .env (config modular). Permite alternar AWX local
# vs Azure cambiando solo el .env, sin tocar codigo ni prompts.
# ---------------------------------------------------------------------------
def _load_jt_ids_from_env() -> dict:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return {
        # Analisis de logs
        "jt_workspace_snapshot": int(env.get("AWX_JT_WORKSPACE_SNAPSHOT", 32)),
        "jt_errors_analysis":    int(env.get("AWX_JT_ERRORS_ANALYSIS", 33)),
        "jt_sox_audit":          int(env.get("AWX_JT_SOX_AUDIT", 34)),
        "jt_brute_force":        int(env.get("AWX_JT_BRUTE_FORCE", 35)),
        # Diagnostico de infraestructura (no invasivos)
        "jt_aci_state":          int(env.get("AWX_JT_ACI_STATE", 52)),
        "jt_appservice_state":   int(env.get("AWX_JT_APPSERVICE_STATE", 53)),
        "jt_sql_health":         int(env.get("AWX_JT_SQL_HEALTH", 54)),
        "jt_full_health_check":  int(env.get("AWX_JT_FULL_HEALTH_CHECK", 55)),
        # Remediacion (dry_run=true por defecto en playbook)
        "jt_aci_restart":        int(env.get("AWX_JT_ACI_RESTART", 56)),
        "jt_aci_stop":           int(env.get("AWX_JT_ACI_STOP", 57)),
        "jt_aci_start":          int(env.get("AWX_JT_ACI_START", 58)),
        "jt_appservice_restart": int(env.get("AWX_JT_APPSERVICE_RESTART", 59)),
    }


JT_IDS = _load_jt_ids_from_env()


SCENARIOS = {
    "system-status": {
        "title": "Estado del Sistema",
        "icon": "📊",
        "subtitle": "Inventario amplio del workspace",
        "prompt": (
            "Ejecuta directamente el job template id={jt_workspace_snapshot} "
            "(talento-workspace-snapshot) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para obtener un inventario completo del "
            "workspace de TALENTO en las últimas {time_range_hours} horas. "
            "Cuando termine, sintetiza los hallazgos: tablas pobladas, top "
            "tabla, filas, schema, muestra. Reporta en español estructurado."
        ),
        "expected_jt": JT_IDS["jt_workspace_snapshot"],
        "renderer": "snapshot",
        "pain_point": "(5) Estrategia de monitoreo — vista panorámica",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
    },
    "errors-production": {
        "title": "Errores en Producción",
        "icon": "🚨",
        "subtitle": "Detección y análisis de ERROR/WARN críticos",
        "prompt": (
            "Ejecuta directamente el job template id={jt_errors_analysis} "
            "(talento-errors-analysis) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para detectar errores y warnings críticos en "
            "TALENTO en las últimas {time_range_hours} horas. Cuando termine, "
            "sintetiza: cuántos errores, cuántos warnings, severity_status, top "
            "mensajes, containers afectados. Reporta en español."
        ),
        "expected_jt": JT_IDS["jt_errors_analysis"],
        "renderer": "errors",
        "pain_point": "Mesa de ayuda sin RCA clara",
        "card_class": "card-alert",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
    },
    "sox-audit": {
        "title": "Auditoría SOX",
        "icon": "🔐",
        "subtitle": "Quién accedió, qué aprobó, incidentes BD",
        "prompt": (
            "TALENTO es regulado por SOX. Ejecuta directamente el job template "
            "id={jt_sox_audit} (talento-sox-audit) con extra_vars_json="
            "'{{\"time_range_hours\": {time_range_hours}}}' para auditar la "
            "actividad de las últimas {time_range_hours} horas. Cuando termine, "
            "sintetiza: audit_status, logins por usuario, acciones privilegiadas "
            "(rol=LIDER, aprobaciones), incidentes de seguridad BD (failed SQL "
            "logins). Reporta en español con énfasis en compliance."
        ),
        "expected_jt": JT_IDS["jt_sox_audit"],
        "renderer": "sox",
        "pain_point": "Objetos no autorizados BD + cumplimiento SOX",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
    },
    "brute-force": {
        "title": "Detección de Brute Force",
        "icon": "🛡️",
        "subtitle": "Múltiples intentos de login fallidos por usuario",
        "prompt": (
            "Detecta intentos de brute force en TALENTO. Ejecuta directamente el "
            "job template id={jt_brute_force} (talento-brute-force-detector) con "
            "extra_vars_json='{{\"time_range_hours\": {time_range_hours}, "
            "\"failed_threshold\": {failed_threshold}}}' para identificar usuarios "
            "con {failed_threshold}+ intentos fallidos en {time_range_hours} horas. "
            "Cuando termine, sintetiza: usuarios sospechosos, severidad HIGH/MEDIUM/LOW, "
            "recomendación de acción. Reporta en español."
        ),
        "expected_jt": JT_IDS["jt_brute_force"],
        "renderer": "brute-force",
        "pain_point": "Accesos no autorizados (foco específico)",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours", "failed_threshold"],
    },
    "payroll-slow": {
        "title": "Lentitud Cierre Nómina",
        "icon": "⏱️",
        "subtitle": "Errores y degradación durante cierre mensual",
        "prompt": (
            "Hoy es día de cierre de nómina en TALENTO y se reportó lentitud. "
            "Ejecuta directamente el job template id={jt_errors_analysis} "
            "(talento-errors-analysis) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para detectar errores recientes en las últimas "
            "{time_range_hours} horas. Sintetiza: errores SQL/Hibernate, containers "
            "afectados, hipótesis de causa raíz asociada al cierre (conexiones BD "
            "saturadas, queries lentas, etc.). Reporta en español orientado a "
            "operaciones."
        ),
        "expected_jt": JT_IDS["jt_errors_analysis"],
        "renderer": "errors",
        "pain_point": "Lentitud generalizada en cierres de nómina",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
    },
    # ──────────────────────────────────────────────────────────────
    # AUTO-REMEDIACION — diagnostico de infraestructura (no invasivo)
    # ──────────────────────────────────────────────────────────────
    "infra-health-check": {
        "title": "Health Check Completo",
        "icon": "🏥",
        "subtitle": "Estado ACI + App Service + SQL en una sola corrida",
        "prompt": (
            "Ejecuta directamente el job template id={jt_full_health_check} "
            "(talento-full-health-check) con extra_vars_json='{{}}' para obtener "
            "un panorama de salud completo de la infraestructura de TALENTO. "
            "Cuando termine, sintetiza: estado de cada capa (ACI, App Service, "
            "SQL), veredicto global (HEALTHY/DEGRADED/CRITICAL) y recomendacion "
            "concreta sobre proximos pasos. Reporta en espanol estructurado."
        ),
        "expected_jt": JT_IDS["jt_full_health_check"],
        "renderer": "generic",
        "pain_point": "Vision panoramica de infraestructura (caso de uso 4.1)",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
    },
    "container-state": {
        "title": "Estado del Container",
        "icon": "📦",
        "subtitle": "Diagnostico detallado del Azure Container Instance",
        "prompt": (
            "Ejecuta directamente el job template id={jt_aci_state} "
            "(talento-aci-state) con extra_vars_json='{{}}'. Cuando termine, "
            "sintetiza: nombre del container, state actual (Running/...), "
            "restartCount, ultimo evento, recursos asignados. Indica si hay "
            "senales de problema (state != Running, restartCount alto, eventos "
            "BackOff/Failed)."
        ),
        "expected_jt": JT_IDS["jt_aci_state"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-container (caso de uso 4.1)",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
    },
    "appservice-state": {
        "title": "Estado del App Service",
        "icon": "🌐",
        "subtitle": "Diagnostico del Azure App Service (API backend)",
        "prompt": (
            "Ejecuta directamente el job template id={jt_appservice_state} "
            "(talento-appservice-state) con extra_vars_json='{{}}'. Cuando "
            "termine, sintetiza: estado del App Service (Running/Stopped), "
            "availability (Normal/Limited/...), host name, ultimo modify. "
            "Indica si hay senales de problema."
        ),
        "expected_jt": JT_IDS["jt_appservice_state"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-API (caso de uso 4.1)",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
    },
    "sql-health": {
        "title": "Salud de Base de Datos",
        "icon": "🗄️",
        "subtitle": "Estado del SQL Server y bases de datos",
        "prompt": (
            "Ejecuta directamente el job template id={jt_sql_health} "
            "(talento-sql-health) con extra_vars_json='{{}}'. Cuando termine, "
            "sintetiza: SQL Server name + fqdn, lista de databases con su "
            "status (Online/...), tier/SKU (S2, S3, etc.) y tamaño max. "
            "Indica si hay algo no-Online o alguna DB cerca del limite."
        ),
        "expected_jt": JT_IDS["jt_sql_health"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-BD (caso de uso 4.1)",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
    },
    # ──────────────────────────────────────────────────────────────
    # AUTO-REMEDIACION — accion (DRY-RUN por defecto)
    # ──────────────────────────────────────────────────────────────
    "auto-remediate-restart": {
        "title": "Auto-Remediación: Restart",
        "icon": "🔧",
        "subtitle": "Reiniciar Container (DRY-RUN — confirma antes de ejecutar)",
        "prompt": (
            "Ejecuta directamente el job template id={jt_aci_restart} "
            "(talento-aci-restart) con extra_vars_json='{{\"dry_run\": true, "
            "\"reason\": \"Auto-remediacion propuesta por agente IA via "
            "dashboard\"}}'. Esto NO va a reiniciar el container realmente — "
            "es una simulacion (dry-run). Cuando termine, sintetiza: estado "
            "actual del container, accion que SE EJECUTARIA si dry_run fuera "
            "false, URL del API que se llamaria, e indica claramente al usuario "
            "que para ejecutar de verdad debe re-correr con dry_run=false "
            "(operacion bajo su responsabilidad)."
        ),
        "expected_jt": JT_IDS["jt_aci_restart"],
        "renderer": "generic",
        "pain_point": "Demo de auto-remediacion con safety pattern",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": [],
    },
    "free-text": {
        "title": "Pregunta Libre",
        "icon": "🤖",
        "subtitle": "Escribe tu pregunta — el agente decide la tool",
        "prompt": None,  # se sustituye por el texto del usuario
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Flexibilidad operativa",
        "card_class": "card-neutral",
        "free_text": True,
        "accepts_filters": [],
    },
}


def get_scenario(scenario_id: str) -> Optional[dict]:
    return SCENARIOS.get(scenario_id)


def list_scenarios() -> list:
    """Devuelve la lista en orden para el frontend, sin el prompt completo."""
    out = []
    for sid, s in SCENARIOS.items():
        out.append({
            "id": sid,
            "title": s["title"],
            "icon": s["icon"],
            "subtitle": s["subtitle"],
            "pain_point": s["pain_point"],
            "card_class": s["card_class"],
            "free_text": s["free_text"],
            "renderer": s["renderer"],
            "accepts_filters": s.get("accepts_filters", []),
        })
    return out


def resolve_prompt(
    scenario_id: str,
    free_text: Optional[str] = None,
    filters: Optional[dict] = None,
) -> Optional[str]:
    """Devuelve el prompt final para enviar al agente, con filtros aplicados.

    Para escenarios pre-canned: sustituye placeholders del prompt con los
    valores del dict `filters`. Si un placeholder no viene en filters, usa
    el valor de DEFAULT_FILTERS.
    Para 'free-text': devuelve el texto del usuario (debe venir).
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        return None
    if scenario["free_text"]:
        return (free_text or "").strip() or None

    # Aplicar filtros (con fallback a defaults) + JT IDs configurados en .env.
    # JT_IDS no es override-able por el usuario — es config del entorno.
    effective = {**DEFAULT_FILTERS, **JT_IDS, **(filters or {})}
    try:
        return scenario["prompt"].format(**effective)
    except (KeyError, ValueError):
        return scenario["prompt"]


def get_default_filters() -> dict:
    """Expone DEFAULT_FILTERS al cliente (para inicializar la UI)."""
    return dict(DEFAULT_FILTERS)
