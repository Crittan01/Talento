"""CLI: `python -m eval run [options]`

Orquesta el pipeline completo:
  1. Carga el dataset (golden_dataset.jsonl) y valida con Pydantic.
  2. Conecta a Foundry con AzureCliCredential.
  3. Inicializa SecretsResolver, ToolExecutor, FoundryEvaluatorSuite.
  4. Por cada caso: AgentRunner → VerdictEngine → record.
  5. Reporter emite Markdown + JSON con timestamp.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

from .config import AppConfig, apply_env_for_bridge, load_dotenv_safely
from .foundry_eval import FoundryEvaluatorSuite
from .foundry_publish import publish_to_portal
from .reporter import CaseExecutionRecord, JSONExporter, MarkdownReporter
from .runner import AgentRunner
from .schemas import CaseDefinition, RunResult
from .secrets import SecretsResolver
from .tool_executor import BridgeToolExecutor, HttpToolExecutor
from .verdict import QualityEvaluation, VerdictEngine


logger = logging.getLogger("eval")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def load_cases(config: AppConfig, case_ids: Optional[List[str]]) -> List[CaseDefinition]:
    """Carga el JSONL y filtra por case_ids si se especificaron."""
    cases: List[CaseDefinition] = []
    with open(config.paths.dataset_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            cases.append(CaseDefinition.model_validate(data))

    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c.case_id in wanted]
    return cases


def build_system_prompt(config: AppConfig) -> str:
    """Carga el system prompt del bridge para que el LLM-judge tenga el ground truth.

    Asegura el path al function-app dir (donde vive bridge_l2.py).
    """
    function_app_dir = str(config.paths.evaluations_root.parent)
    if function_app_dir not in sys.path:
        sys.path.insert(0, function_app_dir)
    import bridge_l2
    return bridge_l2.build_system_instructions()


def execute(args) -> int:
    config = AppConfig()
    setup_logging(args.verbose)
    logger.info("Iniciando eval pipeline contra %s", config.foundry.agent_name)

    # 1. Cargar env (filtrando SP de bridge_l2)
    env_vars = load_dotenv_safely(config.paths.env_file)
    apply_env_for_bridge(env_vars)

    # 2. Auth Foundry via AzureCliCredential
    credential = AzureCliCredential()
    project = AIProjectClient(endpoint=config.foundry.project_endpoint, credential=credential)
    logger.info("Conectado a %s", config.foundry.project_endpoint)

    # 3. Secrets + Executor + Quality
    secrets = SecretsResolver(config, credential=credential)
    if args.executor == "http":
        executor = HttpToolExecutor(config)
        logger.info("ToolExecutor: HTTP (delegando al Function App)")
    else:
        executor = BridgeToolExecutor(config, secrets)
        logger.info("ToolExecutor: bridge (directo desde cliente local)")
    quality: Optional[QualityEvaluation] = None
    if not args.no_quality:
        system_prompt = build_system_prompt(config)
        suite = FoundryEvaluatorSuite(config, secrets, system_prompt)
        quality = QualityEvaluation(foundry_evaluator=suite)
        logger.info("LLM-judge habilitado (deployment=%s)", config.foundry.model_deployment)
    else:
        logger.info("LLM-judge DESHABILITADO (--no-quality)")

    # 4. Cases + engine + runner
    cases = load_cases(config, args.case_ids.split(",") if args.case_ids else None)
    if args.limit:
        cases = cases[: args.limit]
    logger.info("Casos a ejecutar: %d", len(cases))

    runner = AgentRunner(project, config, executor)
    engine = VerdictEngine(quality=quality) if quality else VerdictEngine()

    # 5. Loop principal
    records: List[CaseExecutionRecord] = []
    runs_by_id: dict = {}   # case_id -> RunResult (para publish opcional)
    cases_by_id: dict = {case.case_id: case for case in cases}
    t_start = time.time()

    for idx, case in enumerate(cases, 1):
        case_t0 = time.time()
        print(f"[{idx:2}/{len(cases)}] {case.case_id} ({case.category}) — ", end="", flush=True)

        run_result = runner.run(case)
        elapsed = time.time() - case_t0
        runs_by_id[case.case_id] = run_result

        if run_result.error:
            print(f"⚠ AGENT ERROR ({run_result.error[:60]})")
            verdict = engine.evaluate(case, run_result)
            records.append(CaseExecutionRecord(
                case_id=case.case_id,
                category=case.category,
                safety_critical=case.safety_critical,
                verdict=verdict,
                agent_elapsed_s=elapsed,
                error=run_result.error,
            ))
            continue

        verdict = engine.evaluate(case, run_result)
        records.append(CaseExecutionRecord(
            case_id=case.case_id,
            category=case.category,
            safety_critical=case.safety_critical,
            verdict=verdict,
            agent_elapsed_s=elapsed,
        ))

        global_pass = "PASS" if verdict.passed else "FAIL"
        tools = ",".join(sorted({tc.name for tc in run_result.tool_calls}))
        print(f"{global_pass} ({elapsed:.0f}s, tools=[{tools or '—'}], hops={run_result.hops})")
        if not verdict.passed:
            for f in verdict.all_failures[:2]:
                print(f"           {f[:120]}")

    total_elapsed = time.time() - t_start
    print(f"\nTotal: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)\n")

    # 6. Reporting
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    config.paths.results_dir.mkdir(parents=True, exist_ok=True)

    json_path = config.paths.results_dir / f"run_{ts}.json"
    JSONExporter().export(records, total_elapsed, json_path)
    print(f"► JSON: {json_path}")

    md_path = config.paths.results_dir / f"report_{ts}.md"
    md_content = MarkdownReporter(config).render(records, total_elapsed)
    md_path.write_text(md_content)
    print(f"► Reporte: {md_path}")

    # 7. Publish opcional al portal Foundry
    if args.publish:
        if args.no_quality:
            print("⚠ --publish requiere --quality (LLM-judge necesario para el portal)")
        else:
            system_prompt = build_system_prompt(config)
            print("\n► Publicando al portal Foundry...")
            studio_url = publish_to_portal(
                config=config,
                secrets=secrets,
                system_prompt=system_prompt,
                cases_by_id=cases_by_id,
                runs_by_id=runs_by_id,
                evaluation_name=f"{args.evaluation_name}_{ts}",
            )
            if studio_url:
                print(f"► Portal Foundry: {studio_url}")

    # 8. Exit code segun threshold
    blocking_fails = sum(1 for r in records if not r.verdict.passed)
    return 0 if blocking_fails == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval", description="Eval pipeline para talento-triage-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Ejecuta el eval sobre el dataset")
    run.add_argument("--case-ids", help="Coma-separados (ej H01,D04)")
    run.add_argument("--limit", type=int, help="Solo primeros N casos")
    run.add_argument("--no-quality", action="store_true", help="Skip LLM-judge")
    run.add_argument(
        "--executor", choices=["http", "bridge"], default="http",
        help="http: tools via Function App (default). bridge: directo desde cliente local",
    )
    run.add_argument(
        "--publish", action="store_true",
        help="Publicar resultados al portal Foundry (ademas del reporte local)",
    )
    run.add_argument(
        "--evaluation-name", default="talento-triage-agent",
        help="Nombre del run en el portal Foundry (con --publish)",
    )
    run.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    if args.cmd == "run":
        return execute(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
