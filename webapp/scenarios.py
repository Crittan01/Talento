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
        "title": "Health Check",
        "icon": "🏥",
        "subtitle": "Estado de infraestructura — selecciona alcance",
        "prompt": (
            "El operador pide health check con alcance='{scope}'. Mapea:\n"
            "  - completo (default) -> id={jt_full_health_check} (talento-full-health-check)\n"
            "  - container -> id={jt_aci_state} (talento-aci-state)\n"
            "  - appservice -> id={jt_appservice_state} (talento-appservice-state)\n"
            "  - sql -> id={jt_sql_health} (talento-sql-health)\n\n"
            "Ejecuta directamente el job template correspondiente al alcance "
            "con extra_vars_json='{{}}'. Cuando termine, sintetiza:\n"
            "  - Si alcance=completo: estado de cada capa (ACI, App Service, SQL), "
            "veredicto global (HEALTHY/DEGRADED/CRITICAL) y recomendacion.\n"
            "  - Si alcance=container: nombre, state, restartCount, eventos.\n"
            "  - Si alcance=appservice: state, availability, host, ultimo deploy.\n"
            "  - Si alcance=sql: server status, databases (Online/Offline), tier, "
            "tamano usado.\n\n"
            "Indica si hay senales de problema. Reporta en espanol estructurado."
        ),
        "expected_jt": JT_IDS["jt_full_health_check"],
        "renderer": "generic",
        "pain_point": "Diagnostico de infraestructura con alcance configurable",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": ["scope"],
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
            "PASO 1: Llama UNA VEZ a la tool lookup_correlation_id con "
            "correlation_id='{user_input}' y time_range_hours={time_range_hours}. "
            "El bridge construye la KQL — NO escribas KQL, NO uses "
            "query_log_analytics.\n\n"
            "PASO 2: Si lookup_correlation_id devuelve 0 filas, reporta "
            "explicitamente 'no encontrado en la ventana' y sugiere al operador "
            "ampliar el rango o verificar el correlation_id. NO sigas explorando.\n\n"
            "PASO 3: Si hay filas y aparecen codigos TLNT-XXX en error_code o "
            "en msg, consulta file_search con el codigo (ej 'TLNT-008') para "
            "citar su definicion. NO llames a lookup_tlnt_code ni a otra tool "
            "de logs para esto — solo necesitas la definicion estatica.\n\n"
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
    "tlnt-explorer": {
        "title": "Codigos TLNT",
        "icon": "📚",
        "subtitle": "Ranking si esta vacio, definicion + instancias si das un codigo",
        "prompt": (
            "El operador escribio: '{user_input}'.\n\n"
            "Si el input esta VACIO: llama a tlnt_explorer con codigo='' y "
            "time_range_hours={time_range_hours}. La tool devuelve el ranking "
            "de codigos por frecuencia. Para los 3-5 mas frecuentes, consulta "
            "file_search con cada codigo para citar la definicion del catalogo. "
            "Sintetiza el ranking + las definiciones + recomendacion para mesa "
            "de ayuda.\n\n"
            "Si el input trae un codigo TLNT-XXX: "
            "(a) Consulta file_search con el codigo para extraer la definicion "
            "oficial del catalogo (descripcion, modulo, accion soporte, solucion "
            "usuario). NO inventes significados.\n"
            "(b) Llama a tlnt_explorer con codigo='{user_input}' y "
            "time_range_hours={time_range_hours} para ver instancias reales en "
            "el workspace. Si devuelve 0 filas, reporta 'sin ocurrencias en la "
            "ventana — el catalogo lo documenta pero no hay eventos hoy'.\n"
            "(c) Sintetiza: definicion oficial + cuantas ocurrencias + sample "
            "de correlation_ids para investigacion forense.\n\n"
            "Si el input es una pregunta libre ('que significa X', '¿cual es el "
            "mas frecuente?'), interpreta y dispatcha al modo correspondiente. "
            "Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Mesa de ayuda — ranking + definicion + instancias en una sola tarjeta",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Codigo TLNT (opcional) o deja vacio para ranking",
        "free_text_placeholder": "Ej: TLNT-008 (vacio = top ranking)",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # PENDING (3) — esperando que EAPPS habilite el dato que falta
    # ═══════════════════════════════════════════════════════════════════════
    "sox-audit": {
        "title": "Auditoria SOX por Usuario",
        "icon": "🔐",
        "subtitle": "Auditoria de accesos privilegiados con identidad estructurada",
        "prompt": (
            "Capacidad pendiente — la disponibilidad de campos identitarios "
            "estructurados (usuario, rol, accion privilegiada) requiere "
            "habilitacion en el ambiente reconstruido."
        ),
        "expected_jt": None,
        "renderer": "sox",
        "pain_point": "Cumplimiento SOX por usuario",
        "card_class": "card-critical",
        "free_text": True,
        "free_text_label": "Usuario a auditar",
        "free_text_placeholder": "Ej: jtorres, cmedina",
        "accepts_filters": ["time_range_hours"],
        "tier": "pending",
        "pending_eapps_reason": (
            "El ambiente reconstruido del sistema emite el campo `usuario` en "
            "el JSON estructurado de logs (verificado en su salida), pero el "
            "pipeline de ingesta hacia el workspace de Log Analytics no esta "
            "habilitado todavia. Una vez conectado, el escenario se activa "
            "automaticamente sin cambios. Para tener algun grado de auditoria "
            "por usuario HOY, ver 'Actividad por Usuario'."
        ),
    },
    "brute-force": {
        "title": "Deteccion de Brute Force",
        "icon": "🛡️",
        "subtitle": "Patron de auth fallida por usuario (TLNT-002/008/009/011)",
        "prompt": (
            "Capacidad pendiente — la disponibilidad de los codigos de "
            "autenticacion fallida agrupables por usuario requiere habilitacion "
            "del pipeline de logs del ambiente reconstruido."
        ),
        "expected_jt": None,
        "renderer": "brute-force",
        "pain_point": "Accesos no autorizados — TLNT-002/008/009/011",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["time_range_hours", "failed_threshold"],
        "tier": "pending",
        "pending_eapps_reason": (
            "La logica de bloqueo por intentos fallidos ya esta implementada en "
            "el ambiente reconstruido del sistema (verificado: emite TLNT-009 "
            "'Login bloqueado' tras N intentos TLNT-002/008). Pendiente de "
            "habilitar el pipeline de logs hacia el workspace para que el agente "
            "pueda detectar y reportar el patron en tiempo real."
        ),
    },
    "user-activity": {
        "title": "Actividad por Usuario",
        "icon": "👤",
        "subtitle": "Resumen agregado de actividad para un username",
        "prompt": (
            "Investigacion forense del usuario '{user_input}' en las ultimas "
            "{time_range_hours} horas.\n\n"
            "PASO 1: Llama UNA VEZ a la tool user_activity con usuario="
            "'{user_input}' y time_range_hours={time_range_hours}. El bridge usa "
            "el campo dedicado del JSON si esta poblado, o extrae el usuario del "
            "mensaje libre con regex. Devuelve agregado: eventos totales, "
            "errores, warns, codigos vistos, loggers, primera y ultima actividad.\n\n"
            "PASO 2: Si devuelve 0 filas, indica 'sin actividad del usuario en "
            "la ventana' y sugiere ampliar el rango o validar el username.\n\n"
            "PASO 3: Si hay actividad y aparecen codigos TLNT-XXX en el set "
            "'codigos', consulta file_search por cada codigo distinto para "
            "citar su definicion del catalogo.\n\n"
            "Sintetiza patron de actividad, errores tipicos, modulos visitados, "
            "y veredicto operacional. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Investigacion forense por usuario (cobertura ~2254 eventos/24h)",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Username a investigar",
        "free_text_placeholder": "Ej: jtorres, cmedina, jparra",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },
    "performance-analysis": {
        "title": "Analisis de Performance",
        "icon": "⏱️",
        "subtitle": "Latencia por endpoint, throughput, dependencias",
        "prompt": (
            "Capacidad pendiente — requiere telemetria aplicativa activa."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Lentitud generalizada (cierres de nomina, picos)",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "pending",
        "pending_eapps_reason": (
            "Requiere activacion de telemetria de Application Insights en "
            "el sistema: las tablas AppRequests, AppExceptions, AppDependencies, "
            "AppMetrics estan en cero filas en los ultimos 30 dias. Pendiente "
            "de habilitacion por el equipo de plataforma."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECONDARY — diagnostico granular + utilitarios
    # ═══════════════════════════════════════════════════════════════════════
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
        "pain_point": "Auto-remediacion con safety guard SOX (dry-run + doble confirmacion)",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": [],
        "tier": "primary",
    },
    "free-text": {
        "title": "Pregunta Libre",
        "icon": "🤖",
        "subtitle": "Escribe tu pregunta — el agente decide la tool",
        "prompt": None,  # se sustituye por el texto del usuario tal cual
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Flexibilidad operativa — el agente combina tools",
        "card_class": "card-neutral",
        "free_text": True,
        "free_text_label": "Pregunta libre al agente",
        "free_text_placeholder": "Ej: ¿Cuantos eventos hubo en la ultima hora?",
        "accepts_filters": [],
        "tier": "primary",
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
        # Para escenarios con template que ACEPTAN input vacio (ej tlnt-explorer
        # en modo ranking), permitimos texto vacio si el prompt es template.
        # Sin template + texto vacio sigue siendo invalido (no hay prompt que
        # mandar al agente).
        if not text and not (scenario["prompt"] and "{user_input}" in scenario["prompt"]):
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
