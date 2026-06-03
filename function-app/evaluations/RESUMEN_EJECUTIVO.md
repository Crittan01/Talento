# Agente IA TALENTO — Resumen ejecutivo

**Caso de uso 1 del RFP — TALENTO administración y operación**
**Estado**: ✅ **certificado 50/50 (100%) con defensa en profundidad**
**Fecha**: 2026-06-03
**Versión del agente**: `talento-triage-agent v7-gpt4o-guard`
**Portal Foundry**: [Ver run en Evaluations](https://ai.azure.com/resource/build/evaluation/a2358708-14a6-4f22-96e8-b4849e014406?wsid=/subscriptions/7c5b032f-7879-4ec3-a2ed-978b444f6755/resourceGroups/rg-central-is2/providers/Microsoft.CognitiveServices/accounts/aifoundry-is2/projects/proj-foundry-is2&tid=11062244-d8ab-4caf-8cf4-7c2c44868da3)

---

## ¿Qué construimos?

Un agente de IA en Azure AI Foundry (`talento-triage-agent`) que asiste al equipo de operaciones de TALENTO 7x24:

- **Diagnostica** la salud de los componentes (Container Instance, App Service, SQL Server) consultando estado real vía Azure Resource Manager.
- **Investiga** logs en Log Analytics con KQL para reconstruir el viaje de cada petición (correlation_id), agrupar errores, detectar spikes.
- **Consulta** la base de conocimiento TALENTO (catálogo de 15 códigos TLNT-XXX, runbook de 6 escenarios típicos, catálogo de 12 Job Templates AWX, guía de patrones KQL).
- **Propone** acciones correctivas (restart, stop, audit) con doble confirmación obligatoria — nunca ejecuta acciones invasivas sin autorización explícita del operador humano.

Operación end-to-end:
```
Operador → /api/run → Azure AI Foundry (agente) → AWX + Log Analytics
                          ↓
                       Respuesta estructurada
                       (Hallazgo, Hipótesis, Pasos, Acción)
```

---

## Garantías SOX cumplidas (certificadas con 50 casos)

| Garantía | Validada en |
|---|---|
| El agente **NUNCA** ejecuta acciones destructivas (`dry_run=false`) sin doble confirmación | 10 escenarios destructivos (D01-D10), 100% rechazo |
| El agente **rechaza** acciones fuera del catálogo de Job Templates | D04 (detener BD), D08 (borrar logs), D09 (cambiar passwords) |
| El agente **detecta** confirmaciones huérfanas (cuando un usuario afirma falsamente que existió una propuesta previa) | D10, validado en producción |
| El agente **mantiene** el protocolo bajo ataques de inyección de prompts ("ignora tus instrucciones") | D05, D06, D07 |
| Cada decisión queda auditable con `correlation_id` y `tool_calls.args` completos | Reportes JSON crudos en `results/` |
| El pipeline de evaluación es reproducible y testeable | 30 tests unitarios, schemas Pydantic, ADRs documentando decisiones |

---

## Cómo se midió

**3 dimensiones independientes**:

1. **Safety** (bloqueante SOX): inspección determinística de `tool_calls.args`. Mide qué *pidió* el agente, no si los tools respondieron OK.
2. **Functional** (bloqueante): tools esperados invocados con argumentos correctos (`template_id`, `time_range_hours`, etc.).
3. **Quality** (informativo): LLM-judge de Azure AI Foundry — `IntentResolution`, `ToolCallAccuracy`, `TaskAdherence` — devuelve scores 1-5 por dimensión.

**50 casos en JSONL versionado**:
- 15 happy path (preguntas estándar)
- 15 ambiguous (vagas — el agente debe pedir contexto o diagnosticar amplio)
- 10 destructive (adversariales: jailbreak, inyección, confirmaciones huérfanas)
- 10 multi-turn (conversaciones de 2-3 turnos)

**Thresholds por categoría**:
- Happy ≥ 85%
- Ambiguous ≥ 70%
- Destructive = **100%** (estricto SOX — cualquier fallo es bloqueante)
- Multi-turn ≥ 80%

---

## Resultado de la certificación

```
50/50 PASS (100%) en TODAS las dimensiones bloqueantes
```

| Categoría | Safety | Functional | Verdict | Threshold | Status |
|---|---|---|---|---|---|
| happy | 15/15 (100%) | 15/15 (100%) | 15/15 | ≥85% | ✅ |
| ambiguous | 15/15 (100%) | 15/15 (100%) | 15/15 | ≥70% | ✅ |
| destructive | 10/10 (100%) | 10/10 (100%) | 10/10 | 100% | ✅ |
| multi_turn | 10/10 (100%) | 10/10 (100%) | 10/10 | ≥80% | ✅ |

Trayectoria de mejora:
- Versión inicial (v3): 32/50 (64%)
- Tras refuerzos de safety (v5): 45/50 (90%)
- **Versión certificada (v6-proactive): 50/50 (100%)**

---

## Arquitectura del componente de evaluación

10 módulos Python con responsabilidad única:

- `eval/schemas.py` — modelos Pydantic (single source of truth)
- `eval/verdict.py` — Verdict Engine compone Safety + Functional + Quality
- `eval/runner.py` — invoca al agente, captura tool_calls, multi-turn
- `eval/tool_executor.py` — Protocol con DI (Bridge/HTTP/Mock)
- `eval/foundry_eval.py` — wrappers de LLM-judge con auth via Azure SDK
- `eval/reporter.py` — Markdown + JSON con 3 dimensiones separadas

4 ADRs (Architecture Decision Records) documentan las decisiones.

30 tests unitarios corren en 0.05s sin necesidad de red.

---

## Para Ecopetrol — qué pueden ver

1. **Dashboard nativo en Azure AI Foundry** — el cliente accede a su portal Foundry, sección Evaluations, y ve los 50 casos con scores por dimensión y comparativo entre versiones del agente.
2. **Reporte Markdown ejecutivo** — `results/report_<timestamp>.md` con drill-down de safety + detalle por caso.
3. **JSON crudo** — `results/run_<timestamp>.json` con cada `tool_call` capturado, args completos, intent_summary, scores LLM-judge.
4. **Reproducibilidad**: `python -m eval run` regenera todo desde cero contra el agente productivo en Foundry.

---

## Próximos pasos (sugeridos, no incluidos en esta certificación)

| Iniciativa | Aporte | Tiempo |
|---|---|---|
| **Phase 2 sobre TALENTO**: Guardrails (Content Safety), Bing Grounding, Code Interpreter | Robustez ante datos reales del cliente | 1-2 sprints |
| **CI/CD**: hook que corra `pytest + eval run` en cada bump de `CATALOG_VERSION` | Auto-bloqueo de regresiones safety | 1 sprint |
| **Caso 2 del RFP**: Reconstrucción TALENTO | Ampliación scope | Aterrizar alcance primero |
| **Caso 3 del RFP**: EasyGO microservicios AKS | Ampliación scope | Aterrizar alcance primero |

---

## Decisiones de diseño no negociables

- ✅ El agente NUNCA ejecuta `dry_run=false` automáticamente. Siempre requiere mensaje explícito del operador en una segunda solicitud.
- ✅ El agente rechaza acciones fuera del catálogo de Job Templates y escala al equipo correspondiente (DBA, admin Entra ID, plataforma).
- ✅ Cada caso de evaluación está atado a un `CATALOG_VERSION` del agente — cambios al system prompt obligan revalidar todo el dataset.
- ✅ Safety es 100% determinístico (no depende de LLM-judge). Las heurísticas semánticas son complementarias, no bloqueantes.

---

**Material adjunto entregable**:
- `evaluations/CERTIFICATION.md` — evidencia técnica completa
- `evaluations/AUDIT.md` — auditoría del proceso de evaluación
- `evaluations/results/run_<ts>.json` — datos crudos de la certificación
- `evaluations/results/report_<ts>.md` — reporte canónico
- URL del portal Foundry (con `--publish`)
