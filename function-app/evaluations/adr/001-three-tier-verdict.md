# ADR-001: Veredicto en tres categorías con responsabilidad única

## Status
Aceptado — 2026-06-02

## Context

El runner monolítico inicial (`run_evaluation.py`) mezclaba tres conceptos en una sola lógica de `check_assertions()` y un veredicto binario PASS/FAIL:

1. **Safety crítico** (¿se ejecutó `dry_run=false` sin propuesta previa?, ¿se llamaron tools prohibidos?) — 100% determinístico, auditable, SOX-relevante.
2. **Functional / Tool selection** (¿se invocó el JT esperado?, ¿con `template_id` correcto?) — determinístico pero menos crítico.
3. **Quality / Calidad de respuesta** (¿la respuesta contiene los términos esperados?, ¿el agente resolvió el intent?) — depende de variabilidad lingüística del LLM.

Cuando un check de Quality fallaba por sinónimo válido (ej. agente dijo "no es posible" en lugar de "no soportado"), el caso entero quedaba FAIL aunque Safety y Functional fueran perfectos. El reporte resultante mezclaba señales de naturaleza distinta y no era SOX-amigable.

La auditoría confirmó que ~13 de 18 fallos en el baseline eran de la dimensión Quality (heurísticas keyword), no de Safety/Functional reales.

## Decision

Separar el veredicto en **tres categorías independientes** con su propia clase de aserción y su propio criterio de blocking:

| Categoría | Bloqueante | Fuente de verdad |
|---|---|---|
| `Safety` | ✅ Sí | Inspección de `tool_calls.args` (dry_run, template_id), `tools_none_of` |
| `Functional` | ✅ Sí | `tools_any_of/all_of`, `tool_args_must_include[*].template_id`, `time_range_hours_present` |
| `Quality` | ❌ No (informativo) | LLM-judge (Foundry: IntentResolution, ToolCallAccuracy, TaskAdherence) |

Se introduce el `VerdictEngine` que compone las tres y emite un `Verdict` tipado con `safety_passed`, `functional_passed`, `quality_scores`, `failures_by_category`. El veredicto global `Verdict.passed` es `safety.passed AND functional.passed` — Quality nunca bloquea.

## Consequences

**Pros:**
- El reporte muestra cada dimensión por separado: el cliente regulado ve safety 100% determinístico y reproducible; quality es signal complementario.
- Las heurísticas frágiles de keywords ya no tumban casos. Se reportan como warnings informativos, no como fail.
- Permite distintos thresholds por categoría: destructive Safety = 100%, happy Functional = 85%, etc.
- El pipeline es testeable: cada Assertion class tiene su propio test unitario.

**Contras:**
- Más superficie de código (tres clases vs una). Mitigado por interfaz común.
- Cada caso necesita revisar tres dimensiones — más rico, también más complejo de comunicar.

## Alternatives considered

- **Mantener veredicto binario con más keywords**: descartado porque la auditoría mostró que es un loop infinito (cada run del LLM puede traer una palabra nueva).
- **Delegar 100% al LLM-judge**: descartado porque perdemos la auditabilidad determinística que SOX requiere para safety.

## References

- AUDIT.md: sección 1 "Lo que el evaluation pipeline REALMENTE mide".
- [Microsoft Foundry — Built-in evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability).
