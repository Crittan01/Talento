"""Builder del golden_dataset.jsonl desde los cases tipados.

Uso:
  python3 -m dataset.builder

Validacion: Pydantic falla si algun caso es invalido. Asserts adicionales
verifican distribucion + IDs unicos.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Hacer eval/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.config import AppConfig
from eval.schemas import CaseDefinition
from .cases.ambiguous import ambiguous_cases
from .cases.destructive import destructive_cases
from .cases.happy import happy_cases
from .cases.multi_turn import multi_turn_cases


EXPECTED_DISTRIBUTION = {
    "happy": 15,
    "ambiguous": 15,
    "destructive": 10,
    "multi_turn": 10,
}


def build_all_cases() -> list[CaseDefinition]:
    return [
        *happy_cases(),
        *ambiguous_cases(),
        *destructive_cases(),
        *multi_turn_cases(),
    ]


def validate(cases: list[CaseDefinition]) -> None:
    assert len(cases) == sum(EXPECTED_DISTRIBUTION.values()), (
        f"Esperaba {sum(EXPECTED_DISTRIBUTION.values())} casos, obtuve {len(cases)}"
    )

    ids = [c.case_id for c in cases]
    duplicates = [i for i, count in Counter(ids).items() if count > 1]
    assert not duplicates, f"IDs duplicados: {duplicates}"

    actual = Counter(c.category for c in cases)
    for cat, expected_n in EXPECTED_DISTRIBUTION.items():
        assert actual[cat] == expected_n, (
            f"Distribucion {cat}: esperaba {expected_n}, obtuve {actual[cat]}"
        )


def serialize(cases: list[CaseDefinition], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for case in cases:
            data = case.model_dump(exclude_none=True)
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def main() -> int:
    cases = build_all_cases()
    validate(cases)
    config = AppConfig()
    out_path = config.paths.dataset_jsonl
    serialize(cases, out_path)

    safety_n = sum(1 for c in cases if c.safety_critical)
    print(f"✓ {len(cases)} casos serializados a {out_path}")
    print(f"  Distribucion: {dict(Counter(c.category for c in cases))}")
    print(f"  Safety critical: {safety_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
