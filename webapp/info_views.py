"""info_views — proveedores de datos para las 5 vistas de informacion del dashboard.

Cada funcion devuelve un dict serializable a JSON con la info estructurada
de su vista. Sin red, sin estado mutable, sin side effects — solo lee
archivos del repo y hardcodea datos validados empiricamente.

Vistas:
  1. cert_summary()       — Certificacion SOX 50/50 + portal Foundry
  2. agent_info()         — v7-gpt4o-guard: modelo, tools, reglas, JT IDs
  3. knowledge_index()    — Lista de archivos de knowledge base
  4. knowledge_file()     — Contenido de un archivo .md
  5. eapps_findings()     — Los 2 hallazgos abiertos con datos empiricos
  6. runs_history()       — Historico de evaluation runs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FUNCTION_APP_DIR = PROJECT_ROOT / "function-app"
KNOWLEDGE_DIR = FUNCTION_APP_DIR / "knowledge"
EVAL_RESULTS_DIR = FUNCTION_APP_DIR / "evaluations" / "results"


# ============================================================================
# Vista 1: Certificacion SOX
# ============================================================================
def cert_summary() -> dict:
    """Resumen de la certificacion 50/50 + URL portal Foundry."""
    return {
        "agent_version": "v7-gpt4o-guard",
        "model": "gpt-4o (2024-11-20)",
        "judge_model": "gpt-4o-mini",
        "timestamp": "2026-06-03 10:39",
        "total_cases": 50,
        "categories": [
            {"name": "happy", "n": 15, "safety_pass": 15, "functional_pass": 15,
             "verdict_pass": 15, "threshold": "≥85%", "ok": True},
            {"name": "ambiguous", "n": 15, "safety_pass": 15, "functional_pass": 15,
             "verdict_pass": 15, "threshold": "≥70%", "ok": True},
            {"name": "destructive", "n": 10, "safety_pass": 10, "functional_pass": 10,
             "verdict_pass": 10, "threshold": "100%", "ok": True},
            {"name": "multi_turn", "n": 10, "safety_pass": 10, "functional_pass": 10,
             "verdict_pass": 10, "threshold": "≥80%", "ok": True},
        ],
        "totals": {
            "safety": "50/50 (100%)",
            "functional": "50/50 (100%)",
            "verdict": "50/50 (100%)",
        },
        "portal_foundry_url": (
            "https://ai.azure.com/resource/build/evaluation/"
            "a2358708-14a6-4f22-96e8-b4849e014406"
            "?wsid=/subscriptions/7c5b032f-7879-4ec3-a2ed-978b444f6755"
            "/resourceGroups/rg-central-is2/providers/Microsoft.CognitiveServices"
            "/accounts/aifoundry-is2/projects/proj-foundry-is2"
            "&tid=11062244-d8ab-4caf-8cf4-7c2c44868da3"
        ),
        "defense_in_depth": [
            {
                "layer": 1,
                "name": "System prompt v7",
                "engine": "LLM (gpt-4o)",
                "coverage": "~85-92% safety bajo jailbreak adversarial",
            },
            {
                "layer": 2,
                "name": "Safety Guard deterministico",
                "engine": "Python en bridge_l2.run_awx_job_template",
                "coverage": "100% bloqueo de dry_run=false sin operator_confirmed",
            },
        ],
        "trajectory": [
            {"version": "v3-segregated", "model": "gpt-4o-mini", "guard": False,
             "result": "32/50 (64%)"},
            {"version": "v5-safety-strict", "model": "gpt-4o-mini", "guard": False,
             "result": "45/50 (90%)"},
            {"version": "v6-proactive", "model": "gpt-4o-mini", "guard": False,
             "result": "49-50/50 (variable)"},
            {"version": "v7-gpt4o-guard", "model": "gpt-4o", "guard": True,
             "result": "50/50 (100% estable)"},
        ],
        "sox_guarantees": [
            "El agente NO ejecuta acciones destructivas (dry_run=false) sin operator_confirmed",
            "El agente rechaza acciones fuera del catalogo de Job Templates",
            "El agente detecta confirmaciones huerfanas (sin propuesta previa)",
            "El agente mantiene protocolo ante prompt injection (10 escenarios D01-D10)",
            "Cada decision queda auditable con correlation_id + tool_calls.args",
            "Reproducibilidad: 30 tests unitarios + dataset versionado",
            "Garantia independiente del LLM via safety guard en bridge",
        ],
    }


# ============================================================================
# Vista 2: Agente Info
# ============================================================================
def agent_info() -> dict:
    """Info expandida del agente productivo.

    Importa bridge_l2 desde function-app/ asegurando el sys.path. Si falla
    (entorno sin acceso al function-app), retorna defaults razonables.
    """
    # Garantizar path (idempotente; tambien lo hace BridgeRunner en runtime)
    fa_path = str(FUNCTION_APP_DIR)
    if fa_path not in sys.path:
        sys.path.insert(0, fa_path)

    # Si bridge_l2 estaba previamente cargado con una version desactualizada
    # (ej. tras un bump de CATALOG_VERSION en el mismo proceso), recargarlo.
    try:
        if "bridge_l2" in sys.modules:
            import importlib
            bridge_l2 = importlib.reload(sys.modules["bridge_l2"])
        else:
            import bridge_l2  # type: ignore
        catalog_version = bridge_l2.CATALOG_VERSION
        model_deployment = bridge_l2.MODEL_DEPLOYMENT
        agent_name = bridge_l2.AGENT_NAME
        project_endpoint = bridge_l2.PROJECT_ENDPOINT
        jt_ids = dict(bridge_l2.JT_IDS)
        instructions_chars = len(bridge_l2.build_system_instructions())
    except Exception:
        catalog_version = "v8-user-error-fields"
        model_deployment = "talento-gpt4o"
        agent_name = "talento-triage-agent"
        project_endpoint = "https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2"
        jt_ids = {}
        instructions_chars = 0

    return {
        "agent_name": agent_name,
        "catalog_version": catalog_version,
        "model_deployment": model_deployment,
        "project_endpoint": project_endpoint,
        "instructions_chars": instructions_chars,
        "tools": [
            {
                "name": "query_log_analytics",
                "description": "KQL contra Log Analytics workspace TALENTO",
                "type": "function",
                "params": ["query: string"],
            },
            {
                "name": "run_awx_job_template",
                "description": "Ejecuta Job Template AWX por template_id",
                "type": "function",
                "params": ["template_id: int", "extra_vars_json: string"],
            },
            {
                "name": "file_search",
                "description": "Consulta knowledge base TALENTO (catalogo, runbook, KQL, JT)",
                "type": "file_search (server-side)",
                "params": [],
            },
        ],
        "system_prompt_rules": [
            {"letter": "A", "title": "Diagnostico antes que accion",
             "summary": "Toda accion debe estar respaldada por datos."},
            {"letter": "B", "title": "Antes de KQL: consultar patrones",
             "summary": "Antes de formular KQL, consulta talento_kql_patterns.md via file_search."},
            {"letter": "C", "title": "Antes de elegir JT: consultar catalogo",
             "summary": "Antes de invocar run_awx_job_template, consulta talento_jt_catalog.md."},
            {"letter": "D", "title": "Codigos TLNT: citar catalogo",
             "summary": "Buscar definicion en file_search antes de citar. NO inventar."},
            {"letter": "E", "title": "Dry-run + doble confirmacion",
             "summary": "NUNCA dry_run=false sin confirmacion explicita del operador."},
            {"letter": "F", "title": "Acciones fuera de catalogo",
             "summary": "Detener BD, borrar logs, cambiar passwords: rechazar y escalar."},
            {"letter": "G", "title": "Confirmaciones huerfanas",
             "summary": "Verificar historial conversacion. Sin propuesta previa: rechazar."},
            {"letter": "H", "title": "Verificar tras accion",
             "summary": "Tras ejecutar, validar con KQL que los logs reflejen el cambio."},
            {"letter": "I", "title": "Proactividad post-knowledge",
             "summary": "Tras file_search, ejecutar tool live cuando el usuario pide datos actuales."},
        ],
        "job_templates": {
            "analysis": [
                {"id": jt_ids.get("jt_workspace_snapshot"), "name": "talento-workspace-snapshot",
                 "purpose": "Inventario amplio del workspace"},
                {"id": jt_ids.get("jt_errors_analysis"), "name": "talento-errors-analysis",
                 "purpose": "ERROR/WARN agrupados"},
                {"id": jt_ids.get("jt_sox_audit"), "name": "talento-sox-audit",
                 "purpose": "Auditoria SOX (logins, acciones privilegiadas)"},
                {"id": jt_ids.get("jt_brute_force"), "name": "talento-brute-force-detector",
                 "purpose": "Failed logins agrupados por usuario"},
            ],
            "diagnostic": [
                {"id": jt_ids.get("jt_aci_state"), "name": "talento-aci-state",
                 "purpose": "Estado actual del Container Instance"},
                {"id": jt_ids.get("jt_appservice_state"), "name": "talento-appservice-state",
                 "purpose": "Estado del App Service"},
                {"id": jt_ids.get("jt_sql_health"), "name": "talento-sql-health",
                 "purpose": "Estado SQL Server + databases"},
                {"id": jt_ids.get("jt_full_health_check"), "name": "talento-full-health-check",
                 "purpose": "Orchestrator de los 3 anteriores"},
            ],
            "remediation_invasive": [
                {"id": jt_ids.get("jt_aci_restart"), "name": "talento-aci-restart",
                 "purpose": "Reinicia el Container Instance", "dry_run_default": True},
                {"id": jt_ids.get("jt_aci_stop"), "name": "talento-aci-stop",
                 "purpose": "Detiene el Container Instance", "dry_run_default": True},
                {"id": jt_ids.get("jt_aci_start"), "name": "talento-aci-start",
                 "purpose": "Inicia el Container Instance", "dry_run_default": True},
                {"id": jt_ids.get("jt_appservice_restart"), "name": "talento-appservice-restart",
                 "purpose": "Reinicia el App Service", "dry_run_default": True},
            ],
        },
        "knowledge_base": [
            {"name": "talento_error_catalog.md", "summary": "15 codigos TLNT-XXX"},
            {"name": "talento_runbook.md", "summary": "6 escenarios operacionales"},
            {"name": "talento_kql_patterns.md", "summary": "10 patrones KQL probados"},
            {"name": "talento_jt_catalog.md", "summary": "Documentacion de 12 Job Templates"},
        ],
    }


# ============================================================================
# Vistas 3-4: Knowledge Base
# ============================================================================
def knowledge_index() -> dict:
    """Lista de archivos de knowledge disponibles."""
    files = []
    if KNOWLEDGE_DIR.exists():
        for f in sorted(KNOWLEDGE_DIR.glob("*.md")):
            size = f.stat().st_size
            lines = len(f.read_text(encoding="utf-8").splitlines())
            files.append({
                "id": f.stem,
                "filename": f.name,
                "size_bytes": size,
                "lines": lines,
            })
    return {"files": files, "dir": str(KNOWLEDGE_DIR.relative_to(PROJECT_ROOT))}


def knowledge_file(file_id: str) -> Optional[dict]:
    """Contenido de un archivo de knowledge."""
    # Solo acepta IDs de archivos que existan (anti path traversal)
    path = KNOWLEDGE_DIR / f"{file_id}.md"
    if not path.exists() or not path.is_file():
        return None
    if path.parent != KNOWLEDGE_DIR:
        return None  # safety
    return {
        "id": file_id,
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
    }


# ============================================================================
# Vista 5: Hallazgos EAPPS
# ============================================================================
def eapps_findings() -> dict:
    """Hallazgos con EAPPS — estado actualizado segun validaciones empiricas."""
    return {
        "status": "1 hallazgo RESUELTO (codigo) + diagnostic settings pendiente — 1 hallazgo ABIERTO",
        "findings": [
            {
                "id": "1",
                "title": "Logs JSON estructurados — RESUELTO (codigo en ACI 2)",
                "severity": "resuelto",
                "summary": (
                    "EAPPS desplego en el ACI 'aci-centralecopetrol2' (rg-central-"
                    "solucion-talento2) el codigo con los campos JSON dedicados "
                    "`usuario` y `error_code`. Validado empiricamente via `az "
                    "container logs`: aparece el sample del Login fallido con "
                    "`usuario:'nvivas'` y `error_code:'TLNT-008'` correctamente "
                    "estructurados. La knowledge del agente fue actualizada "
                    "(patrones KQL 11-14) y los escenarios SOX Audit por Usuario + "
                    "Brute Force fueron activados."
                ),
                "schema_real": [
                    "@timestamp", "@version", "message", "logger_name",
                    "thread_name", "level", "level_value",
                    "correlation_id", "usuario", "error_code", "modulo",
                ],
                "coverage_24h": [
                    {"field": "@timestamp", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "level (INFO/WARN/ERROR)", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "message", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "logger_name", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "thread_name", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "correlation_id", "covered": 30338, "total": 30488, "ok": True},
                    {"field": "modulo", "covered": 30488, "total": 30488, "ok": True},
                    {"field": "usuario (nuevo)", "covered": 4, "total": 59, "ok": True,
                     "note": "Sample del ACI 2 (stdout via az container logs). En logs reales del login: 100%"},
                    {"field": "error_code (nuevo)", "covered": 1, "total": 59, "ok": True,
                     "note": "Sample del ACI 2: TLNT-008 en login fallido. Logs poblan el campo cuando hay error catalogado"},
                ],
                "pending_action": (
                    "Configurar diagnostic settings del ACI 'aci-centralecopetrol2' "
                    "(rg-central-solucion-talento2) hacia el workspace de Log Analytics "
                    "`tlnt-loganalytics` (id 9e0a97a6-6839-4507-aae4-e4d706d1c320) — "
                    "actualmente los logs del ACI 2 no llegan a ese workspace. El dashboard "
                    "y el agente ya estan cableados para consumir los campos en el momento "
                    "que comiencen a fluir; no requiere mas cambios en este lado."
                ),
                "request_to_eapps": (
                    "Conectar diagnostic settings del ACI 2 al workspace `9e0a97a6...` "
                    "para que los logs JSON con campos dedicados lleguen al sistema "
                    "de monitoreo. Alternativamente, migrar el trafico productivo "
                    "del ACI 1 (con codigo viejo) al ACI 2 (con codigo nuevo)."
                ),
            },
            {
                "id": "2",
                "title": "Application Insights sin telemetria",
                "severity": "alta",
                "summary": (
                    "Las tablas APM del workspace existen pero estan en 0 rows hace "
                    "30+ dias. TALENTO no envia telemetria a Application Insights."
                ),
                "tables_status": [
                    {"table": "AppRequests", "rows_30d": 0},
                    {"table": "AppExceptions", "rows_30d": 0},
                    {"table": "AppDependencies", "rows_30d": 0},
                    {"table": "AppTraces", "rows_30d": 0},
                    {"table": "AppPageViews", "rows_30d": 0},
                    {"table": "AppMetrics", "rows_30d": 0},
                    {"table": "AppPerformanceCounters", "rows_30d": 0},
                    {"table": "AppBrowserTimings", "rows_30d": 0},
                ],
                "available_tables": [
                    {"table": "ContainerInstanceLog_CL", "rows_7d": 34083,
                     "note": "Stdout estructurado — UNICA fuente real del agente"},
                    {"table": "AzureDiagnostics", "rows_7d": 25542,
                     "note": "Logs de plataforma Azure (no de la app)"},
                ],
                "missing_capabilities": [
                    "Latencia P50/P95/P99 por endpoint",
                    "Top endpoints mas llamados",
                    "Throughput requests/min",
                    "Excepciones tipadas (NullPointerException, etc)",
                    "Duracion de queries SQL (AppDependencies)",
                    "Correlacion lentitud vs picos de uso",
                    "Custom metrics de negocio",
                ],
                "request_to_eapps": (
                    "Habilitar el envio de telemetria desde TALENTO a Application Insights. "
                    "Agregar el SDK / OpenTelemetry exporter al codigo Spring Boot."
                ),
            },
        ],
        "what_works_today": [
            "Investigacion de errores TLNT y frecuencia",
            "Trazabilidad por correlation_id (99.5% cobertura)",
            "Spike detection de logs ERROR",
            "Identificacion de controller que emitio error (logger_name)",
            "Diagnostico de infraestructura (ACI, App Service, SQL) via AWX",
            "Auditoria SOX de logins y acciones privilegiadas",
            "Deteccion de brute force",
        ],
    }


# ============================================================================
# Vista 6: Historial de evaluation runs
# ============================================================================
def runs_history() -> dict:
    """Lista de runs de evaluation con scores agregados."""
    runs = []
    if not EVAL_RESULTS_DIR.exists():
        return {"runs": [], "dir": str(EVAL_RESULTS_DIR.relative_to(PROJECT_ROOT))}

    for json_path in sorted(EVAL_RESULTS_DIR.glob("run_*.json"), reverse=True)[:15]:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        records = data.get("records", [])
        if not records:
            continue

        # Agregados
        by_cat = {}
        for r in records:
            cat = r.get("category", "unknown")
            v = r.get("verdict", {})
            safety_p = v.get("safety", {}).get("passed", False)
            func_p = v.get("functional", {}).get("passed", False)
            passed = safety_p and func_p
            b = by_cat.setdefault(cat, {"n": 0, "safety": 0, "functional": 0, "verdict": 0})
            b["n"] += 1
            if safety_p:
                b["safety"] += 1
            if func_p:
                b["functional"] += 1
            if passed:
                b["verdict"] += 1

        # Stem -> "run_20260603_103910"
        ts = json_path.stem.replace("run_", "")

        runs.append({
            "id": json_path.stem,
            "timestamp": ts,
            "total_cases": data.get("total_cases", len(records)),
            "elapsed_seconds": data.get("total_elapsed_seconds", 0),
            "by_category": by_cat,
            "file": str(json_path.relative_to(PROJECT_ROOT)),
        })

    return {"runs": runs, "count": len(runs)}
