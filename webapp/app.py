"""app — FastAPI principal del dashboard TALENTO Operations Console.

Rutas:
  GET  /                           Dashboard HTML (Jinja2)
  GET  /api/scenarios              Lista de 6 escenarios (JSON)
  POST /api/run                    Lanza un run (body: scenario_id, free_text?, mock?)
  GET  /api/run/{run_id}/stream    SSE con eventos del run
  GET  /healthz                    Health check

Variables de entorno relevantes:
  FORCE_MOCK=1  →  todos los runs usan mock (red de seguridad para demos)
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import bridge_runner, info_views, mock_events, elk_alerts
from .event_bus import bus
from .live_feed import feed
from .scenarios import list_scenarios, resolve_prompt, get_scenario, get_default_filters, is_pending


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="TALENTO Operations Console")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _force_mock() -> bool:
    return os.environ.get("FORCE_MOCK", "").lower() in ("1", "true", "yes")


@app.on_event("startup")
async def _register_live_feed_loop() -> None:
    """Registra el event loop en el live_feed para que publish() funcione
    desde los worker threads del agente."""
    feed.set_loop(asyncio.get_running_loop())


@app.on_event("startup")
def _ensure_foundry_agent() -> None:
    """Verifica al arrancar uvicorn que el agente Foundry con el AGENT_NAME
    actual existe (con al menos una version). Si no existe, lo crea via
    create_version. Esto evita el 404 'Agent X with version not found'
    cuando se bumpean los JT IDs (nuevo hash → nuevo AGENT_NAME).
    """
    if _force_mock():
        print("[startup] FORCE_MOCK activo — skip Foundry agent setup.", flush=True)
        return
    try:
        import bridge_l2
        from azure.ai.projects import AIProjectClient

        project = AIProjectClient(
            endpoint=bridge_l2.PROJECT_ENDPOINT,
            credential=bridge_l2.get_azure_credential(),
        )
        # ¿El agente ya tiene versiones registradas? La SDK pide agent_name=
        # (no name=) — si se pasa mal cae a [] y siempre re-crea version.
        try:
            versions = list(project.agents.list_versions(agent_name=bridge_l2.AGENT_NAME))
        except Exception:
            versions = []
        if versions:
            print(
                f"[startup] Agente '{bridge_l2.AGENT_NAME}' ya existe "
                f"con {len(versions)} version(es) — skip create.",
                flush=True,
            )
            return
        print(
            f"[startup] Agente '{bridge_l2.AGENT_NAME}' NO existe — creando "
            f"con JT_IDS={bridge_l2.JT_IDS}...",
            flush=True,
        )
        agent = bridge_l2.setup_agent_version(project)
        print(
            f"[startup] ✓ Agente creado: name={agent.name} version={getattr(agent, 'version', '?')}",
            flush=True,
        )
    except Exception as exc:
        # No bloqueamos el arranque si Foundry no responde — la primera
        # request fallara y el error sera visible en el dashboard.
        print(f"[startup] ⚠ No se pudo asegurar el agente Foundry: {exc}", flush=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    scenario_id: str
    free_text: Optional[str] = None
    mock: bool = False
    filters: Optional[dict] = None  # ej. {"time_range_hours": 4, "failed_threshold": 10}


class ElkRunRequest(BaseModel):
    alert_id: str
    mock: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _asset_version() -> str:
    """Hash corto del mtime de ecp.js + ecp.css para cache-busting.
    Cuando cambia cualquiera de los dos, la version cambia y el navegador
    recarga el asset nuevo automaticamente (sin hard refresh manual)."""
    try:
        js = (STATIC_DIR / "js" / "ecp.js").stat().st_mtime
        css = (STATIC_DIR / "css" / "ecp.css").stat().st_mtime
        rj = (STATIC_DIR / "js" / "renderers.js").stat().st_mtime
        return str(int(js + css + rj))[-8:]
    except OSError:
        return "1"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Pagina principal del dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "force_mock": _force_mock(),
            "scenarios": list_scenarios(),
            "asset_version": _asset_version(),
        },
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "force_mock": _force_mock()}


@app.get("/api/scenarios")
async def api_scenarios():
    return {
        "scenarios": list_scenarios(),
        "force_mock": _force_mock(),
        "default_filters": get_default_filters(),
    }


# ---------------------------------------------------------------------------
# Info views — 5 paneles informativos sobre el estado del agente y certificacion
# ---------------------------------------------------------------------------
@app.get("/api/info/cert")
async def api_info_cert():
    """Resumen de certificacion SOX 50/50 + portal Foundry."""
    return info_views.cert_summary()


@app.get("/api/info/agent")
async def api_info_agent():
    """Info expandida del agente productivo (version, modelo, tools, reglas, JTs)."""
    return info_views.agent_info()


@app.get("/api/info/knowledge")
async def api_info_knowledge():
    """Lista de archivos de knowledge base disponibles."""
    return info_views.knowledge_index()


@app.get("/api/info/knowledge/{file_id}")
async def api_info_knowledge_file(file_id: str):
    """Contenido de un archivo de knowledge (Markdown)."""
    data = info_views.knowledge_file(file_id)
    if data is None:
        raise HTTPException(404, f"Knowledge file no encontrado: {file_id}")
    return data


@app.get("/api/info/findings")
async def api_info_findings():
    """Estado del ambiente — capacidades en habilitacion y bloqueos abiertos."""
    return info_views.eapps_findings()


@app.get("/api/info/runs")
async def api_info_runs():
    """Historial de runs de evaluation con scores agregados."""
    return info_views.runs_history()


@app.post("/api/run")
async def api_run(payload: RunRequest):
    """Lanza un run (real o mock) y devuelve run_id para conectar via SSE."""
    scenario = get_scenario(payload.scenario_id)
    if not scenario:
        raise HTTPException(404, f"scenario_id desconocido: {payload.scenario_id}")

    # Roadmap (en habilitacion): rechazar con 400 explicativo
    if is_pending(payload.scenario_id):
        raise HTTPException(
            400,
            f"Este escenario esta en habilitacion y no se puede "
            f"ejecutar todavia. Razon: {scenario.get('pending_eapps_reason', 'pendiente')}",
        )

    # Validar free_text ANTES del split mock/real — aplica en ambos modos.
    # resolve_prompt devuelve None si el escenario requiere free_text y no se dio.
    prompt = resolve_prompt(
        payload.scenario_id,
        free_text=payload.free_text,
        filters=payload.filters,
    )
    if prompt is None:
        raise HTTPException(400, "Pregunta vacia o invalida (free_text requerido para este escenario)")

    # Modo mock: forzado por env var (FORCE_MOCK=1) o solicitado en el request
    use_mock = payload.mock or _force_mock()

    if use_mock:
        run_id = await bridge_runner.start_mock_run(payload.scenario_id, mock_events)
        return {"run_id": run_id, "mode": "mock"}

    # Los filtros del UI se pasan como force_extra_vars.
    # target_env ("v1"/"v2") controla qué instancia investigan las tools de infra.
    filters = dict(payload.filters or {})
    filters.setdefault("target_env", "v2")  # default: instancia activa
    run_id = await bridge_runner.start_run(
        user_question=prompt,
        no_setup=True,
        max_hops=8,
        force_extra_vars=filters,
    )
    return {"run_id": run_id, "mode": "real"}


# ---------------------------------------------------------------------------
# Simulación ELK — visualiza el flujo cuando una alerta viene del HUB
# ---------------------------------------------------------------------------
@app.get("/api/elk/alerts")
async def api_elk_alerts():
    """Lista las alertas ELK demo con su payload y camino de investigación."""
    return {"alerts": elk_alerts.list_elk_alerts()}


@app.post("/api/elk/run")
async def api_elk_run(payload: ElkRunRequest):
    """Dispara el flujo de una alerta ELK: normaliza el payload igual que el
    endpoint productivo y lanza la investigación del agente. Devuelve run_id
    + el payload de la alerta + el prompt normalizado para visualizar el flujo."""
    spec = elk_alerts.get_elk_alert(payload.alert_id)
    if not spec:
        raise HTTPException(404, f"alert_id desconocido: {payload.alert_id}")

    alert = spec["alert"]
    prompt = elk_alerts.build_alert_prompt(alert)
    target_env = alert.get("target_env", "v2")

    if payload.mock or _force_mock():
        # En mock no hay secuencia pregrabada de ELK — devolvemos solo el contexto
        raise HTTPException(400, "El flujo ELK requiere modo real (no mock)")

    run_id = await bridge_runner.start_run(
        user_question=prompt,
        no_setup=True,
        max_hops=8,
        force_extra_vars={"target_env": target_env},
    )
    return {
        "run_id": run_id,
        "mode": "real",
        "alert": alert,
        "rule": spec["rule"],
        "normalized_prompt": prompt,
        "suggested_path": elk_alerts._suggested_path(alert.get("metric", "")),
    }


# ---------------------------------------------------------------------------
# Monitor en vivo — ELK REAL dispara aquí y se visualiza al instante.
# Este es el endpoint que ELK (o curl, o el simulador --http) llamaría en
# producción. NO requiere la UI demo: la alerta entra, el agente investiga,
# y todo se transmite en vivo a las pantallas /monitor conectadas.
# ---------------------------------------------------------------------------
@app.post("/api/elk/ingest")
async def api_elk_ingest(request: Request):
    """Endpoint que ELK llama de verdad. Recibe el payload de alerta crudo,
    lo publica al monitor en vivo, normaliza y lanza la investigación del
    agente — emitiendo cada paso al feed para visualización instantánea."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body inválido — debe ser JSON")

    alert = body.get("alert")
    if not isinstance(alert, dict):
        raise HTTPException(400, "Payload sin 'alert' — formato ELK esperado")

    prompt = elk_alerts.build_alert_prompt(alert)
    target_env = alert.get("target_env", "v2")
    rule = alert.get("rule", "regla-sin-nombre")

    # 1. Publicar "alerta recibida" al monitor — aparece al instante
    import uuid as _uuid
    incident_id = _uuid.uuid4().hex[:8]
    feed.publish({
        "type": "elk.alert.received",
        "incident_id": incident_id,
        "rule": rule,
        "severity": alert.get("severity", "?"),
        "metric": alert.get("metric", "?"),
        "resource": alert.get("resource", "?"),
        "context": alert.get("context", {}),
        "source": alert.get("source", "elk"),
        "suggested_path": elk_alerts._suggested_path(alert.get("metric", "")),
    })

    # 2. Lanzar el agente; cada evento se replica al monitor
    def feed_emit(event: dict):
        feed.publish({**event, "incident_id": incident_id, "rule": rule})

    import time as _t
    run_id = await bridge_runner.start_run(
        user_question=prompt,
        no_setup=True,
        max_hops=8,
        force_extra_vars={
            "target_env": target_env,
            # Contexto del incidente para report_incident → Panel de Aprobacion.
            # Claves con prefijo _ NO viajan a AWX (filtradas por _awx_safe_extra_vars).
            "_elk_alert": {**alert, "rule": rule},
            "_incident_id": f"INC-{incident_id}",
            "_t_start": _t.time(),
        },
        extra_emit=feed_emit,
    )

    return {
        "status": "accepted",
        "incident_id": incident_id,
        "run_id": run_id,
        "message": "Alerta ingestada — visualizando en /monitor",
    }


@app.get("/api/elk/feed")
async def api_elk_feed(request: Request):
    """SSE del monitor en vivo. Cada pantalla /monitor se conecta aquí y
    recibe en tiempo real todas las alertas que entran por /api/elk/ingest."""
    sub_id, queue = feed.subscribe()

    async def event_generator():
        # Hidratar con los últimos eventos para contexto inmediato
        yield "event: hello\ndata: {}\n\n"
        for ev in feed.history()[-15:]:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            feed.unsubscribe(sub_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/monitor", response_class=HTMLResponse)
async def monitor(request: Request):
    """Pantalla del Monitor en Vivo — radar de alertas ELK entrantes."""
    return templates.TemplateResponse(
        "monitor.html",
        {"request": request, "asset_version": _asset_version()},
    )


@app.get("/api/run/{run_id}/stream")
async def api_stream(run_id: str, request: Request):
    """Stream SSE de eventos del run.

    Cliente abre EventSource(`/api/run/<id>/stream`). El servidor itera la
    queue del bus y envia cada evento como 'data: {...}\n\n'. Cierra al
    recibir un evento type='done' o al desconectar el cliente.
    """
    if not bus.exists(run_id):
        raise HTTPException(404, f"run_id no encontrado: {run_id}")

    async def event_generator():
        # Heartbeat inicial para que el browser confirme conexion
        yield "event: hello\ndata: {}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await bus.get(run_id, timeout=10.0)
                if event is None:
                    # Heartbeat (mantiene conexion viva ante proxies/timeouts)
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            bus.unregister(run_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx no-buffer si llegase a estar detras
        },
    )
