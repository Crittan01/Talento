# Evaluations — TALENTO Triage Agent

Pipeline arquitectónico de evaluación del agente `talento-triage-agent` (Azure AI Foundry).

Tres dimensiones medidas por separado, cada una con su responsabilidad:

| Dimensión | Bloqueante | Fuente | Threshold |
|---|---|---|---|
| **Safety** | ✅ Sí | Inspección determinística de `tool_calls.args` | 100% en safety-critical |
| **Functional** | ✅ Sí | `tools_any_of/all_of`, `template_id`, args | 85% / 70% / 100% / 80% por categoría |
| **Quality** | ❌ No (informativo) | LLM-judge (IntentResolution, ToolCallAccuracy, TaskAdherence) | scores 1-5 |

Decisiones de diseño documentadas en [`adr/`](adr/). Ver [AUDIT.md](AUDIT.md) para la justificación de la arquitectura.

---

## Estructura

```
evaluations/
├── adr/                          # Architecture Decision Records
│   ├── 001-three-tier-verdict.md
│   ├── 002-foundry-judge-api-key.md
│   ├── 003-pydantic-schemas.md
│   └── 004-tool-executor-injection.md
│
├── eval/                         # Paquete principal
│   ├── __main__.py               # CLI (python -m eval run)
│   ├── config.py                 # AppConfig — single source of truth
│   ├── schemas.py                # Pydantic: CaseDefinition, RunResult, Verdict
│   ├── secrets.py                # SecretsResolver via Azure SDK (no subprocess)
│   ├── runner.py                 # AgentRunner — invoca Foundry
│   ├── response_parser.py        # parsea response.output del Responses API
│   ├── tool_executor.py          # ToolExecutor Protocol + Bridge/Mock impls
│   ├── verdict.py                # VerdictEngine + 3 categorías
│   ├── foundry_eval.py           # LLM-judge wrappers (api_key auth)
│   └── reporter.py               # Markdown + JSON
│
├── dataset/                      # Dataset versionado
│   ├── builder.py                # CLI: python -m dataset.builder
│   ├── golden_dataset.jsonl      # output (regenerable)
│   └── cases/                    # 50 casos en Python tipado
│       ├── happy.py              # 15
│       ├── ambiguous.py          # 15
│       ├── destructive.py        # 10
│       └── multi_turn.py         # 10
│
├── tests/                        # Unit tests del pipeline (sin red)
│   ├── conftest.py
│   ├── test_safety_assertions.py     # 8 tests
│   ├── test_functional_assertions.py # 8 tests
│   ├── test_verdict_engine.py        # 6 tests
│   └── test_response_parser.py       # 8 tests
│
├── results/                      # outputs por run
├── pytest.ini
├── AUDIT.md                      # Auditoría del pipeline previo
└── README.md                     # este archivo
```

---

## Uso

### 1. Build del dataset desde cases tipados

```bash
cd function-app/evaluations
python3 -m dataset.builder
```

Salida:
```
✓ 50 casos serializados a .../dataset/golden_dataset.jsonl
  Distribucion: {'happy': 15, 'ambiguous': 15, 'destructive': 10, 'multi_turn': 10}
  Safety critical: 14
```

### 2. Unit tests (sin red, < 1s)

```bash
python3 -m pytest tests/ -v
```

30 tests del pipeline (Safety + Functional + Verdict Engine + Response Parser).

### 3. Smoke con casos seleccionados (sin LLM-judge)

```bash
python3 -m eval run --case-ids H01,D04,D10,M05 --no-quality
```

### 4. Eval completa con LLM-judge

```bash
python3 -m eval run
```

50 casos × ~15s/caso (~25-40 min con LLM-judge). Costo aproximado: < $2 USD en tokens.

### Outputs

- `results/run_<ts>.json` — payload completo con `verdict.model_dump()` por caso
- `results/report_<ts>.md` — reporte ejecutivo con 3 dimensiones separadas, drill-down de safety, detalle por caso

---

## Permisos requeridos

La identidad del usuario (`az login`) debe tener:

- `Cognitive Services User` sobre el recurso `aifoundry-is2` (para `list_keys`)
- `Website Contributor` sobre `fa-solucion-talento` (para `list_application_settings`)

Si los permisos faltan, `SecretsResolver` falla con error explícito.

---

## Decisiones arquitectónicas (resumen)

### ADR-001: Tres categorías de veredicto

El veredicto PASS/FAIL compone Safety + Functional. Quality (LLM-judge) es informativo y no bloquea. Esto separa criterios determinísticos (auditables, SOX-amigables) de criterios semánticos (sujetos a variabilidad LLM).

### ADR-002: Foundry LLM-judge con `api_key` resuelto por Azure SDK

El SDK `azure-ai-evaluation` con `azure_ad_token_provider` da 401 en `AsyncAzureOpenAI`. Se resuelve obteniendo el `api_key` via `CognitiveServicesManagementClient` — sin `subprocess` ni hardcoded values.

### ADR-003: Pydantic schemas con validación en build-time

Reemplazan el JSON manual sin tipo. `CaseDefinition`, `ExpectedBehavior`, `Verdict`, `RunResult` son single source of truth con validadores explícitos (`query xor turns`, prefix coincide con category, etc).

### ADR-004: ToolExecutor con inyección de dependencias

`AgentRunner` recibe un `ToolExecutor` (`Protocol`) en lugar de llamar directo a `bridge_l2`. Permite mockear en tests, intercambiar implementación a futuro (HTTP via Function App), y desacoplar la configuración del bridge.

---

## Cómo agregar un nuevo caso

1. Editar el archivo de la categoría correspondiente en `dataset/cases/`.
2. Crear instancia de `CaseDefinition` — Pydantic valida en build.
3. Regenerar: `python3 -m dataset.builder`.
4. Verificar con tests + smoke: `python3 -m pytest tests/ && python3 -m eval run --case-ids <NEW_ID> --no-quality`.

---

## Cómo agregar una nueva aserción

1. Si es **Safety**: añadir check en `eval/verdict.py:SafetyAssertion.evaluate`. Test correspondiente en `tests/test_safety_assertions.py`.
2. Si es **Functional**: análogo en `FunctionalAssertion`.
3. Si es **Quality**: depende del LLM-judge — agregar un nuevo evaluator en `eval/foundry_eval.py`.

---

## Out of scope

- Migración al wizard de Foundry portal (Modo B del AUDIT)
- CI/CD pipelines (`pytest` + `eval run` en cada push)
- Custom evaluators (LLM-judge personalizado)
- Azure Key Vault para secretos
