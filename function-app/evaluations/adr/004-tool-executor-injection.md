# ADR-004: ToolExecutor con inyección de dependencias

## Status
Aceptado — 2026-06-02

## Context

El runner inicial llamaba directamente a `bridge_l2.execute_kql()` y `bridge_l2.run_awx_job_template()` desde dentro de `run_agent_for_case()`. Eso significaba:

- **Tests no son posibles sin red**: cualquier test que recorra el runner termina pegándole a Log Analytics + AWX productivos.
- **El `bridge_l2` está acoplado**: si quisiera testear el AgentRunner aislado, tendría que monkey-patch los módulos.
- **No hay forma de cambiar la implementación**: si en el futuro quiero invocar vía `/api/run` HTTP (para testear el wrapper Function App), el path sería un fork del runner.
- **Auth y configuración están mezcladas**: el bridge lee `os.environ["AWX_TOKEN"]` y `os.environ["AWX_URL"]` ad-hoc. Para override (ej. token productivo vs local) hay que tocar env globalmente.

## Decision

Introducir un `ToolExecutor` como **Protocol** (interfaz tipada) que el `AgentRunner` recibe por constructor. Dos implementaciones:

```python
from typing import Protocol

class ToolExecutor(Protocol):
    def execute_kql(self, query: str) -> dict: ...
    def execute_awx(self, template_id: int, extra_vars: dict) -> dict: ...
```

1. **`BridgeToolExecutor`** (producción): delega a `bridge_l2` pero con la configuración inyectada via `AppConfig` y los secretos via `SecretsResolver`. NO usa `os.environ` ad-hoc — el bridge sigue leyendo env, pero el ejecutor se asegura que las vars correctas están seteadas antes de delegar.

2. **`MockToolExecutor`** (tests): respuestas hardcodeadas o configurables. No tiene I/O.

Una posible tercera implementación futura `HttpToolExecutor` invocaría `/api/run` del Function App para testing E2E del wrapper completo.

## Consequences

**Pros:**
- Tests del runner pueden simular cualquier escenario (KQL devuelve N filas, AWX devuelve 401, AWX devuelve 200, tool no soportado, etc).
- El `AgentRunner` no tiene acoplamiento con `bridge_l2`. Puede co-evolucionar el dataset/runner sin tocar el bridge.
- La configuración (`AWX_URL`, secrets) entra por inyección, no por env globales. Permite correr múltiples evals en paralelo con configs distintas (futuro).
- Smoke contra Function App E2E es un nuevo `HttpToolExecutor`, no un fork del runner.

**Contras:**
- Una indirección más en runtime. Despreciable comparado con el costo del LLM (10ms vs 5s).
- `bridge_l2` no fue diseñado para que sus tools se llamen aislados (lee env globales). El `BridgeToolExecutor` actúa como adapter — setea env si falta, delega, no muta env permanentemente.

## Estructura en código

```
eval/
├── tool_executor.py
│   ├── class ToolExecutor(Protocol):    # interfaz
│   ├── class BridgeToolExecutor:        # producción (delega a bridge_l2)
│   └── class MockToolExecutor:          # tests
└── runner.py
    └── class AgentRunner:
            def __init__(self, project, config, executor: ToolExecutor): ...
```

## Alternatives considered

- **Monkey-patch `bridge_l2` en tests con `unittest.mock`**: posible pero frágil — los tests dependen de la estructura interna del bridge.
- **Hacer a `bridge_l2` mismo aceptar inyección**: refactor del bridge fuera del scope de este plan. Lo evitamos.
- **Pasar funciones (callbacks) en lugar de Protocol**: menos tipado, menos discoverable. Protocol da mejor signal en IDE.

## References

- [PEP 544 — Protocols](https://peps.python.org/pep-0544/).
- AUDIT.md: sección 4 "Auditoría del código del runner".
