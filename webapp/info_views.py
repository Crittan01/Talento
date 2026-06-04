"""info_views — proveedores de datos para las vistas de informacion del dashboard.

Cada funcion devuelve un dict serializable a JSON con la info estructurada
de su vista. Sin red, sin estado mutable, sin side effects — lee archivos
del repo y consume vars del .env activo via bridge_l2.ENV.

Vistas:
  1. cert_summary()       — Certificacion SOX 50/50 + portal Foundry
  2. agent_info()         — Version actual: modelo, tools, reglas, JT IDs
  3. knowledge_index()    — Lista de archivos de knowledge base
  4. knowledge_file()     — Contenido de un archivo .md
  5. eapps_findings()     — Hallazgos abiertos con datos empiricos
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

# Vars del .env activo — el dashboard lee de aqui en vez de hardcodear nombres.
sys.path.insert(0, str(FUNCTION_APP_DIR))
import bridge_l2  # noqa: E402

ACI_NAME = bridge_l2.ENV.get("ACI_NAME", "<sin-configurar>")
ACI_RG = bridge_l2.ENV.get("ACI_RESOURCE_GROUP", "<sin-configurar>")
APPSERVICE_NAME = bridge_l2.ENV.get("APPSERVICE_NAME", "<sin-configurar>")
APPSERVICE_RG = bridge_l2.ENV.get("APPSERVICE_RESOURCE_GROUP", "<sin-configurar>")
SQL_NAME = bridge_l2.ENV.get("SQL_SERVER_NAME", "<sin-configurar>")
SQL_RG = bridge_l2.ENV.get("SQL_RESOURCE_GROUP", "<sin-configurar>")
WORKSPACE_ID = bridge_l2.ENV.get("LOG_ANALYTICS_WORKSPACE_ID", "<sin-configurar>")


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
# Vista 5: Estado del ambiente
# ============================================================================
def eapps_findings() -> dict:
    """Estado del ambiente y bloqueos abiertos con el equipo de plataforma."""
    return {
        "status": "2 hallazgos ABIERTOS bloquean la demo SOX por usuario",
        "findings": [
            {
                "id": "1",
                "title": (
                    f"Pipeline de logs del ACI moderno `{ACI_NAME}` desconectado"
                ),
                "severity": "alta",
                "summary": (
                    f"El target operativo (via .env) es el ACI moderno `{ACI_NAME}` en "
                    f"el RG `{ACI_RG}`. Inspeccion empirica del workspace de Log "
                    f"Analytics confirma que ese ACI NO emite logs: "
                    f"(a) sin diagnostic settings (Azure Monitor), "
                    f"(b) sin propiedad legacy `diagnostics.logAnalytics` en el "
                    f"containerGroup. En las ultimas 24h, los 13,659 registros de "
                    f"`ContainerInstanceLog_CL` provienen integramente del ACI 1 viejo "
                    f"(`aci-centralecopetrol` en `rg-central-solucion-talento`) via "
                    f"propiedad legacy ya configurada. AWX operara sobre el ACI moderno "
                    f"pero las KQL del agente solo veran al viejo hasta que se conecte "
                    f"el pipeline."
                ),
                "evidence": [
                    f"ACI moderno (target): {ACI_NAME} en {ACI_RG} -> sin logs.",
                    f"ACI viejo (origen actual de logs): aci-centralecopetrol en rg-central-solucion-talento -> 13,659 registros/24h.",
                    f"Workspace destino: law-central-soluciontalento (customerId {WORKSPACE_ID}).",
                    "Diagnostic settings ACI moderno: list vacia.",
                    "Container.diagnostics.logAnalytics ACI moderno: no configurado (propiedad inmutable).",
                ],
                "pending_action": (
                    f"Recrear `{ACI_NAME}` con bloque `diagnostics.logAnalytics` "
                    f"apuntando al workspace `law-central-soluciontalento` (customerId "
                    f"{WORKSPACE_ID}). Es una propiedad INMUTABLE — no se puede "
                    f"agregar post-creacion. Comando az exacto al final de este hallazgo."
                ),
                "command_for_eapps": (
                    "WS_KEY=$(az monitor log-analytics workspace get-shared-keys "
                    "-g rg-central-solucion-talento -n law-central-soluciontalento "
                    "--query primarySharedKey -o tsv) && \\\n"
                    f"# luego: redesplegar {ACI_NAME} (template ARM o az container create) "
                    f"con diagnostics.logAnalytics.workspaceId={WORKSPACE_ID} "
                    "y workspaceKey=$WS_KEY"
                ),
            },
            {
                "id": "2",
                "title": "Campo de identidad de usuario ausente en JSON de logs",
                "severity": "media",
                "summary": (
                    "Se habia confirmado que el JSON estructurado expondria los "
                    "campos `usuario` y `error_code`. Inspeccion empirica del "
                    "workspace en 168h (30,523 eventos JSON) muestra: "
                    "(a) el codigo TLNT vive en `codigo_error` (campo en ESPANOL, "
                    "22.7% cobertura), no `error_code`; (b) NO existe ningun "
                    "campo de identidad (`usuario`, `user`, `userName`, "
                    "`principalName`, `userId`). El correlador disponible es "
                    "`correlation_id` (99.5%). Cualquier query SOX por usuario "
                    "devuelve 0 filas hoy."
                ),
                "evidence": [
                    "Keys top-level del JSON en 168h: @timestamp, @version, level, level_value, message, modulo, logger_name, thread_name (100%), correlation_id (99.5%), codigo_error (22.7%), tags (3.7%).",
                    "0 ocurrencias de cualquier campo de identidad de usuario.",
                    "Knowledge actualizado a `tostring(p.codigo_error)` y escenarios sox-audit/brute-force/user-activity movidos a tier=pending.",
                ],
                "request_to_eapps": (
                    "Instrumentar Logback MDC con el principal autenticado para que "
                    "aparezca como key top-level del JSON estructurado. Hasta entonces, "
                    "la auditoria SOX por usuario es inviable y se debe cruzar "
                    "manualmente `correlation_id` contra Azure AD signin logs."
                ),
            },
            {
                "id": "3",
                "title": f"Service Principal con permisos sobre `{ACI_RG}` — RESUELTO",
                "severity": "resuelto",
                "summary": (
                    f"El SP `logssolution` (bbd498f7-...) ya tiene rol Contributor "
                    f"asignado sobre `{ACI_RG}` (asignado por admin Azure tras "
                    f"escalado). Smoke Health Check Completo (JT 55) ejecuta "
                    f"end-to-end exitosamente y reporta datos reales del ACI "
                    f"moderno `{ACI_NAME}`."
                ),
                "evidence": [
                    "az role assignment list --include-inherited: Contributor sobre rg-central-solucion-talento2 confirmado.",
                    "Smoke v14 post-asignacion: scenario=infra-health-check -> JT 55 job_id=482 -> AWX status=successful en 8.9s.",
                    f"Artifacts: overall_severity=HEALTHY, ACI={ACI_NAME} Running restartCount=0, App Service Running Normal, SQL Online Standard.",
                ],
            },
            {
                "id": "4",
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
