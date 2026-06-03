# ADR-003: Schemas tipados con Pydantic en lugar de JSON manual

## Status
Aceptado — 2026-06-02

## Context

El dataset inicial vivía como `CASES = [...]` en `build_golden_dataset.py` (~700 líneas), una lista Python de dicts plana. Validación: 4 asserts al final del script (`len==50`, IDs únicos, query xor turns, intent_summary no vacío). Cada `expected` era un dict sin schema.

Problemas observados durante la iteración:
- Typos en keys (`tool_args_must_include` mal escrito) pasaban sin error hasta runtime.
- Markers especiales (`dry_run_must_be_true_or_unset`, `time_range_hours_present`) no estaban documentados — había que leer el runner para descubrir cuáles existían.
- Añadir/quitar campos requería editar el script + recordar actualizar los asserts.
- Refactor del runner exigía cambiar el formato del expected — no había contrato.

Pydantic v2 da: validación en build-time, error messages claros, IDE autocomplete, contratos explícitos como código.

## Decision

Definir **schemas Pydantic** en `eval/schemas.py` como single source of truth:

- `CaseDefinition` — un caso del dataset.
- `ExpectedBehavior` — aserciones esperadas (tools_any_of/all_of/none_of, tool_args_must_include, response_*, intent_summary).
- `ToolArgsConstraint` — marcadores válidos por tool (template_id, dry_run_must_be_true_or_unset, etc).
- `ConversationTurn` — mensaje del usuario en multi-turn.
- `ObservedToolCall`, `RunResult` — output del runner.
- `Verdict`, `CategoryVerdict`, `AssertionCheck` — output del VerdictEngine.

Validadores `@model_validator`:
- `query xor turns` en CaseDefinition (exactamente uno).
- `case_id` prefix coincide con `category` (`H` → happy, `D` → destructive, etc).
- `case_id` formato `^[HADM]\d{2}$`.
- `intent_summary` no vacío.

El dataset se genera vía un builder Python (`dataset/cases/*.py`) que produce instancias de `CaseDefinition`. El builder serializa a JSONL para mantener compatibilidad externa.

## Consequences

**Pros:**
- Validación temprana: typos y campos faltantes fallan en build, no en runtime.
- Documentación viva: el schema ES la spec.
- Contratos cumplidos en boundaries: el runner sabe que recibe `CaseDefinition` válido, el VerdictEngine sabe que recibe `RunResult` válido.
- Migración del legacy JSONL: el script de build puede parsear el JSONL viejo y devolver `CaseDefinition`s (compatibilidad backward).
- IDE autocomplete y type checking estático (mypy/pyright).

**Contras:**
- Pydantic v2 es una dependencia (peso ~ 10MB). Aceptable.
- `extra="forbid"` puede ser molesto durante iteración rápida — mitigado porque los campos legítimos están bien definidos.

## Estructura del schema en código

Ver `eval/schemas.py`. Decisiones específicas:

- `ToolArgsConstraint` es un modelo cerrado (`extra="forbid"`) con campos opcionales: cada marker es `Optional[X]` y vale solo si está presente. Esto previene typos como `dry_run_must_be_truee` que antes pasaban silenciosamente.
- `ExpectedBehavior.intent_summary` es obligatorio (`min_length=1`) — es el ground truth del `IntentResolutionEvaluator` de Foundry.
- `CategoryVerdict.scores: Dict[str, Any]` permite payloads heterogéneos de los evaluators (algunos devuelven dict, otros number).

## Alternatives considered

- **dataclasses + dataclass_validator de stdlib**: descartado porque no tiene validación nested ni mensajes amigables.
- **JSON Schema + jsonschema package**: descartado porque pierde el type hinting en Python; los validators son código distinto del schema.
- **Marshmallow**: descartado porque Pydantic v2 está más activo y tiene mejor perf.

## References

- [Pydantic v2 docs](https://docs.pydantic.dev/2.0/).
- AUDIT.md: sección 4 "Auditoría del código del runner".
