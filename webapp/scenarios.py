"""scenarios — catalogo de los 6 escenarios pre-canned del dashboard.

Cada escenario define:
- id: identificador para la API
- title, icon, subtitle: lo que ve el usuario en la card
- prompt: instruccion que se le pasa al agente Foundry (muy directiva, fuerza
  el JT correcto para reducir wandering)
- expected_jt: id de Job Template esperado (informativo, no enforced)
- renderer: que renderer del frontend se usa para pintar el resultado
- pain_point: a que pain point del RFP responde
- free_text: True si el usuario puede sustituir el prompt
"""
from __future__ import annotations

from typing import Optional


SCENARIOS = {
    "system-status": {
        "title": "Estado del Sistema",
        "icon": "📊",
        "subtitle": "Inventario amplio del workspace en últimas 24h",
        "prompt": (
            "Ejecuta directamente el job template id=48 (talento-workspace-snapshot) "
            "con extra_vars_json='{\"time_range_hours\": 24}' para obtener un "
            "inventario completo del workspace de TALENTO. Cuando termine, "
            "sintetiza los hallazgos del set_stats: tablas pobladas, top tabla, "
            "filas, schema, muestra. Reporta en español estructurado."
        ),
        "expected_jt": 48,
        "renderer": "snapshot",
        "pain_point": "(5) Estrategia de monitoreo — vista panorámica",
        "card_class": "card-info",
        "free_text": False,
    },
    "errors-production": {
        "title": "Errores en Producción",
        "icon": "🚨",
        "subtitle": "Detección y análisis de eventos ERROR/WARN críticos",
        "prompt": (
            "Ejecuta directamente el job template id=49 (talento-errors-analysis) "
            "con extra_vars_json='{\"time_range_hours\": 24}' para detectar "
            "errores y warnings críticos en TALENTO. Cuando termine, sintetiza "
            "los hallazgos: cuántos errores, cuántos warnings, severity_status, "
            "top mensajes y containers afectados. Reporta en español."
        ),
        "expected_jt": 49,
        "renderer": "errors",
        "pain_point": "Mesa de ayuda sin RCA clara",
        "card_class": "card-alert",
        "free_text": False,
    },
    "sox-audit": {
        "title": "Auditoría SOX",
        "icon": "🔐",
        "subtitle": "Quién accedió, qué aprobó, incidentes de seguridad BD",
        "prompt": (
            "TALENTO es regulado por SOX. Ejecuta directamente el job template "
            "id=50 (talento-sox-audit) con extra_vars_json='{\"time_range_hours\": 24}' "
            "para auditar la actividad de las últimas 24 horas. Cuando termine, "
            "sintetiza los hallazgos: audit_status, logins por usuario, acciones "
            "privilegiadas (rol=LIDER, aprobaciones), incidentes de seguridad BD "
            "(failed SQL logins). Reporta en español con énfasis en compliance."
        ),
        "expected_jt": 50,
        "renderer": "sox",
        "pain_point": "Objetos no autorizados BD + cumplimiento SOX",
        "card_class": "card-critical",
        "free_text": False,
    },
    "brute-force": {
        "title": "Detección de Brute Force",
        "icon": "🛡️",
        "subtitle": "Múltiples intentos de login fallidos por usuario",
        "prompt": (
            "Detecta intentos de brute force en TALENTO. Ejecuta directamente el "
            "job template id=51 (talento-brute-force-detector) con "
            "extra_vars_json='{\"time_range_hours\": 24, \"failed_threshold\": 5}' "
            "para identificar usuarios con múltiples intentos fallidos en "
            "ventana corta. Cuando termine, sintetiza: cuántos usuarios "
            "sospechosos, severidad, recomendación de acción. Reporta en español."
        ),
        "expected_jt": 51,
        "renderer": "brute-force",
        "pain_point": "Accesos no autorizados (foco específico)",
        "card_class": "card-critical",
        "free_text": False,
    },
    "payroll-slow": {
        "title": "Lentitud Cierre Nómina",
        "icon": "⏱️",
        "subtitle": "Errores y degradación durante cierre mensual",
        "prompt": (
            "Hoy es día de cierre de nómina en TALENTO y se reportó lentitud. "
            "Ejecuta directamente el job template id=49 (talento-errors-analysis) "
            "con extra_vars_json='{\"time_range_hours\": 4}' para detectar "
            "errores recientes que puedan explicar la lentitud. Sintetiza: "
            "errores SQL/Hibernate, containers afectados, hipótesis de causa raíz "
            "asociada al cierre (conexiones BD saturadas, queries lentas, etc.). "
            "Reporta en español orientado a operaciones."
        ),
        "expected_jt": 49,
        "renderer": "errors",
        "pain_point": "Lentitud generalizada en cierres de nómina",
        "card_class": "card-warning",
        "free_text": False,
    },
    "free-text": {
        "title": "Pregunta Libre",
        "icon": "🤖",
        "subtitle": "Escribe tu propia pregunta — el agente decide qué tool usar",
        "prompt": None,  # se sustituye por el texto del usuario
        "expected_jt": None,
        "renderer": "generic",
        "pain_point": "Flexibilidad operativa",
        "card_class": "card-neutral",
        "free_text": True,
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
        })
    return out


def resolve_prompt(scenario_id: str, free_text: Optional[str] = None) -> Optional[str]:
    """Devuelve el prompt final para enviar al agente.

    Para escenarios pre-canned: devuelve el prompt fijo.
    Para 'free-text': devuelve el texto del usuario (debe venir).
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        return None
    if scenario["free_text"]:
        return (free_text or "").strip() or None
    return scenario["prompt"]
