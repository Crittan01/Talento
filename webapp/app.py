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

from . import bridge_runner, mock_events
from .event_bus import bus
from .scenarios import list_scenarios, resolve_prompt, get_scenario


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="TALENTO Operations Console")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _force_mock() -> bool:
    return os.environ.get("FORCE_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    scenario_id: str
    free_text: Optional[str] = None
    mock: bool = False


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
    return {"scenarios": list_scenarios(), "force_mock": _force_mock()}


@app.post("/api/run")
async def api_run(payload: RunRequest):
    """Lanza un run (real o mock) y devuelve run_id para conectar via SSE."""
    scenario = get_scenario(payload.scenario_id)
    if not scenario:
        raise HTTPException(404, f"scenario_id desconocido: {payload.scenario_id}")

    # Modo mock: forzado por env var (FORCE_MOCK=1) o solicitado en el request
    use_mock = payload.mock or _force_mock()

    if use_mock:
        run_id = await bridge_runner.start_mock_run(payload.scenario_id, mock_events)
        return {"run_id": run_id, "mode": "mock"}

    # Modo real: resuelve prompt y lanza el bridge
    prompt = resolve_prompt(payload.scenario_id, payload.free_text)
    if not prompt:
        raise HTTPException(400, "Pregunta vacia (free_text requerido para free-text)")

    run_id = await bridge_runner.start_run(
        user_question=prompt,
        no_setup=True,
        max_hops=4,
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
