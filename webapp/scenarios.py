"""scenarios — catalogo del dashboard TALENTO v21.

Tiers:
  - "primary":   escenarios operativos con datos reales.
  - "secondary": utilitarios / demos de capacidades especificas.

Cada escenario define:
- id, title, icon, subtitle, prompt, renderer, pain_point, tier
- free_text: True si el usuario ingresa texto en el modal
- accepts_filters: lista de filtros aplicables
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


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
        # Remediaciones de compute (invasivas)
        "jt_aci_restart":             int(env.get("AWX_JT_ACI_RESTART", 56)),
        "jt_aci_stop":                int(env.get("AWX_JT_ACI_STOP", 57)),
        "jt_aci_start":               int(env.get("AWX_JT_ACI_START", 58)),
        "jt_appservice_restart":      int(env.get("AWX_JT_APPSERVICE_RESTART", 59)),
        # Remediaciones de configuracion (dry_run=true por defecto)
        "jt_sql_diagnostics_enable":  int(env.get("AWX_JT_SQL_DIAGNOSTICS_ENABLE", 61)),
        "jt_nsg_block_ip":            int(env.get("AWX_JT_NSG_BLOCK_IP", 62)),
    }


JT_IDS = _load_jt_ids_from_env()


SCENARIOS = {
    # ═══════════════════════════════════════════════════════════════════════
    # PRIMARY — escenarios operativos con datos reales
    # ═══════════════════════════════════════════════════════════════════════

    "infra-health-check": {
        "title": "System Health",
        "icon": "🏥",
        "subtitle": "Infraestructura completa — Container, App Service, SQL, Storage, Red",
        "prompt": (
            "El operador pide health check con alcance='{scope}'.\n\n"
            "Mapeo de alcances:\n"
            "  - completo (default): llama lookup_infrastructure mode='full' Y "
            "    lookup_sql para estado completo de todas las capas.\n"
            "  - container: llama lookup_infrastructure mode='aci'.\n"
            "  - appservice: llama lookup_infrastructure mode='appservice'.\n"
            "  - sql: llama lookup_sql.\n"
            "  - storage: llama lookup_infrastructure mode='storage'.\n"
            "  - network: llama lookup_infrastructure mode='network'.\n"
            "  - quotas: llama lookup_infrastructure mode='quotas'.\n\n"
            "Ejecuta con resource_group='' (usa el configurado por defecto). "
            "Sintetiza:\n"
            "  - completo: veredicto global HEALTHY/DEGRADED/CRITICAL por capa "
            "    (ACI, App Service, SQL, Storage, Quotas) + recomendacion.\n"
            "  - container: state, restartCount, eventos recientes.\n"
            "  - appservice: state, availability, hostname.\n"
            "  - sql: servers, databases (status/tier/size).\n"
            "  - storage: cuentas con https_only compliance.\n"
            "  - network: NSG rules con acceso abierto.\n"
            "  - quotas: vCPUs y container groups used/limit.\n\n"
            "PASO EXTRA (solo si alcance=completo y hay DEGRADED o CRITICAL): "
            "llama tlnt_explorer con codigo='' y time_range_hours=3 para ver "
            "si hay errores recientes que expliquen la degradacion. "
            "Incluye los top codigos TLNT en el resumen.\n\n"
            "Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "health",
        "pain_point": "Diagnostico completo de infraestructura — Container, App Service, SQL, Storage, Red",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": ["scope"],
        "tier": "primary",
    },

    "errors-production": {
        "title": "Errores Recientes",
        "icon": "🚨",
        "subtitle": "ERROR/WARN agrupados — top codigos TLNT con definicion",
        "prompt": (
            "Detecta errores y warnings criticos en TALENTO de las ultimas "
            "{time_range_hours} horas.\n\n"
            "PASO 1: Llama a tlnt_explorer con codigo='' y "
            "time_range_hours={time_range_hours} para obtener el ranking "
            "de codigos de error por frecuencia.\n\n"
            "PASO 2: Para los 3-5 codigos mas frecuentes, consulta file_search "
            "con cada codigo para citar su definicion oficial del catalogo.\n\n"
            "PASO 3: Sintetiza: cuantos errores, cuantos warnings, top codigos "
            "TLNT con su definicion y controladores afectados (logger_name). "
            "Indica el nivel de severidad global. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "errors",
        "pain_point": "Mesa de ayuda sin RCA clara — top errores con definicion en una sola tarjeta",
        "card_class": "card-alert",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },

    "anomaly-scan": {
        "title": "Scan de Anomalias",
        "icon": "📈",
        "subtitle": "Deteccion estadistica de picos y caidas anomalas",
        "prompt": (
            "Escanea anomalias estadisticas en TALENTO en las ultimas "
            "{time_range_hours} horas.\n\n"
            "PASO 1: Llama a detect_anomalies con metric_type='error_rate' y "
            "time_range_hours={time_range_hours}.\n\n"
            "PASO 2: Llama a detect_anomalies con metric_type='auth_failures' y "
            "time_range_hours={time_range_hours}.\n\n"
            "PASO 3 (solo si hay SPIKES en auth_failures): Llama a "
            "lookup_runtime_logs con modo='brute_force' para identificar "
            "usuarios sospechosos activos.\n\n"
            "PASO 4 (solo si hay SPIKES en error_rate o auth_failures): Llama a "
            "detect_anomalies con metric_type='request_volume' para correlacionar "
            "si hubo pico de trafico simultaneo.\n\n"
            "PASO 5 (solo si hay SPIKE en error_rate): Llama a tlnt_explorer "
            "con codigo='' y time_range_hours={time_range_hours} para identificar "
            "que codigos TLNT aumentaron en la ventana del spike.\n\n"
            "Sintetiza: para cada metrica, cuantas anomalias, timestamps, "
            "SPIKE vs DIP, score maximo. Si hay correlacion entre metricas "
            "(spike de requests + spike de errores simultaneo) indicalo "
            "como hallazgo prioritario. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Deteccion proactiva de comportamiento anomalo via ML estadistico",
        "card_class": "card-warning",
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
            "en msg, consulta file_search con el codigo para citar su definicion. "
            "NO llames a tlnt_explorer ni a otra tool de logs para esto.\n\n"
            "Sintetiza la secuencia cronologica: entrada de la peticion, pasos "
            "ejecutados, donde fallo si hay ERROR/WARN, codigo TLNT con su "
            "explicacion. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Trazabilidad forense por peticion HTTP",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Pega el correlation_id (UUID o hex 32)",
        "free_text_placeholder": "Ej: 951db4dc-e5c7-49a6-85a1-b1135caffd1c",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },

    "tlnt-explorer": {
        "title": "Codigos TLNT",
        "icon": "📚",
        "subtitle": "Ranking si vacio, definicion + instancias si das un codigo",
        "prompt": (
            "El operador escribio: '{user_input}'.\n\n"
            "Si el input esta VACIO: llama a tlnt_explorer con codigo='' y "
            "time_range_hours={time_range_hours}. La tool devuelve el ranking "
            "de codigos por frecuencia. Para los 3-5 mas frecuentes, consulta "
            "file_search con cada codigo para citar la definicion del catalogo. "
            "Sintetiza el ranking + definiciones + recomendacion para mesa de ayuda.\n\n"
            "Si el input trae un codigo TLNT-XXX:\n"
            "(a) Consulta file_search con el codigo para extraer la definicion "
            "oficial (descripcion, modulo, accion soporte, solucion usuario).\n"
            "(b) Llama a tlnt_explorer con codigo='{user_input}' y "
            "time_range_hours={time_range_hours} para ver instancias reales. "
            "Si devuelve 0 filas, reporta 'sin ocurrencias en la ventana'.\n"
            "(c) Sintetiza: definicion oficial + ocurrencias + sample de "
            "correlation_ids para investigacion forense.\n\n"
            "Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Mesa de ayuda — ranking + definicion + instancias en una tarjeta",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Codigo TLNT (opcional) o deja vacio para ranking",
        "free_text_placeholder": "Ej: TLNT-008 (vacio = top ranking)",
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },

    "sox-audit": {
        "title": "Auditoria SOX por Usuario",
        "icon": "🔐",
        "subtitle": "Actividad reciente, risk score y codigos TLNT del usuario",
        "prompt": (
            "Audita la actividad del usuario '{user_input}' en TALENTO en "
            "las ultimas 3 horas.\n\n"
            "PASO 1: Llama a lookup_runtime_logs con modo='user_audit', "
            "usuario='{user_input}', minutos=180.\n\n"
            "PASO 2: Si la tool devuelve 0 filas, indica 'sin actividad de "
            "{user_input} en las ultimas 3 horas' y sugiere validar el username.\n\n"
            "PASO 3: Si aparecen codigos TLNT, consulta file_search por cada "
            "codigo distinto para citar la definicion del catalogo.\n\n"
            "Sintetiza con enfasis SOX: total eventos, ratio errores/warns, "
            "codigos vistos con su definicion, primera y ultima actividad, "
            "loggers (controllers tocados), y veredicto operacional "
            "(HIGH >=20%, MEDIUM >=10%, LOW <10%).\n\n"
            "PASO 4 (solo si veredicto HIGH): llama detect_anomalies con "
            "metric_type='auth_failures' y time_range_hours=6 para ver si el "
            "patron de fallos del usuario es sistemico o puntual. "
            "Incluye la conclusion en el resumen.\n\n"
            "Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Cumplimiento SOX por usuario con identidad estructurada",
        "card_class": "card-info",
        "free_text": True,
        "free_text_label": "Usuario a auditar",
        "free_text_placeholder": "Ej: nvivas, cmedina, jtorres",
        "accepts_filters": [],
        "tier": "primary",
    },

    "brute-force": {
        "title": "Deteccion de Brute Force",
        "icon": "🛡️",
        "subtitle": f"Usuarios con fallos de auth sobre umbral (TLNT-002/008/009/011)",
        "prompt": (
            "Detecta usuarios con patron de fuerza bruta en TALENTO "
            "(ultimas 3 horas) con umbral >={failed_threshold} fallos.\n\n"
            "PASO 1: Llama a lookup_runtime_logs con modo='brute_force', "
            "usuario='', minutos=180, threshold={failed_threshold}.\n\n"
            "PASO 2: Si devuelve 0 filas, indica 'sin patrones de fuerza "
            "bruta en las ultimas 3 horas con umbral >={failed_threshold}'.\n\n"
            "PASO 3: Para cada usuario sospechoso, consulta file_search por "
            "los codigos TLNT involucrados para citar su definicion.\n\n"
            "Sintetiza: usuarios sospechosos con severidad (HIGH >=10, "
            "MEDIUM >=5, LOW >=3), codigos involucrados, velocidad de ataque, "
            "recomendacion. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Deteccion de accesos no autorizados en tiempo real",
        "card_class": "card-critical",
        "free_text": False,
        "accepts_filters": ["failed_threshold"],
        "tier": "primary",
    },

    "user-activity": {
        "title": "Actividad por Usuario",
        "icon": "👤",
        "subtitle": "Resumen agregado de actividad para un username",
        "prompt": (
            "Investigacion forense del usuario '{user_input}' en las ultimas "
            "{time_range_hours} horas.\n\n"
            "PASO 1: Llama UNA VEZ a la tool user_activity con usuario="
            "'{user_input}' y time_range_hours={time_range_hours}.\n\n"
            "PASO 2: Si devuelve 0 filas, indica 'sin actividad del usuario en "
            "la ventana' y sugiere ampliar el rango o validar el username.\n\n"
            "PASO 3: Si hay actividad y aparecen codigos TLNT-XXX, consulta "
            "file_search por cada codigo distinto para citar su definicion.\n\n"
            "Sintetiza patron de actividad, errores tipicos, modulos visitados, "
            "y veredicto operacional. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Investigacion forense por usuario en ventana historica",
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
        "subtitle": "Latencia, errores HTTP, throughput y dependencias lentas",
        "prompt": (
            "Analiza la performance aplicativa de TALENTO en las ultimas "
            "{time_range_hours} horas.\n\n"
            "PASO 1: Llama a lookup_app_insights con modo='top_endpoints' y "
            "time_range_hours={time_range_hours}.\n\n"
            "PASO 2: Si hay endpoints con P95 alta (>1000 ms), llama a "
            "lookup_app_insights con modo='latency_p95'.\n\n"
            "PASO 3: Llama a lookup_app_insights con modo='errors_5xx'.\n\n"
            "PASO 4: Si se detectan errores o latencia anomala, llama a "
            "lookup_app_insights con modo='slow_deps' para dependencias lentas.\n\n"
            "Sintetiza: top 3 endpoints con carga + latencia, anomalias "
            "(error rate >1% o P95 >1s), dependencias lentas si aplica, "
            "recomendaciones. Reporta en espanol estructurado."
        ),
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Lentitud generalizada — latencia, HTTP errors, dependencias",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": ["time_range_hours"],
        "tier": "primary",
    },

    "free-text": {
        "title": "Pregunta Libre",
        "icon": "🤖",
        "subtitle": "Escribe tu pregunta — el agente decide la tool",
        "prompt": None,
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Flexibilidad operativa — el agente combina tools",
        "card_class": "card-neutral",
        "free_text": True,
        "free_text_label": "Pregunta libre al agente",
        "free_text_placeholder": "Ej: ¿Cuantos eventos tuvo nvivas en la ultima hora?",
        "accepts_filters": [],
        "tier": "primary",
    },

    "sql-diagnostics-enable": {
        "title": "Habilitar Diagnósticos SQL",
        "icon": "🗄️",
        "subtitle": "Activa QueryStore, Blocks, Deadlocks → Log Analytics (dry-run por defecto)",
        "prompt": (
            "lookup_sql() mostró que los diagnostic settings de SQL no están activos "
            "(diagnostics.available=false). Proponer habilitarlos.\n\n"
            "PASO 1: Confirma el estado ejecutando lookup_sql() para mostrar el mensaje "
            "de configuración pendiente.\n\n"
            "PASO 2: Propone al operador lanzar el job template "
            f"{JT_IDS['jt_sql_diagnostics_enable']} (talento-sql-diagnostics-enable) "
            "con extra_vars_json='{\"dry_run\": true}'. Esto mostrará exactamente qué "
            "se configuraría sin tocar Azure.\n\n"
            "PASO 3: Sintetiza qué categorías se habilitarían (SQLInsights, QueryStore, "
            "Blocks, Deadlocks) y qué datos estarán disponibles en lookup_sql() "
            "una vez activado (~15 min de latencia inicial).\n\n"
            "Indica que para ejecutar de verdad se requiere confirmación explícita "
            "con dry_run=false. Reporta en español estructurado."
        ),
        "expected_jt": JT_IDS["jt_sql_diagnostics_enable"],
        "renderer": "generic",
        "pain_point": "Habilita monitoreo de performance SQL (slow queries, bloqueos, deadlocks)",
        "card_class": "card-info",
        "free_text": False,
        "accepts_filters": [],
        "tier": "secondary",
    },

    "nsg-block-ip": {
        "title": "Bloquear IP Sospechosa",
        "icon": "🚫",
        "subtitle": "Respuesta a brute force — agrega regla DENY en NSG (dry-run por defecto)",
        "prompt": (
            "El operador quiere bloquear la IP sospechosa '{user_input}' tras "
            "detección de brute force.\n\n"
            "PASO 1: Valida que la IP tenga formato correcto (X.X.X.X o CIDR X.X.X.X/N).\n\n"
            "PASO 2: Muestra el estado actual del NSG ejecutando lookup_infrastructure "
            "con mode='network' para ver las reglas existentes.\n\n"
            "PASO 3: Propone lanzar el job template "
            f"{JT_IDS['jt_nsg_block_ip']} (talento-nsg-block-ip) con "
            "extra_vars_json='{\"dry_run\": true, \"source_ip\": \"{user_input}\", "
            "\"rule_reason\": \"brute-force-detection\"}'. Esto mostrará el nombre "
            "de la regla y la prioridad que se usaría.\n\n"
            "PASO 4: Indica claramente que el bloqueo es TEMPORAL — para revertir "
            "hay que eliminar la regla del NSG manualmente. No reemplaza la "
            "revisión forense completa. Para ejecutar de verdad: dry_run=false.\n\n"
            "Reporta en español estructurado con advertencias de seguridad."
        ),
        "expected_jt": JT_IDS["jt_nsg_block_ip"],
        "renderer": "generic",
        "pain_point": "Bloqueo preventivo de IP en brute force HIGH — respuesta inmediata",
        "card_class": "card-critical",
        "free_text": True,
        "free_text_label": "IP a bloquear",
        "free_text_placeholder": "Ej: 203.0.113.42 o 192.168.0.0/24",
        "accepts_filters": [],
        "tier": "secondary",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SECONDARY — demostracion del safety pattern de remediacion
    # ═══════════════════════════════════════════════════════════════════════

    "auto-remediate-restart": {
        "title": "Auto-Remediacion: Restart",
        "icon": "🔧",
        "subtitle": "Reiniciar Container (DRY-RUN — safety pattern SOX)",
        "prompt": (
            "Primero diagnostica el estado actual del container con "
            "lookup_infrastructure mode='aci'. Luego ejecuta el job template "
            f"id={JT_IDS['jt_aci_restart']} (aci-restart) con "
            "extra_vars_json='{\"dry_run\": true, "
            "\"reason\": \"Remediacion propuesta por agente via dashboard\"}'. "
            "Esto NO reiniciara el container realmente. Sintetiza estado actual, "
            "accion que SE EJECUTARIA y URL del job AWX. Indica al usuario que "
            "para ejecutar de verdad se requiere confirmacion explicita."
        ),
        "expected_jt": JT_IDS["jt_aci_restart"],
        "renderer": "generic",
        "pain_point": "Demostracion del safety guard SOX (diagnostico + dry-run + doble confirmacion)",
        "card_class": "card-warning",
        "free_text": False,
        "accepts_filters": [],
        "tier": "secondary",
    },
}


def get_scenario(scenario_id: str) -> Optional[dict]:
    return SCENARIOS.get(scenario_id)


def list_scenarios() -> list:
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
            "free_text_placeholder": s.get("free_text_placeholder", "Escribe tu pregunta..."),
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
    scenario = get_scenario(scenario_id)
    if not scenario:
        return None

    if scenario.get("tier") == "pending":
        return None

    if scenario["free_text"]:
        text = (free_text or "").strip()
        # Escenarios donde user_input vacío es válido (tlnt-explorer=ranking, free-text=sin template)
        allows_empty = scenario_id in ("tlnt-explorer", "free-text")
        if not text and not allows_empty:
            return None
        if scenario["prompt"] and "{user_input}" in scenario["prompt"]:
            effective = {**DEFAULT_FILTERS, **JT_IDS, **(filters or {}), "user_input": text}
            try:
                return scenario["prompt"].format(**effective)
            except (KeyError, ValueError):
                return scenario["prompt"]
        return text

    effective = {**DEFAULT_FILTERS, **JT_IDS, **(filters or {})}
    # scope default para health check
    effective.setdefault("scope", "completo")
    try:
        return scenario["prompt"].format(**effective)
    except (KeyError, ValueError):
        return scenario["prompt"]


def get_default_filters() -> dict:
    return dict(DEFAULT_FILTERS)


def is_pending(scenario_id: str) -> bool:
    s = get_scenario(scenario_id)
    return bool(s and s.get("tier") == "pending")
