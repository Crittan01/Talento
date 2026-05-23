"""event_bus — gestor thread-safe de queues por run_id para SSE.

Cada click en una card crea un run_id (uuid). El bridge corre en un thread
worker y emite eventos via callback. El callback hace queue.put_nowait().
El endpoint SSE consume la queue y los envia al browser.

Diseñado para soportar concurrencia: multiples runs simultaneos cada uno con
su propia queue aislada.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Optional


class EventBus:
    """Registro de asyncio.Queue por run_id."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}
        self._loops: Dict[str, asyncio.AbstractEventLoop] = {}

    def register(self, loop: asyncio.AbstractEventLoop) -> str:
        """Crea un run_id nuevo y su queue asociada. Devuelve el run_id."""
        run_id = uuid.uuid4().hex
        self._queues[run_id] = asyncio.Queue()
        self._loops[run_id] = loop
        return run_id

    def emit_threadsafe(self, run_id: str, event: dict) -> None:
        """Emite un evento desde un thread distinto al del event loop.

        El bridge llama esto desde su worker thread. Usa call_soon_threadsafe
        para encolar en la queue asyncio del loop principal.
        """
        if run_id not in self._queues:
            return
        loop = self._loops.get(run_id)
        queue = self._queues.get(run_id)
        if loop is None or queue is None:
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            # Loop cerrado, ignoramos
            pass

    async def get(self, run_id: str, timeout: float = 180.0) -> Optional[dict]:
        """Espera el siguiente evento de un run_id. Devuelve None en timeout."""
        queue = self._queues.get(run_id)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def unregister(self, run_id: str) -> None:
        """Limpia recursos del run_id (se llama al cerrar la SSE)."""
        self._queues.pop(run_id, None)
        self._loops.pop(run_id, None)

    def exists(self, run_id: str) -> bool:
        return run_id in self._queues


# Singleton global usado por la app
bus = EventBus()
