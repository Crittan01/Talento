"""Parser de response.output del Foundry Responses API.

Convierte los items heterogeneos de response.output en estructuras tipadas
listas para consumir por el runner:
  - function_call -> requires execution (KQL/AWX) + alimenta siguiente hop
  - file_search_call -> registrar como tool usado (server-side)
  - message -> extraer texto final
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import ObservedToolCall


@dataclass
class FunctionCallItem:
    """Una function_call extraida que requiere ejecucion."""
    call_id: str
    name: str
    args: Dict[str, Any]


@dataclass
class ParsedResponse:
    """Resultado de parsear response.output de UN hop del agente.

    Contiene:
      - text_chunks: trozos de texto del agente en este hop
      - function_calls: tool calls que requieren ejecucion para el siguiente hop
      - observed_tool_calls: registros para reportar (incluye file_search server-side)
    """
    text_chunks: List[str] = field(default_factory=list)
    function_calls: List[FunctionCallItem] = field(default_factory=list)
    observed_tool_calls: List[ObservedToolCall] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.text_chunks)

    @property
    def has_pending_calls(self) -> bool:
        return bool(self.function_calls)


def parse_response_output(response, turn: int, hop: int) -> ParsedResponse:
    """Parsea response.output, agnostico al SDK underlying.

    El response viene del openai_client.responses.create(...). Sus items
    pueden ser:
      - {type: 'function_call', name, arguments(str), call_id}
      - {type: 'file_search_call', ...}   (server-side, sin args expuestos)
      - {type: 'message', content: [{text: {value}}]}
    """
    parsed = ParsedResponse()

    for item in getattr(response, "output", []):
        itype = getattr(item, "type", None)

        if itype == "function_call":
            try:
                args = json.loads(item.arguments) if item.arguments else {}
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": str(item.arguments)[:200]}
            parsed.function_calls.append(FunctionCallItem(
                call_id=item.call_id,
                name=item.name,
                args=args,
            ))
            parsed.observed_tool_calls.append(ObservedToolCall(
                name=item.name,
                args=args,
                turn=turn,
                hop=hop,
            ))

        elif itype == "file_search_call":
            # Tool integrado server-side. Sin args expuestos. Solo registramos.
            parsed.observed_tool_calls.append(ObservedToolCall(
                name="file_search",
                args={},
                turn=turn,
                hop=hop,
            ))

        elif itype == "message":
            content = getattr(item, "content", None) or []
            for c in content:
                text_obj = getattr(c, "text", None)
                if text_obj is not None:
                    # text_obj puede ser str o objeto con .value
                    value = getattr(text_obj, "value", None) or text_obj
                    if value:
                        parsed.text_chunks.append(str(value))

    return parsed


def get_output_text_fallback(response) -> str:
    """Fallback cuando no hay items message — algunos SDKs exponen output_text."""
    return getattr(response, "output_text", "") or ""
