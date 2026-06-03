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
        "subtitle": "ERROR/WARN agrupados por error_code dedicado",
        "prompt": (
            "Detecta errores y warnings criticos en TALENTO de las ultimas "
            "{time_range_hours} horas. Ejecuta directamente el job template "
            "id={jt_errors_analysis} (talento-errors-analysis) con extra_vars_json="
            "'{{\"time_range_hours\": {time_range_hours}}}'. Cuando termine, "
            "sintetiza cuantos errores, cuantos warnings, top mensajes, codigos "
            "TLNT-XXX detectados. Para cada codigo TLNT cita su definicion "
            "consultando el catalogo TLNT via file_search. Indica los controllers "
            "afectados (logger_name). Reporta en espanol estructurado."
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
            "Reconstruye el viaje del correlation_id '{user_input}' en TALENTO "
            "sobre las ultimas {time_range_hours} horas.\n\n"
            "PASO 1: Consulta file_search con 'patron KQL trazabilidad "
            "correlation_id' para LEER el patron 3 documentado en la guia KQL. "
            "Extrae de ahi la query KQL.\n\n"
            "PASO 2: Ejecuta query_log_analytics pasando una QUERY KQL VALIDA "
            "que filtre por `tostring(p.correlation_id) == '{user_input}'` "
            "(despues de parse_json del campo Message) en ventana "
            "ago({time_range_hours}h), ordenada por TimeGenerated asc.\n\n"
            "PASO 3: Si en los resultados aparecen codigos TLNT-XXX en "
            "p.error_code o en el mensaje, consulta file_search con el codigo "
            "para citar su definicion del catalogo.\n\n"
            "Sintetiza la secuencia cronologica: entrada de la peticion, pasos "
            "ejecutados, donde fallo si hay ERROR/WARN, codigo TLNT con su "
            "explicacion. Reporta en espanol estructurado (Hallazgo, Hipotesis, "
            "Pasos, Accion)."
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
            "El operador pregunta: '{user_input}'.\n\n"
            "PASO 1: Consulta file_search con la pregunta exacta del operador "
            "para buscar en el catalogo de codigos TLNT-XXX (knowledge base).\n\n"
            "PASO 2: De la respuesta de file_search extrae para cada codigo "
            "encontrado: descripcion oficial, modulo origen, accion sugerida "
            "para soporte, solucion para usuario final. Cita textualmente del "
            "catalogo, no parafrases.\n\n"
            "Si el codigo no esta en el catalogo, indicalo claramente y sugiere "
            "validar con EAPPS. NO inventes significados de codigos. NO uses "
            "query_log_analytics para esto — file_search del catalogo es "
            "suficiente. Reporta en espanol estructurado."
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
            "TALENTO es regulado por SOX. El operador pide auditar la actividad "
            "por usuario de las ultimas {time_range_hours} horas. \n\n"
            "PASO 1: Consulta file_search con la pregunta 'patron KQL auditoria "
            "SOX por usuario' para LEER el patron 13 documentado en la guia KQL. "
            "(file_search devuelve markdown del knowledge base — extrae de ahi la "
            "query KQL).\n\n"
            "PASO 2: Toma la query KQL del patron 13, ajusta el time range a "
            "ago({time_range_hours}h), y ejecuta query_log_analytics pasando la "
            "QUERY KQL como argumento (NO pases texto de busqueda — el tool "
            "espera KQL valido contra ContainerInstanceLog_CL con parse_json "
            "del campo Message).\n\n"
            "PASO 3: Si aparecen codigos TLNT-XXX en los resultados, consulta "
            "file_search con el codigo (ej 'TLNT-008') para citar su definicion "
            "del catalogo.\n\n"
            "Sintetiza usuarios con mas actividad, acciones privilegiadas, "
            "anomalias. Reporta en espanol con enfasis en compliance."
        ),
        "expected_jt": None,
        "renderer": "sox",
        "pain_point": "Cumplimiento SOX por usuario",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },
    "brute-force": {
        "title": "Deteccion de Brute Force",
        "icon": "🛡️",
        "subtitle": "Intentos fallidos por usuario (TLNT-002/008/011)",
        "prompt": (
            "Detecta brute force en TALENTO sobre las ultimas {time_range_hours} "
            "horas, con umbral de {failed_threshold} fallos por usuario.\n\n"
            "PASO 1: Consulta file_search con 'patron KQL brute force por usuario' "
            "para LEER el patron 12 (markdown). Extrae de ahi la query KQL.\n\n"
            "PASO 2: Toma esa query, ajusta time range a ago({time_range_hours}h) "
            "y umbral a fails >= {failed_threshold}. Ejecuta query_log_analytics "
            "pasando la QUERY KQL como argumento. La query debe filtrar por "
            "`tostring(p.error_code) in ('TLNT-002','TLNT-008','TLNT-011')` "
            "(despues de parse_json del campo Message) y agrupar por "
            "tostring(p.usuario).\n\n"
            "PASO 3: Para cada usuario sospechoso, cita la definicion de los "
            "codigos TLNT involucrados consultando file_search.\n\n"
            "Sintetiza usuarios afectados, severidad (HIGH si fails >= 10, "
            "MEDIUM si >= 5, LOW si < 5), primer/ultimo intento, recomendacion "
            "(bloqueo, notificacion a SOC). Reporta en espanol."
        ),
        "expected_jt": None,
        "renderer": "brute-force",
        "pain_point": "Accesos no autorizados — TLNT-002/008/011",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours", "failed_threshold"],
        "tier": "primary",
    },
    "user-activity": {
        "title": "Actividad por Usuario",
        "icon": "👤",
        "subtitle": "Logins, acciones y errores de un usuario especifico",
        "prompt": (
            "El operador investiga la actividad del usuario '{user_input}' en "
            "TALENTO sobre las ultimas {time_range_hours} horas.\n\n"
            "PASO 1: Consulta file_search con 'patron KQL actividad por usuario' "
            "para LEER el patron 11. Extrae la query KQL del markdown.\n\n"
            "PASO 2: Ejecuta query_log_analytics pasando una query KQL VALIDA "
            "que filtre por `tostring(p.usuario) == '{user_input}'` despues de "
            "parse_json del campo Message, en ventana ago({time_range_hours}h). "
            "Devuelve los logs ordenados por TimeGenerated desc con: timestamp, "
            "level, error_code (de p.error_code), msg (de p.message), "
            "correlation_id, logger_name. Maximo 50 filas.\n\n"
            "PASO 3: Si aparecen codigos TLNT-XXX, consulta file_search con cada "
            "codigo para citar su definicion del catalogo.\n\n"
            "Sintetiza patron de actividad (cantidad de logins ok vs fail, "
            "errores tipicos, modulos visitados), señales de brute force "
            "(varios TLNT-002/008/011) o cuenta comprometida. Reporta en espanol "
            "estructurado (Hallazgo, Hipotesis, Pasos, Accion)."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Investigacion forense por usuario (campo `usuario` dedicado)",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Username a investigar",
        "free_text_placeholder": "Ej: jtorres, nvivas",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
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
