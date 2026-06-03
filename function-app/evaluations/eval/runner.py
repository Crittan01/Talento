"""AgentRunner — invoca al agente Foundry y captura el signal completo.

Orquesta:
  1. Crear conversation_id por caso.
  2. Por cada turn del usuario: enviar input, parsear response.output, ejecutar
     tools via ToolExecutor, alimentar siguiente hop hasta no haber function_calls.
  3. Acumular tool_calls observados + final_text + multi-turn.

Salida: RunResult tipado, listo para consumir por el VerdictEngine.
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from typing import List, Optional

from .config import AppConfig
from .response_parser import parse_response_output, get_output_text_fallback
from .schemas import CaseDefinition, ObservedToolCall, RunResult
from .tool_executor import ToolExecutor

logger = logging.getLogger("eval.runner")


class AgentRunner:
    """Invoca al agente y captura RunResult tipado.

    No depende de bridge_l2 directamente — todo I/O pasa por inyecciones:
      - project: AIProjectClient (Foundry)
      - executor: ToolExecutor (bridge real o mock)
      - config: AppConfig
    """

    def __init__(
        self,
        project,
        config: AppConfig,
        executor: ToolExecutor,
    ) -> None:
        self.project = project
        self.config = config
        self.executor = executor

    def run(self, case: CaseDefinition) -> RunResult:
        """Ejecuta el agente sobre el caso. Manejo de errores robusto."""
        client = self.project.get_openai_client()
        conversation = client.conversations.create()

        user_messages: List[dict] = []
        final_text = ""
        all_tool_calls: List[ObservedToolCall] = []
        total_hops = 0
        error: Optional[str] = None

        turns = case.turns or [{"role": "user", "content": case.query}]
        t0 = time.time()

        try:
            for turn_idx, turn in enumerate(turns):
                turn_num = turn_idx + 1
                user_content = turn["content"] if isinstance(turn, dict) else turn.content
                user_messages.append({"role": "user", "content": user_content})

                response = client.responses.create(
                    input=user_content,
                    conversation=conversation.id,
                    extra_body={
                        "agent_reference": {
                            "name": self.config.foundry.agent_name,
                            "type": "agent_reference",
                        }
                    },
                )

                # Multi-hop dentro del turn
                hops_done = 0
                pending_at_exit = False
                for hop in range(1, self.config.runner.max_hops_per_turn + 1):
                    total_hops += 1
                    hops_done = hop
                    parsed = parse_response_output(response, turn=turn_num, hop=hop)
                    all_tool_calls.extend(parsed.observed_tool_calls)

                    if parsed.text:
                        final_text = parsed.text

                    if not parsed.has_pending_calls:
                        break  # turn complete

                    # Ejecutar function_calls y alimentar siguiente hop
                    fn_outputs = self._execute_function_calls(parsed.function_calls)
                    response = client.responses.create(
                        input=fn_outputs,
                        conversation=conversation.id,
                        extra_body={
                            "agent_reference": {
                                "name": self.config.foundry.agent_name,
                                "type": "agent_reference",
                            }
                        },
                    )
                else:
                    # Loop agotado por max_hops con respuesta aun pendiente.
                    # Marcar para drenar y NO romper la conversacion.
                    pending_at_exit = True

                # Drain final: si el ultimo response tiene pending calls que no
                # se procesaron, ejecutarlas y enviar fn_outputs para cerrar.
                # Esto previene "No tool output found for function call" en el
                # siguiente turn.
                if pending_at_exit:
                    last_parsed = parse_response_output(
                        response, turn=turn_num, hop=hops_done + 1,
                    )
                    if last_parsed.has_pending_calls:
                        drain_outputs = self._execute_function_calls(last_parsed.function_calls)
                        all_tool_calls.extend(last_parsed.observed_tool_calls)
                        total_hops += 1
                        try:
                            response = client.responses.create(
                                input=drain_outputs,
                                conversation=conversation.id,
                                extra_body={
                                    "agent_reference": {
                                        "name": self.config.foundry.agent_name,
                                        "type": "agent_reference",
                                    }
                                },
                            )
                            drained = parse_response_output(
                                response, turn=turn_num, hop=hops_done + 2,
                            )
                            all_tool_calls.extend(drained.observed_tool_calls)
                            if drained.text:
                                final_text = drained.text
                        except Exception as drain_err:
                            logger.warning(
                                "Drain final fallo en %s turn %d: %s",
                                case.case_id, turn_num, drain_err,
                            )

            if not final_text:
                final_text = get_output_text_fallback(response) or "[sin respuesta]"

        except Exception as e:
            error = f"{type(e).__name__}: {str(e)[:400]}"
            logger.exception("AgentRunner caught error for case %s", case.case_id)

        elapsed = time.time() - t0
        return RunResult(
            case_id=case.case_id,
            final_text=final_text,
            tool_calls=all_tool_calls,
            user_messages=user_messages,
            hops=total_hops,
            elapsed_seconds=round(elapsed, 2),
            error=error,
        )

    def _execute_function_calls(self, function_calls) -> list:
        """Ejecuta cada function_call via ToolExecutor y construye los outputs."""
        fn_outputs = []
        truncate = self.config.runner.tool_output_truncate_chars

        for fc in function_calls:
            if fc.name == "query_log_analytics":
                kql = fc.args.get("query", "")
                result = self.executor.execute_kql(kql)
            elif fc.name == "run_awx_job_template":
                template_id = fc.args.get("template_id")
                ev_raw = fc.args.get("extra_vars_json", "{}")
                try:
                    ev = json.loads(ev_raw) if isinstance(ev_raw, str) and ev_raw.strip() else {}
                except json.JSONDecodeError:
                    ev = {}
                result = self.executor.execute_awx(template_id, ev)
            else:
                result = {"error": f"unknown tool: {fc.name}"}

            fn_outputs.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": json.dumps(result, ensure_ascii=False)[:truncate],
            })

        return fn_outputs
