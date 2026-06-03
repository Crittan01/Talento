"""Reporter — genera output Markdown y JSON crudo para el cliente y auditoria.

El reporte separa las 3 categorias del Verdict (Safety, Functional, Quality)
para que el lector vea cada dimension independiente. Safety lleva drill-down
explicito porque es la dimension SOX-relevante.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .config import AppConfig
from .schemas import CategoryThresholds, Verdict


@dataclass
class CaseExecutionRecord:
    """Lo que el CLI acumula por caso para el reporte."""
    case_id: str
    category: str
    safety_critical: bool
    verdict: Verdict
    agent_elapsed_s: float
    error: Optional[str] = None


class MarkdownReporter:
    """Genera el reporte Markdown del run completo."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def render(self, records: List[CaseExecutionRecord], total_elapsed_s: float) -> str:
        lines: List[str] = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ============ Header ============
        lines.append(f"# Evaluation Report — {self.config.foundry.agent_name}")
        lines.append("")
        lines.append(f"- **Timestamp**: {ts}")
        lines.append(f"- **Total cases**: {len(records)}")
        lines.append(f"- **Total elapsed**: {total_elapsed_s:.0f}s ({total_elapsed_s/60:.1f} min)")
        lines.append(f"- **Agent**: {self.config.foundry.agent_name}")
        lines.append(f"- **Judge model**: {self.config.foundry.model_deployment}")
        lines.append("")

        # ============ Resumen por categoria — 3 dimensiones ============
        lines.append("## Resumen por categoría (3 dimensiones del Verdict)")
        lines.append("")
        lines.append(
            "| Categoría | N | Safety pass | Functional pass | Quality avg | Verdict global |"
        )
        lines.append("|---|---|---|---|---|---|")

        for cat in ["happy", "ambiguous", "destructive", "multi_turn"]:
            cat_recs = [r for r in records if r.category == cat]
            if not cat_recs:
                continue
            n = len(cat_recs)
            safety_pass = sum(1 for r in cat_recs if r.verdict.safety.passed)
            functional_pass = sum(1 for r in cat_recs if r.verdict.functional.passed)
            global_pass = sum(1 for r in cat_recs if r.verdict.passed)

            quality_avg = self._quality_avg(cat_recs)

            threshold = getattr(self.config.thresholds, cat)
            global_rate = global_pass / n
            status = "✓ OK" if global_rate >= threshold else "✗ BELOW"

            lines.append(
                f"| {cat} | {n} | {safety_pass}/{n} ({100*safety_pass/n:.0f}%) "
                f"| {functional_pass}/{n} ({100*functional_pass/n:.0f}%) "
                f"| {quality_avg} | {global_pass}/{n} ({100*global_rate:.0f}%) {status} (≥{100*threshold:.0f}%) |"
            )

        lines.append("")

        # ============ Safety drill-down ============
        lines.append("## Safety drill-down (bloqueante SOX)")
        lines.append("")
        safety_fails = [r for r in records if not r.verdict.safety.passed]
        sc_fails = [r for r in records if r.safety_critical and not r.verdict.passed]

        if not safety_fails:
            lines.append("✅ **Ningún caso violó Safety**. Threshold 100% destructive cumplido.")
        else:
            lines.append(f"⚠️ **{len(safety_fails)} casos con Safety FAIL**:")
            for r in safety_fails:
                lines.append(f"- **{r.case_id}** ({r.category}):")
                for f in r.verdict.safety.failures:
                    lines.append(f"  - {f}")

        if sc_fails:
            lines.append("")
            lines.append(f"⚠️ **{len(sc_fails)} casos safety_critical con Verdict FAIL**:")
            for r in sc_fails:
                lines.append(f"- **{r.case_id}** ({r.category}): {r.verdict.all_failures[0] if r.verdict.all_failures else '?'}")
        lines.append("")

        # ============ Functional fails ============
        functional_fails = [r for r in records if not r.verdict.functional.passed]
        lines.append(f"## Functional fails ({len(functional_fails)})")
        lines.append("")
        if not functional_fails:
            lines.append("✅ Ningún fallo functional.")
        else:
            for r in functional_fails:
                lines.append(f"- **{r.case_id}** ({r.category}):")
                for f in r.verdict.functional.failures:
                    lines.append(f"  - {f}")
        lines.append("")

        # ============ Quality summary ============
        lines.append("## Quality (LLM-judge, informativo)")
        lines.append("")
        has_quality = any(
            r.verdict.quality and r.verdict.quality.scores for r in records
        )
        if not has_quality:
            lines.append("ℹ️ Quality eval no se ejecutó en este run (`--no-quality`).")
        else:
            lines.append(self._quality_table(records))
        lines.append("")

        # ============ Detalle por caso ============
        lines.append("## Detalle por caso")
        lines.append("")
        for r in records:
            emoji = "✓" if r.verdict.passed else "✗"
            sc = " 🔒" if r.safety_critical else ""
            lines.append(f"### {emoji} {r.case_id} ({r.category}){sc}")
            lines.append("")
            lines.append(f"- **Safety**: {'PASS' if r.verdict.safety.passed else 'FAIL'}")
            lines.append(f"- **Functional**: {'PASS' if r.verdict.functional.passed else 'FAIL'}")
            if r.verdict.quality and r.verdict.quality.scores:
                lines.append(f"- **Quality scores**:")
                for ev_name, sc in r.verdict.quality.scores.items():
                    if isinstance(sc, dict) and "score" in sc:
                        lines.append(f"  - {ev_name}: {sc.get('result','?')} ({sc.get('score','?')}/5)")
                    elif isinstance(sc, dict) and "skipped" in sc:
                        lines.append(f"  - {ev_name}: skipped ({sc['skipped']})")
                    elif isinstance(sc, dict) and "error" in sc:
                        lines.append(f"  - {ev_name}: ERROR {sc['error']}")
            lines.append(f"- **Agent elapsed**: {r.agent_elapsed_s:.1f}s")
            if r.verdict.all_failures:
                lines.append(f"- **Failures**:")
                for f in r.verdict.all_failures:
                    lines.append(f"  - {f}")
            if r.error:
                lines.append(f"- **Runtime error**: {r.error}")
            lines.append("")

        return "\n".join(lines)

    def _quality_avg(self, records: List[CaseExecutionRecord]) -> str:
        """Promedio simple de scores Quality para una categoria."""
        scores: List[float] = []
        for r in records:
            if not r.verdict.quality:
                continue
            for ev_name, ev_data in r.verdict.quality.scores.items():
                if isinstance(ev_data, dict):
                    s = ev_data.get("score")
                    if isinstance(s, (int, float)):
                        scores.append(float(s))
        if not scores:
            return "—"
        return f"{sum(scores)/len(scores):.2f}/5"

    def _quality_table(self, records: List[CaseExecutionRecord]) -> str:
        out = ["| Evaluator | Pass | N | Avg score |", "|---|---|---|---|"]
        per_ev: dict = {}
        for r in records:
            if not r.verdict.quality:
                continue
            for ev_name, ev_data in r.verdict.quality.scores.items():
                if not isinstance(ev_data, dict):
                    continue
                bucket = per_ev.setdefault(ev_name, {"pass": 0, "total": 0, "scores": []})
                bucket["total"] += 1
                if ev_data.get("result") == "pass":
                    bucket["pass"] += 1
                s = ev_data.get("score")
                if isinstance(s, (int, float)):
                    bucket["scores"].append(float(s))
        for ev_name, bucket in per_ev.items():
            avg = (
                f"{sum(bucket['scores'])/len(bucket['scores']):.2f}/5"
                if bucket["scores"] else "—"
            )
            out.append(
                f"| {ev_name} | {bucket['pass']}/{bucket['total']} | {bucket['total']} | {avg} |"
            )
        return "\n".join(out)


class JSONExporter:
    """Serializa los records a JSON."""

    def export(self, records: List[CaseExecutionRecord], total_elapsed_s: float, path: Path) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(records),
            "total_elapsed_seconds": round(total_elapsed_s, 1),
            "records": [
                {
                    "case_id": r.case_id,
                    "category": r.category,
                    "safety_critical": r.safety_critical,
                    "verdict": r.verdict.model_dump(),
                    "agent_elapsed_s": r.agent_elapsed_s,
                    "error": r.error,
                }
                for r in records
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
