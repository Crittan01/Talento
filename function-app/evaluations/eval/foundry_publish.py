"""Publicar resultados de eval al portal Foundry.

El SDK `azure-ai-evaluation` expone `evaluate()` que acepta un JSONL local +
`azure_ai_project` y SUBE los resultados al portal Foundry, devolviendo una
`studio_url` clicable. Esto permite que el cliente (Ecopetrol) vea el
dashboard nativo de Foundry Evaluations sin recibir archivos sueltos.

Este modulo es OPCIONAL — el pipeline funciona local-only sin el. Se activa
con el flag CLI `--publish`.

Reusamos los `RunResult` y `CaseDefinition` ya capturados — construimos el
JSONL en memoria con el schema que esperan los evaluators (query, response,
tool_calls, tool_definitions) y delegamos a `evaluate()`.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AppConfig
from .foundry_eval import TOOL_DEFINITIONS, _build_query_messages, _build_response_messages, _build_tool_calls_for_eval
from .reporter import CaseExecutionRecord
from .schemas import CaseDefinition, RunResult
from .secrets import SecretsResolver

logger = logging.getLogger("eval.publish")


def _record_to_dataset_row(
    case: CaseDefinition,
    run: RunResult,
    system_prompt: str,
) -> Dict[str, Any]:
    """Convierte un (caso, run) a una fila del JSONL que evaluate() consume.

    Los evaluators de Foundry esperan keys: query, response, tool_calls,
    tool_definitions, ground_truth (opcional).
    """
    return {
        "case_id": case.case_id,
        "category": case.category,
        "query": _build_query_messages(case, run, system_prompt),
        "response": _build_response_messages(run),
        "tool_calls": _build_tool_calls_for_eval(run),
        "tool_definitions": TOOL_DEFINITIONS,
        "ground_truth": case.expected.intent_summary,
    }


def write_evaluation_jsonl(
    cases_by_id: Dict[str, CaseDefinition],
    runs_by_id: Dict[str, RunResult],
    system_prompt: str,
    out_path: Path,
) -> int:
    """Serializa el dataset para el batch `evaluate()`. Retorna N filas."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for case_id, run in runs_by_id.items():
            case = cases_by_id.get(case_id)
            if case is None:
                continue
            # Skip casos con error o sin tool_calls (evaluate los rechaza)
            if run.error and not run.tool_calls:
                continue
            row = _record_to_dataset_row(case, run, system_prompt)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


class _ScopedEnvUnset:
    """Context manager que retira temporalmente vars del env y las restaura.

    Necesario porque el SDK azure-ai-evaluation usa DefaultAzureCredential
    internamente para el upload al portal Foundry, y si las vars del SP de
    bridge_l2 (AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET) estan en os.environ
    el SDK preferiria ese SP en lugar de la identidad de az login.

    Solo afecta el scope del publish — al salir restaura las vars originales
    para que bridge_l2 siga funcionando si llega a usarse despues.
    """

    KEYS = ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")

    def __init__(self):
        self._saved = {}

    def __enter__(self):
        import os
        for k in self.KEYS:
            if k in os.environ:
                self._saved[k] = os.environ.pop(k)
        if self._saved:
            logger.info(
                "Scoped unset de %s para forzar AzureCliCredential en publish",
                list(self._saved.keys()),
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import os
        for k, v in self._saved.items():
            os.environ[k] = v
        return False


def publish_to_portal(
    config: AppConfig,
    secrets: SecretsResolver,
    system_prompt: str,
    cases_by_id: Dict[str, CaseDefinition],
    runs_by_id: Dict[str, RunResult],
    evaluation_name: str,
) -> Optional[str]:
    """Sube los runs al portal Foundry usando evaluate() batch API.

    Retorna la studio_url o None si fallo.
    """
    from azure.ai.evaluation import (
        IntentResolutionEvaluator,
        TaskAdherenceEvaluator,
        ToolCallAccuracyEvaluator,
        evaluate,
    )

    model_config = secrets.model_config_for_evaluator()
    evaluators = {
        "intent_resolution": IntentResolutionEvaluator(model_config=model_config),
        "tool_call_accuracy": ToolCallAccuracyEvaluator(model_config=model_config),
        "task_adherence": TaskAdherenceEvaluator(model_config=model_config),
    }

    with tempfile.TemporaryDirectory() as tmp:
        jsonl_path = Path(tmp) / "eval_input.jsonl"
        n_rows = write_evaluation_jsonl(
            cases_by_id, runs_by_id, system_prompt, jsonl_path,
        )
        if n_rows == 0:
            logger.warning("No hay filas para publicar (todos los runs tenian error sin tool_calls)")
            return None

        logger.info("Publicando %d casos al portal Foundry (%s)", n_rows, evaluation_name)

        # azure_ai_project espera el endpoint del project
        azure_ai_project = config.foundry.project_endpoint

        try:
            with _ScopedEnvUnset():
                response = evaluate(
                    data=str(jsonl_path),
                    evaluation_name=evaluation_name,
                    evaluators=evaluators,
                    azure_ai_project=azure_ai_project,
                )
            studio_url = response.get("studio_url") if isinstance(response, dict) else None
            if studio_url:
                logger.info("✓ Resultados publicados: %s", studio_url)
            return studio_url
        except Exception as exc:
            logger.exception("Publish al portal fallo: %s", exc)
            return None
