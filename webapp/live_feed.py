"""live_feed — broadcast bus para el Monitor en Vivo de alertas ELK.

A diferencia de event_bus (una queue por run_id, 1 productor → 1 consumidor),
este es un bus de BROADCAST: cuando una alerta entra por /api/elk/ingest, el
evento se replica a TODAS las pantallas del monitor conectadas simultaneamente.

Flujo:
  ELK → POST /api/elk/ingest → publish(evento) → todas las pantallas /monitor lo ven

Soporta multiples pantallas abiertas a la vez (operaciones, NOC, demo) — cada
una recibe el mismo stream en tiempo real.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from typing import Dict, Optional


class LiveFeed:
    """Broadcast bus thread-safe. Cada subscriber tiene su propia queue;
    publish() replica el evento a todas."""

    def __init__(self, history_size: int = 50) -> None:
        self._subscribers: Dict[str, asyncio.Queue] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # buffer de los ultimos N eventos para que una pantalla nueva tenga contexto
        self._history: deque = deque(maxlen=history_size)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Registra el event loop principal (para publish desde threads)."""
        self._loop = loop

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        """Registra una pantalla nueva. Devuelve (sub_id, queue)."""
        sub_id = uuid.uuid4().hex
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)

    def history(self) -> list:
        """Ultimos eventos para hidratar una pantalla recien conectada."""
        return list(self._history)

    def publish(self, event: dict) -> None:
        """Publica un evento a todas las pantallas. Thread-safe (el agente
        corre en un worker thread; las queues viven en el event loop)."""
        event = {**event, "_ts": time.time()}
        self._history.append(event)

        def _fanout():
            for q in list(self._subscribers.values()):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

        loop = self._loop
        if loop is None:
            # sin loop registrado todavia — solo queda en history
            return
        try:
            loop.call_soon_threadsafe(_fanout)
        except RuntimeError:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton global
feed = LiveFeed()
