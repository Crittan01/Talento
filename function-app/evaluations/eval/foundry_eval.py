"""Wrappers de los Foundry LLM-judge evaluators con api_key auth.

ADR-002: usar api_key en model_config en lugar de AAD token provider para evitar
401 en AsyncAzureOpenAI. El api_key se obtiene via SecretsResolver (Azure SDK,
no subprocess).

Esta clase encapsula la construccion de:
  - query: lista OpenAI-style messages (system + user turns)
  - response: lista con el assistant message final
  - tool_calls + tool_definitions: para ToolCallAccuracy

Y aplica los evaluators:
  - IntentResolutionEvaluator: ¿el agente entendio la intencion?
  - ToolCallAccuracyEvaluator: ¿llamó tools correctos con args correctos?
  - TaskAdherenceEvaluator: ¿siguio el system prompt?

Las salidas son normalizadas a un dict por evaluator con campos `score`,
`result` ('pass'/'fail'), `threshold`, `reason`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .config import AppConfig
from .schemas import CaseDefinition, RunResult
from .secrets import SecretsResolver

logger = logging.getLogger("eval.foundry")


# Tool definitions exactas (extraidas de bridge_l2 TOOL_QUERY_LA y build_tool_run_awx).
# Mantenerlas aqui las desacopla del bridge — si cambian alli, se actualizan aqui.
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "query_log_analytics",
        "description": (
            "Ejecuta una consulta KQL contra el workspace de Log Analytics de TALENTO."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query KQL"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_awx_job_template",
        "description": (
            "Lanza un Job Template en AWX por su template_id con extra_vars opcionales."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {"type": "integer"},
                "extra_vars_json": {"type": "string"},
            },
            "required": ["template_id", "extra_vars_json"],
        },
    },
    {
        "name": "file_search",
        "description": "Consulta la knowledge base de TALENTO.",
        "parameters": {"type": "object", "properties": {}},
    },
]


# Mapping de nombre de evaluator -> prefix del key en su output dict
_KEY_PREFIX = {
    "IntentResolution": "intent_resolution",
    "ToolCallAccuracy": "tool_call_accuracy",
    "TaskAdherence": "task_adherence",
}


def _normalize_result(ev_name: str, raw: dict) -> dict:
    """Extrae los campos relevantes del output de un evaluator."""
    prefix = _KEY_PREFIX.get(ev_name, ev_name.lower())
    return {
        "score": raw.get(prefix),
        "result": raw.get(f"{prefix}_result"),
        "threshold": raw.get(f"{prefix}_threshold"),
        "reason": (raw.get(f"{prefix}_reason") or "")[:300],
    }


def _build_query_messages(case: CaseDefinition, run: RunResult, system_prompt: str) -> list:
    """Construye query para evaluators: system + user turns."""
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    for um in run.user_messages:
        messages.append(um)
    return messages


def _build_response_messages(run: RunResult) -> list:
    """Construye response para evaluators: assistant final message."""
    return [{
        "role": "assistant",
        "content": [{"type": "text", "text": run.final_text}],
    }]


def _build_tool_calls_for_eval(run: RunResult) -> list:
    """Convierte ObservedToolCall a formato OpenAI tool_call."""
    out = []
    for tc in run.tool_calls:
        if tc.name in ("query_log_analytics", "run_awx_job_template"):
            out.append({
                "type": "tool_call",
                "tool_call_id": f"call_{tc.turn}_{tc.hop}_{tc.name}",
                "name": tc.name,
                "arguments": tc.args,
            })
    return out


class FoundryEvaluatorSuite:
    """Compone los 3 evaluators de Foundry y aplica al pipeline."""

    def __init__(
        self,
        config: AppConfig,
        secrets: SecretsResolver,
        system_prompt: str,
    ) -> None:
        self.config = config
        self.secrets = secrets
        self.system_prompt = system_prompt
        self._evaluators: Optional[dict] = None

    def _ensure_evaluators(self) -> dict:
        """Lazy-init de los evaluators (carga el SDK al primer uso)."""
        if self._evaluators is not None:
            return self._evaluators

        from azure.ai.evaluation import (
            IntentResolutionEvaluator,
            ToolCallAccuracyEvaluator,
            TaskAdherenceEvaluator,
        )

        model_config = self.secrets.model_config_for_evaluator()
        logger.info(
            "Inicializando FoundryEvaluatorSuite con deployment=%s",
            model_config["azure_deployment"],
        )

        self._evaluators = {
            "IntentResolution": IntentResolutionEvaluator(model_config=model_config),
            "ToolCallAccuracy": ToolCallAccuracyEvaluator(model_config=model_config),
            "TaskAdherence": TaskAdherenceEvaluator(model_config=model_config),
        }
        return self._evaluators

    def evaluate(self, case: CaseDefinition, run: RunResult) -> Dict[str, Any]:
        """Aplica los 3 evaluators sobre el run. Devuelve dict ev_name -> result."""
        evaluators = self._ensure_evaluators()

        query_msgs = _build_query_messages(case, run, self.system_prompt)
        response_msgs = _build_response_messages(run)
        tool_calls = _build_tool_calls_for_eval(run)

        scores: Dict[str, Any] = {}
        for ev_name, evaluator in evaluators.items():
            try:
                if ev_name == "ToolCallAccuracy":
                    if not tool_calls:
                        scores[ev_name] = {"skipped": "no_tool_calls"}
                        continue
                    raw = evaluator(
                        query=query_msgs,
                        tool_calls=tool_calls,
                        tool_definitions=TOOL_DEFINITIONS,
                    )
                else:
                    raw = evaluator(query=query_msgs, response=response_msgs)
                scores[ev_name] = _normalize_result(ev_name, raw)
            except Exception as e:
                logger.warning("%s fallo para %s: %s", ev_name, case.case_id, e)
                scores[ev_name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}

        return scores
