"""scenarios — catalogo del dashboard TALENTO.

Tres tiers de escenarios:
  - "primary":   foco principal de la demo (datos reales en LA + AWX)
  - "pending":   esperando que EAPPS resuelva hallazgos (campo `usuario` o
                 telemetria AppInsights). Se renderean disabled en la UI.
  - "secondary": utilitarios (diagnostico granular por capa, free-text).

Cuando EAPPS habilite los hallazgos faltantes, basta cambiar el `tier` de
"pending" a "primary" en el escenario correspondiente — el resto del codigo
(prompt, JT, renderer) ya esta listo.

Cada escenario define:
- id: identificador para la API
- title, icon, subtitle: lo que ve el usuario en la card
- prompt: instruccion al agente Foundry. Placeholders Python str.format:
  - {time_range_hours}, {failed_threshold} (filtros)
  - {jt_*} (JT IDs leidos de .env — config modular)
  - {user_input} (texto del usuario en escenarios free_text con prompt template)
- expected_jt: id de Job Template esperado (derivado de JT_IDS)
- renderer: que renderer del frontend se usa
- pain_point: a que pain point del RFP responde
- free_text: True si el usuario puede sustituir el prompt o llenar un slot
- free_text_label / free_text_placeholder: customizan el modal de input
- accepts_filters: lista de filtros aplicables ['time_range_hours', 'failed_threshold']
- tier: "primary" | "pending" | "secondary"
- pending_eapps_reason: solo si tier=="pending"
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


# Defaults globales si el filtro no viene del cliente
DEFAULT_FILTERS = {
    "time_range_hours": 24,
    "failed_threshold": 5,
}


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
        "jt_workspace_snapshot": int(env.get("AWX_JT_WORKSPACE_SNAPSHOT", 32)),
        "jt_errors_analysis":    int(env.get("AWX_JT_ERRORS_ANALYSIS", 33)),
        "jt_sox_audit":          int(env.get("AWX_JT_SOX_AUDIT", 34)),
        "jt_brute_force":        int(env.get("AWX_JT_BRUTE_FORCE", 35)),
        "jt_aci_state":          int(env.get("AWX_JT_ACI_STATE", 52)),
        "jt_appservice_state":   int(env.get("AWX_JT_APPSERVICE_STATE", 53)),
        "jt_sql_health":         int(env.get("AWX_JT_SQL_HEALTH", 54)),
        "jt_full_health_check":  int(env.get("AWX_JT_FULL_HEALTH_CHECK", 55)),
        "jt_aci_restart":        int(env.get("AWX_JT_ACI_RESTART", 56)),
        "jt_aci_stop":           int(env.get("AWX_JT_ACI_STOP", 57)),
        "jt_aci_start":          int(env.get("AWX_JT_ACI_START", 58)),
        "jt_appservice_restart": int(env.get("AWX_JT_APPSERVICE_RESTART", 59)),
    }


JT_IDS = _load_jt_ids_from_env()


SCENARIOS = {
    # ═══════════════════════════════════════════════════════════════════════
    # PRIMARY (6) — escenarios con datos reales en produccion
    # ═══════════════════════════════════════════════════════════════════════
    "infra-health-check": {
        "title": "Health Check Completo",
        "icon": "🏥",
        "subtitle": "Estado ACI + App Service + SQL en una corrida",
        "prompt": (
            "Ejecuta directamente el job template id={jt_full_health_check} "
            "(talento-full-health-check) con extra_vars_json='{{}}' para obtener "
            "panorama de salud completo de la infraestructura TALENTO. Cuando "
            "termine, sintetiza estado de cada capa (ACI, App Service, SQL), "
            "veredicto global (HEALTHY/DEGRADED/CRITICAL) y recomendacion "
            "concreta. Reporta en espanol estructurado."
        ),
        "expected_jt": JT_IDS["jt_full_health_check"],
        "renderer": "generic",
        "pain_point": "Vision panoramica de infraestructura",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
        "tier": "primary",
    },
    "system-status": {
        "title": "Estado del Sistema",
        "icon": "📊",
        "subtitle": "Inventario amplio del workspace de logs",
        "prompt": (
            "Ejecuta directamente el job template id={jt_workspace_snapshot} "
            "(talento-workspace-snapshot) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para obtener inventario completo del workspace "
            "de TALENTO en las ultimas {time_range_hours} horas. Cuando termine, "
            "sintetiza tablas pobladas, top tabla, filas, schema. Reporta en espanol."
        ),
        "expected_jt": JT_IDS["jt_workspace_snapshot"],
        "renderer": "snapshot",
        "pain_point": "Estrategia de monitoreo — vista panoramica",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },
    "errors-production": {
        "title": "Errores Recientes",
        "icon": "🚨",
        "subtitle": "ERROR/WARN agrupados + codigos TLNT activos",
        "prompt": (
            "Ejecuta directamente el job template id={jt_errors_analysis} "
            "(talento-errors-analysis) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para detectar errores y warnings criticos en "
            "TALENTO en las ultimas {time_range_hours} horas. Cuando termine, "
            "sintetiza cuantos errores, cuantos warnings, severity_status, top "
            "mensajes, codigos TLNT-XXX detectados (cita catalogo via file_search "
            "para cada uno). Reporta en espanol."
        ),
        "expected_jt": JT_IDS["jt_errors_analysis"],
        "renderer": "errors",
        "pain_point": "Mesa de ayuda sin RCA clara",
        "card_class": "card-alert",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },
    "correlation-trace": {
        "title": "Investigar Correlation ID",
        "icon": "🔍",
        "subtitle": "Reconstruir el viaje de una peticion especifica",
        "prompt": (
            "Reconstruye el viaje del correlation_id '{user_input}' en TALENTO. "
            "Primero consulta file_search con 'patrones KQL TALENTO' para obtener "
            "el patron 3 (trazabilidad por correlation_id). Luego ejecuta "
            "query_log_analytics con esa query filtrando por correlation_id="
            "'{user_input}' en las ultimas {time_range_hours} horas. Cuando "
            "termine, sintetiza la secuencia cronologica: timestamp de entrada, "
            "logger_name, level, mensaje. Si detectas codigos TLNT-XXX en algun "
            "log, busca su definicion en file_search y citala. Reporta en espanol "
            "estructurado (Hallazgo, Hipotesis, Pasos, Accion)."
        ),
        "expected_jt": None,  # usa query_log_analytics, no AWX
        "renderer": "generic",
        "pain_point": "Trazabilidad forense (99.5% correlation_id disponible)",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Pega el correlation_id (UUID)",
        "free_text_placeholder": "Ej: 8f660c47-e4dd-4e14-8bae-797916b00fda",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },
    "tlnt-lookup": {
        "title": "Consultar Codigo TLNT",
        "icon": "📚",
        "subtitle": "Significado oficial desde el catalogo",
        "prompt": (
            "El usuario pregunta sobre el codigo: '{user_input}'. Usa file_search "
            "con la pregunta exacta para buscar en el catalogo de codigos TLNT-XXX. "
            "Cita textualmente la descripcion, modulo origen, accion sugerida para "
            "soporte y solucion para usuario final. Si el codigo no esta en el "
            "catalogo, indicalo claramente y sugiere validar con EAPPS. NO inventes "
            "significados. Reporta en espanol estructurado."
        ),
        "expected_jt": None,  # solo file_search
        "renderer": "generic",
        "pain_point": "Demo de RAG sobre knowledge base (catalogo de 15 codigos)",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Codigo TLNT o pregunta",
        "free_text_placeholder": "Ej: TLNT-007 o '¿que significa TLNT-014?'",
        "accepts_filters": [],
        "tier": "primary",
    },
    "container-state": {
        "title": "Estado del Container",
        "icon": "📦",
        "subtitle": "Diagnostico del Azure Container Instance",
        "prompt": (
            "Ejecuta directamente el job template id={jt_aci_state} "
            "(talento-aci-state) con extra_vars_json='{{}}'. Cuando termine, "
            "sintetiza: nombre del container, state actual, restartCount, ultimo "
            "evento, recursos asignados. Indica si hay senales de problema "
            "(state != Running, restartCount alto, eventos BackOff/Failed)."
        ),
        "expected_jt": JT_IDS["jt_aci_state"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-container",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
        "tier": "primary",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # PENDING (3) — esperando que EAPPS habilite el dato que falta
    # ═══════════════════════════════════════════════════════════════════════
    "sox-audit": {
        "title": "Auditoria SOX por Usuario",
        "icon": "🔐",
        "subtitle": "Logins privilegiados + acciones criticas por usuario",
        "prompt": (
            "TALENTO es regulado por SOX. Ejecuta el job template id={jt_sox_audit} "
            "(talento-sox-audit) con extra_vars_json='{{\"time_range_hours\": "
            "{time_range_hours}}}' para auditar la actividad de las ultimas "
            "{time_range_hours} horas. Sintetiza audit_status, logins por usuario, "
            "acciones privilegiadas con rol, incidentes BD. Reporta en espanol con "
            "enfasis en compliance."
        ),
        "expected_jt": JT_IDS["jt_sox_audit"],
        "renderer": "sox",
        "pain_point": "Objetos no autorizados BD + cumplimiento SOX",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "pending",
        "pending_eapps_reason": (
            "Requiere campo `usuario` poblado en logs JSON estructurados "
            "(hoy 0/30488 logs lo traen). Sin esto, la auditoria 'quien hizo que' "
            "no es trazable."
        ),
    },
    "brute-force": {
        "title": "Deteccion de Brute Force",
        "icon": "🛡️",
        "subtitle": "Multiples intentos de login fallidos por usuario",
        "prompt": (
            "Detecta intentos de brute force en TALENTO. Ejecuta el job template "
            "id={jt_brute_force} (talento-brute-force-detector) con extra_vars_json="
            "'{{\"time_range_hours\": {time_range_hours}, \"failed_threshold\": "
            "{failed_threshold}}}' para identificar usuarios con {failed_threshold}+ "
            "intentos fallidos. Sintetiza usuarios sospechosos, severidad "
            "HIGH/MEDIUM/LOW, recomendacion de accion. Reporta en espanol."
        ),
        "expected_jt": JT_IDS["jt_brute_force"],
        "renderer": "brute-force",
        "pain_point": "Accesos no autorizados",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours", "failed_threshold"],
        "tier": "pending",
        "pending_eapps_reason": (
            "Requiere codigos TLNT-002/008/011 (autenticacion) en logs reales + "
            "campo `usuario` poblado. Hoy solo aparecen TLNT-001/003/004 y no hay "
            "info de usuario, el JT devolveria 0 hits."
        ),
    },
    "performance-analysis": {
        "title": "Analisis de Performance",
        "icon": "⏱️",
        "subtitle": "Latencia por endpoint, throughput, dependencias",
        "prompt": (
            "Analiza performance de TALENTO en las ultimas {time_range_hours} "
            "horas usando Application Insights. Ejecuta query_log_analytics "
            "contra AppRequests para latencia P50/P95/P99 por endpoint, contra "
            "AppDependencies para queries SQL lentas, contra AppExceptions para "
            "errores tipados. Sintetiza endpoints mas lentos, top excepciones, "
            "duracion promedio de queries. Reporta en espanol."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Lentitud generalizada (cierres de nomina, picos)",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "pending",
        "pending_eapps_reason": (
            "Requiere telemetria Application Insights activa: AppRequests, "
            "AppExceptions, AppDependencies, AppMetrics. Hoy las 8 tablas App* "
            "estan en 0 rows hace 30+ dias — TALENTO no envia telemetria."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECONDARY — diagnostico granular + utilitarios
    # ═══════════════════════════════════════════════════════════════════════
    "appservice-state": {
        "title": "Estado del App Service",
        "icon": "🌐",
        "subtitle": "Diagnostico del Azure App Service (API)",
        "prompt": (
            "Ejecuta directamente el job template id={jt_appservice_state} "
            "(talento-appservice-state) con extra_vars_json='{{}}'. Sintetiza: "
            "estado del App Service, availability, host name. Indica problemas."
        ),
        "expected_jt": JT_IDS["jt_appservice_state"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-API",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
        "tier": "secondary",
    },
    "sql-health": {
        "title": "Salud de Base de Datos",
        "icon": "🗄️",
        "subtitle": "Estado SQL Server y bases de datos",
        "prompt": (
            "Ejecuta directamente el job template id={jt_sql_health} "
            "(talento-sql-health) con extra_vars_json='{{}}'. Sintetiza SQL "
            "Server, lista de databases con status, tier/SKU, tamano max."
        ),
        "expected_jt": JT_IDS["jt_sql_health"],
        "renderer": "generic",
        "pain_point": "Diagnostico foco-BD",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
        "tier": "secondary",
    },
    "auto-remediate-restart": {
        "title": "Auto-Remediacion: Restart",
        "icon": "🔧",
        "subtitle": "Reiniciar Container (DRY-RUN — safety pattern)",
        "prompt": (
            "Ejecuta directamente el job template id={jt_aci_restart} "
            "(talento-aci-restart) con extra_vars_json='{{\"dry_run\": true, "
            "\"reason\": \"Auto-remediacion propuesta por agente IA via dashboard\"}}'. "
            "Esto NO va a reiniciar realmente. Sintetiza estado actual, accion que "
            "SE EJECUTARIA, URL del API. Indica al usuario que para ejecutar real "
            "se requiere confirmacion via operator_confirmed (safety guard del bridge)."
        ),
        "expected_jt": JT_IDS["jt_aci_restart"],
        "renderer": "generic",
        "pain_point": "Demo de auto-remediacion con safety guard",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": [],
        "tier": "secondary",
    },
    "free-text": {
        "title": "Pregunta Libre",
        "icon": "🤖",
        "subtitle": "Escribe tu pregunta — el agente decide la tool",
        "prompt": None,  # se sustituye por el texto del usuario tal cual
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Flexibilidad operativa",
        "card_class": "card-neutral",
        "free_text": True,
        "free_text_label": "Pregunta libre al agente",
        "free_text_placeholder": "Ej: ¿Cuantos eventos hubo en la ultima hora?",
        "accepts_filters": [],
        "tier": "secondary",
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
            "free_text_label": s.get("free_text_label", "Pregunta libre al agente"),
            "free_text_placeholder": s.get("free_text_placeholder",
                                           "Escribe tu pregunta..."),
            "renderer": s["renderer"],
            "accepts_filters": s.get("accepts_filters", []),
            "tier": s.get("tier", "primary"),
            "pending_eapps_reason": s.get("pending_eapps_reason"),
        })
    return out


def resolve_prompt(
    scenario_id: str,
    free_text: Optional[str] = None,
    filters: Optional[dict] = None,
) -> Optional[str]:
    """Devuelve el prompt final para enviar al agente, con filtros aplicados.

    - Escenarios pre-canned (free_text=False): sustituye placeholders del prompt
      con filters + JT_IDS + DEFAULT_FILTERS.
    - Escenarios free-text con prompt template (free_text=True, prompt
      contiene {user_input}): inyecta el texto del usuario en el slot
      `{user_input}` y aplica el resto de placeholders.
    - Escenarios free-text sin template (free_text=True, prompt=None):
      devuelve el texto del usuario tal cual.
    - Escenarios pending: devuelve None (la UI los renderea disabled y /api/run
      los rechaza con 400).
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        return None

    # Bloqueo de pending: el caller (app.py) debe detectar esto y devolver 400
    if scenario.get("tier") == "pending":
        return None

    if scenario["free_text"]:
        text = (free_text or "").strip()
        if not text:
            return None
        # Si el prompt es template (tiene {user_input}), inyecta el texto
        if scenario["prompt"] and "{user_input}" in scenario["prompt"]:
            effective = {**DEFAULT_FILTERS, **JT_IDS, **(filters or {}),
                         "user_input": text}
            try:
                return scenario["prompt"].format(**effective)
            except (KeyError, ValueError):
                return scenario["prompt"]
        # Sin template: devolver el texto del usuario crudo
        return text

    # Escenario pre-canned: aplicar filtros + JT IDs + defaults
    effective = {**DEFAULT_FILTERS, **JT_IDS, **(filters or {})}
    try:
        return scenario["prompt"].format(**effective)
    except (KeyError, ValueError):
        return scenario["prompt"]


def get_default_filters() -> dict:
    """Expone DEFAULT_FILTERS al cliente (para inicializar la UI)."""
    return dict(DEFAULT_FILTERS)


def is_pending(scenario_id: str) -> bool:
    """True si el escenario esta esperando que EAPPS habilite datos."""
    s = get_scenario(scenario_id)
    return bool(s and s.get("tier") == "pending")
