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

from . import bridge_runner, info_views, mock_events
from .event_bus import bus
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
        from azure.identity import DefaultAzureCredential

        project = AIProjectClient(
            endpoint=bridge_l2.PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(exclude_environment_credential=True),
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Pagina principal del dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "force_mock": _force_mock(),
            "scenarios": list_scenarios(),
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
    """Hallazgos abiertos con EAPPS (datos empiricos validados)."""
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

    # Pending de EAPPS: rechazar con 400 explicativo
    if is_pending(payload.scenario_id):
        raise HTTPException(
            400,
            f"Este escenario esta esperando datos de EAPPS y no se puede "
            f"ejecutar todavia. Razon: {scenario.get('pending_eapps_reason', 'pendiente')}",
        )

    # Modo mock: forzado por env var (FORCE_MOCK=1) o solicitado en el request
    use_mock = payload.mock or _force_mock()

    if use_mock:
        run_id = await bridge_runner.start_mock_run(payload.scenario_id, mock_events)
        return {"run_id": run_id, "mode": "mock"}

    # Modo real: resuelve prompt con filtros y lanza el bridge
    prompt = resolve_prompt(
        payload.scenario_id,
        free_text=payload.free_text,
        filters=payload.filters,
    )
    if not prompt:
        raise HTTPException(400, "Pregunta vacia (free_text requerido para free-text)")

    # Los filtros del UI se pasan tambien como force_extra_vars para que el
    # bridge los aplique en cada llamada a AWX, sobrescribiendo lo que el LLM
    # proponga. Esto garantiza que el filtro elegido en la UI llega 100% a
    # AWX aunque el modelo no respete el prompt al pie de la letra.
    run_id = await bridge_runner.start_run(
        user_question=prompt,
        no_setup=True,
        max_hops=8,
        force_extra_vars=payload.filters or None,
    )
    return {"run_id": run_id, "mode": "real"}


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
