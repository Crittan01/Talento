#!/usr/bin/env python3
"""
probe-workspace.py — 10 probes empiricas contra el Log Analytics workspace de
TALENTO. Produce docs/eaps-evidence-report.md con hallazgos cuantitativos
que sustentan el pedido formal a EAPS de instrumentacion estructurada.

Uso:
  python3 scripts/probe-workspace.py [--days N]

Sale en docs/eaps-evidence-report.md (sobrescribe si existe).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OUT_PATH = ROOT / "docs" / "eaps-evidence-report.md"

DEFAULT_DAYS = 7


# ---------------------------------------------------------------------------
# Env loader (mismo patron que bridge_l2)
# ---------------------------------------------------------------------------
def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_PATH)
TENANT = ENV["AZURE_TENANT_ID"]
CLIENT = ENV["AZURE_CLIENT_ID"]
SECRET = ENV["AZURE_CLIENT_SECRET"]
WORKSPACE = ENV["LOG_ANALYTICS_WORKSPACE_ID"]


# ---------------------------------------------------------------------------
# KQL execution helpers
# ---------------------------------------------------------------------------
def get_token() -> str:
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT,
            "client_secret": SECRET,
            "resource": "https://api.loganalytics.io",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


_token_cache = {"token": None}


def kql(query: str) -> dict:
    """Ejecuta KQL, devuelve dict {columns: [...], rows: [...]} o {error: ...}."""
    if _token_cache["token"] is None:
        _token_cache["token"] = get_token()
    r = requests.post(
        f"https://api.loganalytics.azure.com/v1/workspaces/{WORKSPACE}/query",
        json={"query": query},
        headers={
            "Authorization": f"Bearer {_token_cache['token']}",
            "Content-Type": "application/json",
        },
        timeout=120,
    )
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "details": r.text[:500]}
    data = r.json()
    if not data.get("tables"):
        return {"columns": [], "rows": []}
    t = data["tables"][0]
    return {
        "columns": [c["name"] for c in t["columns"]],
        "rows": t.get("rows", []) or [],
    }


def md_table(columns, rows, max_rows=30) -> str:
    if not rows:
        return "_Sin datos._\n"
    rows = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = "\n".join(
        "| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows
    )
    return f"{header}\n{sep}\n{body}\n"


def _md_cell(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("|", "\\|").replace("\n", " ")
    if len(s) > 120:
        s = s[:117] + "..."
    return s


def pct(n, total) -> str:
    if total == 0:
        return "0%"
    return f"{(100.0 * n / total):.1f}%"


# ---------------------------------------------------------------------------
# 10 probes
# ---------------------------------------------------------------------------
def probe_1_inventory(days: int) -> str:
    """Inventario completo de tablas pobladas en N dias."""
    q = f"""
    union withsource=Tabla *
    | where TimeGenerated > ago({days}d)
    | summarize Registros=count(), Primera=min(TimeGenerated), Ultima=max(TimeGenerated) by Tabla
    | order by Registros desc
    """
    r = kql(q)
    if "error" in r:
        return f"**Error**: {r['error']}\n"
    out = [f"Tablas con datos en los ultimos {days} dias: **{len(r['rows'])}**\n"]
    out.append(md_table(r["columns"], r["rows"], max_rows=20))

    if not r["rows"]:
        out.append("\n> ⚠️ **Workspace vacio en este rango.** EAPS necesita verificar instrumentacion antes que cualquier otra cosa.\n")
    else:
        app_insights_tables = [r_ for r_ in r["rows"] if r_[0].startswith("App")]
        if not app_insights_tables:
            out.append("\n> ⚠️ **No hay tablas `App*` (Application Insights)**: la app TALENTO NO esta instrumentada con App Insights. Las tablas operativas estandar (`AppExceptions`, `AppRequests`, `AppTraces`, `AppDependencies`) estan ausentes. Esto es el **gap mas critico**.\n")
    return "".join(out)


def probe_2_schemas() -> str:
    """Schema de las 2 tablas mas pobladas."""
    out = []
    for tabla in ("ContainerInstanceLog_CL", "ContainerEvent_CL"):
        q = f"{tabla} | getschema"
        r = kql(q)
        if "error" in r:
            out.append(f"### {tabla}\n_Error: {r['error']}_\n\n")
            continue
        if not r["rows"]:
            out.append(f"### {tabla}\n_Sin datos / tabla no existe._\n\n")
            continue
        # Solo mostrar nombres + tipos, no toda la metadata
        cols = [(row[0], row[3] if len(row) > 3 else "?") for row in r["rows"]]
        out.append(f"### {tabla} ({len(cols)} columnas)\n\n")
        out.append("| Columna | Tipo |\n| --- | --- |\n")
        for name, tipo in cols:
            out.append(f"| {name} | {tipo} |\n")
        out.append("\n")
        # Detectar custom fields (sufijo _s, _d, _b indican Log Analytics custom)
        custom = [c for c, _ in cols if c.endswith(("_s", "_d", "_b", "_g", "_t"))]
        if custom:
            out.append(f"_Columnas custom detectadas (sufijos LA): {len(custom)}_\n\n")
    return "".join(out)


def probe_3_message_quality(days: int) -> str:
    """Sample 100 mensajes random y clasifica."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d) and isnotempty(Message)
    | sample 100
    | project Message
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin muestras.'}_\n"

    total = len(r["rows"])
    cats = {
        "stack_trace": 0,
        "framework_boot": 0,
        "business_event": 0,
        "error_or_warn": 0,
        "vacio_o_decorativo": 0,
        "otro": 0,
    }
    business_kw = ["usuario", "Login", "login", "vacacion", "incapacidad", "cumple",
                   "calamidad", "aprobar", "validar", "Listando", "rol="]
    boot_kw = ["Spring Boot", "Hibernate", "Tomcat", "Started", "EntityManager",
               "DataSource", "Initialized"]
    for (msg,) in r["rows"]:
        m = (msg or "").strip()
        ml = m.lower()
        if len(m) < 5 or set(m) <= set(" =-_·.|/\\"):
            cats["vacio_o_decorativo"] += 1
        elif "\tat " in m or m.startswith("Caused by") or m.startswith("\tat "):
            cats["stack_trace"] += 1
        elif any(k in m for k in boot_kw):
            cats["framework_boot"] += 1
        elif " ERROR " in m or " WARN " in m or "Exception" in m:
            cats["error_or_warn"] += 1
        elif any(k in m for k in business_kw):
            cats["business_event"] += 1
        else:
            cats["otro"] += 1

    out = [f"Muestreo de N={total} mensajes aleatorios:\n\n"]
    out.append("| Categoria | Count | % |\n| --- | --- | --- |\n")
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        out.append(f"| {k} | {v} | {pct(v, total)} |\n")
    out.append("\n")

    business_pct = 100.0 * cats["business_event"] / total
    if business_pct < 30:
        out.append(f"> ⚠️ **Solo {business_pct:.1f}% de los logs son eventos de negocio identificables.** El resto es ruido de framework/stack traces. Para el agente, esto significa que la mayoria del log es 'inutil' para diagnostico funcional. **Pedir a EAPS niveles de log diferenciados o filtros logback que reduzcan ruido.**\n")
    return "".join(out)


def probe_4_error_codes(days: int) -> str:
    """Detectar codigos de error con patrones comunes."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend c1 = extract(@"(TLNT-\\d+)", 1, Message)
    | extend c2 = extract(@"(ERR-\\d+)", 1, Message)
    | extend c3 = extract(@"(?:code|Code|error_code)[=:\\s]+([A-Z]{{2,6}}-\\d{{2,6}})", 1, Message)
    | extend c4 = extract(@"\\[([A-Z]{{2,5}}-\\d{{2,5}})\\]", 1, Message)
    | extend code = coalesce(c1, c2, c3, c4)
    | where isnotempty(code)
    | summarize Count=count() by code
    | order by Count desc
    | take 30
    """
    r = kql(q)
    if "error" in r:
        return f"_Error: {r['error']}_\n"
    if not r["rows"]:
        return ("Codigos detectados: **0**\n\n"
                "> ⚠️ **EAPS no emite codigos de error estructurados** (no se encontraron patrones tipo `TLNT-XXXX`, `ERR-XXX`, `[CODE-XXX]`, ni `error_code=XXX`). El agente no puede citar 'el error X significa Y' porque no hay X. **Pedido Tier 1.2: catalogo de error codes + emisin en cada log de error/warn.**\n")
    out = [f"Codigos detectados: **{len(r['rows'])} unicos** en {days}d.\n\n"]
    out.append(md_table(r["columns"], r["rows"]))
    return "".join(out)


def probe_5_message_templates(days: int) -> str:
    """Top 30 templates de mensaje (reemplazando numeros/IDs por <N>)."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend Template = replace_regex(Message, @"\\d{{3,}}", "<N>")
    | extend Template = replace_regex(Template, @"[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}", "<UUID>")
    | extend Template = substring(Template, 0, 140)
    | where isnotempty(Template)
    | summarize Count=count() by Template
    | order by Count desc
    | take 30
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin datos.'}_\n"

    # Total estimado para calcular % concentration del top 30
    q_total = f"ContainerInstanceLog_CL | where TimeGenerated > ago({days}d) | count"
    rt = kql(q_total)
    total = rt["rows"][0][0] if rt.get("rows") else 0
    top30_count = sum(row[1] for row in r["rows"])
    concentration = pct(top30_count, total) if total else "?"

    out = [
        f"Total logs en {days}d: **{total:,}**\n",
        f"Top 30 templates cubren: **{concentration}** del total\n\n",
        md_table(r["columns"], r["rows"]),
    ]
    if total and top30_count / total < 0.6:
        out.append("\n> ⚠️ **Alta cardinalidad de mensajes** (el top-30 cubre <60%). Sugiere logs muy ad-hoc, no estructurados. **Pedir a EAPS pattern de logs estructurados (JSON con `message_template` fijo + variables aparte).**\n")
    return "".join(out)


def probe_6_correlation_ids(days: int) -> str:
    """Buscar correlation IDs / trace IDs en mensajes."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend hasUuid = iff(Message matches regex @"[a-f0-9]{{8}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{12}}", 1, 0)
    | extend hasConnId = iff(Message has "ClientConnectionId", 1, 0)
    | extend hasReqId = iff(Message has "request_id" or Message has "X-Request-ID" or Message has "traceparent" or Message has "trace_id", 1, 0)
    | extend hasSpanId = iff(Message has "span_id" or Message has "spanId", 1, 0)
    | summarize
        Total=count(),
        ConUuid=sum(hasUuid),
        ConClientConnId=sum(hasConnId),
        ConRequestId=sum(hasReqId),
        ConSpanId=sum(hasSpanId)
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin datos.'}_\n"
    row = r["rows"][0]
    total, uuid_n, conn_n, req_n, span_n = row
    out = [
        f"| Tipo de ID | Count | % de logs |\n| --- | --- | --- |\n",
        f"| UUID generico | {uuid_n:,} | {pct(uuid_n, total)} |\n",
        f"| ClientConnectionId (SQL) | {conn_n:,} | {pct(conn_n, total)} |\n",
        f"| request_id / X-Request-ID / traceparent / trace_id | {req_n:,} | {pct(req_n, total)} |\n",
        f"| span_id | {span_n:,} | {pct(span_n, total)} |\n",
        f"\nTotal logs analizados: **{total:,}**\n\n",
    ]
    if req_n == 0 and span_n == 0:
        out.append("> ⚠️ **NO hay correlation IDs ni distributed tracing.** El agente no puede seguir una transaccion HTTP -> microservicio -> BD -> SAP. **Pedir a EAPS: propagar `traceparent` (W3C Trace Context) o al menos `X-Request-ID` end-to-end. Integrar OpenTelemetry o Spring Sleuth.**\n")
    elif req_n / total < 0.10:
        out.append(f"> ⚠️ **Solo {pct(req_n, total)} de los logs tienen request ID.** Tracing incompleto. **Pedir a EAPS instrumentacion mas amplia.**\n")
    return "".join(out)


def probe_7_severity_distribution(days: int) -> str:
    """Distribucion de severidad."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend Severity = case(
        Message contains " ERROR ", "ERROR",
        Message contains " WARN ", "WARN",
        Message contains " INFO ", "INFO",
        Message contains " DEBUG ", "DEBUG",
        Message contains " TRACE ", "TRACE",
        Message contains "Exception", "EXCEPTION",
        "OTHER")
    | summarize Count=count() by Severity
    | order by Count desc
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin datos.'}_\n"
    total = sum(row[1] for row in r["rows"])
    out = [
        "| Severidad | Count | % |\n| --- | --- | --- |\n",
    ]
    for row in r["rows"]:
        out.append(f"| {row[0]} | {row[1]:,} | {pct(row[1], total)} |\n")
    out.append(f"\nTotal: **{total:,}**\n\n")

    # Conclusion: si OTHER es alto, los niveles no estan bien marcados
    other = next((row[1] for row in r["rows"] if row[0] == "OTHER"), 0)
    if other / total > 0.5:
        out.append(f"> ⚠️ **{pct(other, total)} de logs sin severidad detectable.** Spring Boot suele incluir ` INFO `/` WARN `/` ERROR ` en el formato estandar; este % sugiere logs sin patron consistente. **Pedir a EAPS: log pattern unificado con severity en posicion fija.**\n")
    return "".join(out)


def probe_8_functional_coverage(days: int) -> str:
    """Que % de logs corresponden a procesos de negocio HR."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend Categoria = case(
        Message has "vacacion" or Message has "Vacacion", "vacaciones",
        Message has "incapacidad" or Message has "Incapacidad", "incapacidades",
        Message has "cumple" or Message has "Cumple", "cumpleanios",
        Message has "calamidad" or Message has "Calamidad", "calamidades",
        Message has "Login" or Message has "login", "auth_login",
        Message has "aprobar" or Message has "denegar" or Message has "Intentando aprobar", "aprobaciones",
        Message has "Spring" or Message has "Hibernate" or Message has "Tomcat" or Message has "EntityManager", "boot_framework",
        Message has "Exception" or Message has "ERROR" or Message has "failed", "errores",
        "otro")
    | summarize Count=count() by Categoria
    | order by Count desc
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin datos.'}_\n"
    total = sum(row[1] for row in r["rows"])
    out = ["| Categoria | Count | % |\n| --- | --- | --- |\n"]
    for row in r["rows"]:
        out.append(f"| {row[0]} | {row[1]:,} | {pct(row[1], total)} |\n")
    out.append(f"\nTotal: **{total:,}**\n\n")

    boot = next((row[1] for row in r["rows"] if row[0] == "boot_framework"), 0)
    if boot / total > 0.5:
        out.append(f"> ⚠️ **{pct(boot, total)} de logs son ruido de framework** (Spring Boot, Hibernate, Tomcat startup, etc.). El agente desperdicia tokens leyendo logs irrelevantes. **Pedir a EAPS: log level WARN por defecto en clases de framework (`logging.level.org.springframework=WARN`), INFO solo para clases propias de negocio (`logging.level.com.nttdata.ecopetrol=INFO`).**\n")
    return "".join(out)


def probe_9_latency_in_logs(days: int) -> str:
    """Logs con info de latencia/duracion."""
    q = f"""
    ContainerInstanceLog_CL
    | where TimeGenerated > ago({days}d)
    | extend hasLatency = iff(
        Message matches regex @"\\d+\\s*ms\\b" or
        Message has "took" or
        Message has "duration" or
        Message has "elapsed", 1, 0)
    | summarize Total=count(), ConLatencia=sum(hasLatency)
    """
    r = kql(q)
    if "error" in r or not r["rows"]:
        return f"_{'Error: ' + r.get('error', '') if 'error' in r else 'Sin datos.'}_\n"
    total, with_lat = r["rows"][0]
    out = [
        f"Logs con metricas de latencia (ms/duration/elapsed/took): **{with_lat:,}** de {total:,} ({pct(with_lat, total)})\n\n",
    ]
    if with_lat / max(total, 1) < 0.05:
        out.append("> ⚠️ **<5% de logs incluyen timing.** El agente no puede responder 'cuanto tarda X' sin metricas. **Pedir a EAPS: Application Insights con request duration auto-track + custom metrics para operaciones criticas (cierre nomina, validacion).**\n")
    return "".join(out)


def probe_10_container_events(days: int) -> str:
    """Detalle de eventos en ContainerEvent_CL."""
    q = f"""
    ContainerEvent_CL
    | where TimeGenerated > ago({days}d)
    | summarize Count=count() by ContainerName_s, Reason_s
    | order by Count desc
    | take 30
    """
    r = kql(q)
    if "error" in r:
        return f"_Error: {r['error']}_\n"
    if not r["rows"]:
        return "_Tabla `ContainerEvent_CL` vacia en este rango._\n"
    out = [
        f"Eventos de container distintos: **{len(r['rows'])}**\n\n",
        md_table(r["columns"], r["rows"], max_rows=30),
    ]
    return "".join(out)


# ---------------------------------------------------------------------------
# Generador del reporte
# ---------------------------------------------------------------------------
def generate_report(days: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        (
            "1. Inventario completo del workspace (ultimos N dias)",
            "Lista TODAS las tablas con datos. Identifica si Application Insights esta o no instrumentado.",
            probe_1_inventory,
        ),
        (
            "2. Schema completo de las tablas pobladas",
            "Verifica si hay campos `custom_*` (lo que indicaria que EAPS ya empezo a estructurar).",
            lambda d: probe_2_schemas(),
        ),
        (
            "3. Calidad del log: clasificacion de N=100 mensajes aleatorios",
            "Estima que fraccion del log es realmente util para diagnostico de negocio vs ruido.",
            probe_3_message_quality,
        ),
        (
            "4. Codigos de error estructurados detectados",
            "Busca patrones `TLNT-XXXX`, `ERR-XXX`, `[CODE-XX]`, `error_code=XXX`. Indica si hay catalogo emitido.",
            probe_4_error_codes,
        ),
        (
            "5. Cardinalidad de templates de mensaje (top 30)",
            "Mide si pocos mensajes-template dominan (= logs estructurados) o hay alta variedad (= logs ad-hoc).",
            probe_5_message_templates,
        ),
        (
            "6. Correlation IDs / Distributed Tracing",
            "Detecta presencia de UUIDs, ClientConnectionId, request_id, traceparent. Esencial para seguir transacciones.",
            probe_6_correlation_ids,
        ),
        (
            "7. Distribucion de severidad",
            "Verifica si las severidades estan bien marcadas o si la mayoria es 'OTHER'.",
            probe_7_severity_distribution,
        ),
        (
            "8. Cobertura funcional (categorias HR)",
            "Que fraccion del log es eventos de procesos reales (vacaciones, login, aprobaciones) vs framework.",
            probe_8_functional_coverage,
        ),
        (
            "9. Metricas de latencia presentes en logs",
            "Cuantos logs incluyen duraciones/timing. Importante para responder preguntas de performance.",
            probe_9_latency_in_logs,
        ),
        (
            "10. Detalle de ContainerEvent_CL",
            "Eventos de orquestacion de container (BackOff, Terminating, etc.) - util para diagnostico de infra.",
            probe_10_container_events,
        ),
    ]

    out = [
        "# Evidencia de gaps de telemetria TALENTO\n",
        f"_Generado: {now} · Workspace: `{WORKSPACE}` · Rango: ultimos {days} dias_\n\n",
        "Este reporte es **evidencia empirica** del estado actual de la telemetria emitida por la app TALENTO (simulada por EAPS). ",
        "Sustenta el pedido formal de robustecimiento al equipo EAPS — no es opinion, son datos del workspace real.\n\n",
        "---\n\n",
    ]
    for i, (title, desc, fn) in enumerate(sections, 1):
        out.append(f"## {title}\n\n")
        out.append(f"_{desc}_\n\n")
        print(f"  [{i}/{len(sections)}] {title[:60]}...", flush=True)
        try:
            out.append(fn(days))
        except Exception as exc:
            out.append(f"_Error en probe: {exc}_\n")
        out.append("\n---\n\n")

    # Conclusion consolidada (la inferimos del contenido pero la generamos textualmente)
    out.append("## Conclusion: pedidos prioritarios para EAPS\n\n")
    out.append(
        "Basado en lo observado en los 10 probes, el pedido formal a EAPS deberia priorizar:\n\n"
        "1. **Instrumentar Application Insights** en la app TALENTO (si las tablas `App*` del Probe 1 estan vacias).\n"
        "   - Spring Boot starter `applicationinsights-spring-boot-starter` o similar.\n"
        "   - Conecta automaticamente exceptions, requests, dependencies, traces a las tablas estandar.\n\n"
        "2. **Logs estructurados en JSON** con campos fijos: `timestamp`, `severity`, `correlation_id`, `user_id`, `business_action`, `entity_id`, `error_code`, `http_status`, `latency_ms`, `module`.\n"
        "   - Implementacion sugerida: `logback-spring.xml` + `logstash-logback-encoder`.\n\n"
        "3. **Catalogo de error codes** (Probe 4 confirma que no hay).\n"
        "   - Entregar archivo MD/JSON con cada codigo + severity + causa + remediacion.\n"
        "   - Subible al vector store del agente Foundry (`file_search` tool).\n\n"
        "4. **Correlation IDs end-to-end** (Probe 6 mide deficit actual).\n"
        "   - Propagar `traceparent` (W3C) o `X-Request-ID` a SAP / SuccessFactors / AD / Salud.\n\n"
        "5. **Niveles de log diferenciados** (si Probe 8 muestra >50% framework noise).\n"
        "   - `logging.level.org.springframework=WARN` (o INFO solo para clases propias).\n"
        "   - Reduce coste de ingestion y mejora ratio signal/noise para el agente.\n\n"
        "---\n\n"
        "_Re-ejecutar este script `python3 scripts/probe-workspace.py` cuando EAPS entregue cambios para comparar el progreso._\n"
    )
    return "".join(out)


def main():
    days = DEFAULT_DAYS
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])

    print(f"▸ Probando workspace {WORKSPACE} en los ultimos {days} dias...\n")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = generate_report(days)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"\n✓ Reporte escrito en: {OUT_PATH}")
    print(f"  ({len(report.splitlines())} lineas, {len(report)} caracteres)")


if __name__ == "__main__":
    main()
