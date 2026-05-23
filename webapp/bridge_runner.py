"""bridge_runner — wrapper thread-safe del bridge_l2.run_cycle para la webapp.

Responsabilidades:
- Lanzar run_cycle en un thread worker (no bloquear el event loop).
- Construir el callback emit que reenvia a la EventBus via call_soon_threadsafe.
- Filtrar secrets antes de cualquier evento que viaje a SSE.
- Manejar errores del bridge y emitir agent.error en lugar de crash silencioso.
"""
from __future__ import annotations

import asyncio
import re
import sys
import traceback
from pathlib import Path
from typing import Optional

# Importar bridge_l2 del directorio padre
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bridge_l2  # noqa: E402

from .event_bus import bus  # noqa: E402

# Patrones para filtrar secrets que jamas deben salir por SSE
_SECRET_PATTERNS = [
    re.compile(re.escape(bridge_l2.ENV.get("AZURE_CLIENT_SECRET", "X" * 80))) if bridge_l2.ENV.get("AZURE_CLIENT_SECRET") else None,
    re.compile(re.escape(bridge_l2.ENV.get("AWX_TOKEN", "X" * 80))) if bridge_l2.ENV.get("AWX_TOKEN") else None,
    re.compile(re.escape(bridge_l2.ENV.get("TEAMS_WEBHOOK_URL", "X" * 80))) if bridge_l2.ENV.get("TEAMS_WEBHOOK_URL") else None,
]
_SECRET_PATTERNS = [p for p in _SECRET_PATTERNS if p is not None]


def _scrub(value):
    """Reemplaza secrets por '[REDACTED]' en cualquier valor anidado."""
    if isinstance(value, str):
        for pat in _SECRET_PATTERNS:
            value = pat.sub("[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _make_emit(run_id: str):
    """Devuelve un callback emit thread-safe que envia eventos a la EventBus."""
    def emit(event: dict) -> None:
        clean = _scrub(event)
        bus.emit_threadsafe(run_id, clean)
    return emit


async def start_run(
    user_question: str,
    no_setup: bool = True,
    max_hops: int = 4,
    force_extra_vars: Optional[dict] = None,
) -> str:
    """Lanza un run del bridge en un thread worker. Devuelve run_id.

    El caller usa run_id para conectarse a /api/run/{run_id}/stream y recibir
    los eventos SSE. El thread worker termina cuando run_cycle termina o
    fallaba.

    force_extra_vars: dict de valores que el bridge inyectara en CADA
    llamada a run_awx_job_template, sobrescribiendo lo que el LLM proponga.
    Esto garantiza que los filtros de la UI sean la fuente de verdad,
    incluso si el modelo ignora el prompt.
    """
    loop = asyncio.get_running_loop()
    run_id = bus.register(loop)
    emit = _make_emit(run_id)

    def _worker():
        """Corre en un thread aparte. Aqui llamamos al bridge sincrono."""
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            emit({"type": "agent.connecting"})
            # exclude_environment_credential=True: usar az login (usuario con
            # acceso a Foundry), no el SP del .env (que solo tiene LA Reader).
            project = AIProjectClient(
                endpoint=bridge_l2.PROJECT_ENDPOINT,
                credential=DefaultAzureCredential(exclude_environment_credential=True),
            )
            agent_name = bridge_l2.AGENT_NAME
            if not no_setup:
                emit({"type": "agent.setup_version"})
                agent = bridge_l2.setup_agent_version(project)
                agent_name = agent.name
                emit({
                    "type": "agent.version_ready",
                    "name": agent.name,
                    "version": agent.version,
                })

            bridge_l2.run_cycle(
                project=project,
                agent_name=agent_name,
                user_question=user_question,
                max_hops=max_hops,
                emit=emit,
                force_extra_vars=force_extra_vars,
            )
        except Exception as exc:
            emit({
                "type": "agent.error",
                "error": str(exc),
                "traceback": traceback.format_exc()[-1500:],
            })
            emit({"type": "done"})

    # Lanza el worker en un thread aparte sin bloquear el loop
    asyncio.create_task(asyncio.to_thread(_worker))
    return run_id


async def start_mock_run(scenario_id: str, mock_events_module) -> str:
    """Lanza un run de mock que reproduce eventos pregrabados.

    No toca Azure/AWX/Teams. Util para ensayar la demo sin riesgo.
    El modulo de mocks debe exponer get_events(scenario_id) -> list[(delay_s, event)].
    """
    loop = asyncio.get_running_loop()
    run_id = bus.register(loop)
    emit = _make_emit(run_id)

    async def _replay():
        events = mock_events_module.get_events(scenario_id)
        if not events:
            emit({
                "type": "agent.error",
                "error": f"No hay mock para scenario_id={scenario_id}",
            })
            emit({"type": "done"})
            return
        for delay, evt in events:
            await asyncio.sleep(delay)
            emit(evt)

    asyncio.create_task(_replay())
    return run_id
