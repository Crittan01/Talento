# Guía de Patrones KQL para Logs TALENTO

Este documento contiene patrones KQL probados para consultar los logs de TALENTO
en Log Analytics. El agente debe consultar esta guía vía `file_search` antes de
formular cualquier query.

## Schema de los logs TALENTO

La aplicación TALENTO emite logs JSON estructurados en `stdout`, que llegan a la
tabla `ContainerInstanceLog_CL`. Cada log tiene los siguientes campos dentro del
campo `Message` (string que es JSON parseable):

```json
{
  "@timestamp":     "2026-06-02T16:55:37.038727083Z",
  "@version":       "1",
  "message":        "[CierreMes] Simulando delay de 6 segundos...",
  "logger_name":    "com.nttdata.ecopetrol.talento.controller.TalentoController",
  "thread_name":    "http-nio-8080-exec-6",
  "level":          "INFO|WARN|ERROR",
  "level_value":    20000,
  "correlation_id": "8f660c47-e4dd-4e14-8bae-797916b00fda",
  "modulo":         "talento"
}
```

Cuando ocurre un error catalogado, el campo `message` contiene el código TLNT-XXX
embebido (ej. `"ERROR [TLNT-001] Usuario 78001 no encontrado"`).

---

## Patrón 1 — Parsing base del JSON

Siempre el primer paso para queries sobre el contenido. Hace `parse_json(Message)`
y extiende los campos a columnas usables.

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| project
    TimeGenerated,
    level = tostring(p.level),
    corr_id = tostring(p.correlation_id),
    logger = tostring(p.logger_name),
    msg = tostring(p.message),
    modulo = tostring(p.modulo)
```

---

## Patrón 2 — Filtrar por nivel (ERROR/WARN/INFO)

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.level) == "ERROR"
| project TimeGenerated, msg = tostring(p.message), corr_id = tostring(p.correlation_id)
| order by TimeGenerated desc
| take 50
```

Variantes:
- `WARN`: cambiar `"ERROR"` por `"WARN"`
- Multiples niveles: `where tostring(p.level) in ("ERROR", "WARN")`

---

## Patrón 3 — Reconstruir trazabilidad por correlation_id

Cuando se reporta un caso específico (ej. "usuario X tuvo problema a las 10:32"),
y se conoce el `correlation_id`, este patrón devuelve todos los logs de esa
petición en orden cronológico:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(2h)
| extend p = parse_json(Message)
| where tostring(p.correlation_id) == "8f660c47-e4dd-4e14-8bae-797916b00fda"
| project TimeGenerated, level = tostring(p.level), msg = tostring(p.message), logger = tostring(p.logger_name)
| order by TimeGenerated asc
```

---

## Patrón 4 — Detectar y contar códigos TLNT-XXX

Identifica todos los códigos del catálogo que aparecieron en una ventana y los
agrupa por frecuencia:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend codigo = extract("(TLNT-\\d+)", 1, Message)
| where isnotempty(codigo)
| summarize Count = count() by codigo
| order by Count desc
```

---

## Patrón 5 — Buscar errores específicos por código

Para investigar instancias de un código específico (ej. TLNT-014):

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| where Message contains "TLNT-014"
| extend p = parse_json(Message)
| project TimeGenerated, msg = tostring(p.message), corr_id = tostring(p.correlation_id)
| order by TimeGenerated desc
```

---

## Patrón 6 — Spike detection (alerta operacional)

Detectar si hay aumento súbito de ERRORS en últimos 5 minutos:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(15m)
| extend p = parse_json(Message)
| where tostring(p.level) == "ERROR"
| summarize errors_count = count() by bin(TimeGenerated, 1m)
| order by TimeGenerated desc
```

Si `errors_count > 5` en cualquier minuto reciente, es señal de incidente activo.

---

## Patrón 7 — Top errores agrupados por mensaje

Útil para identificar qué errores son más frecuentes:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.level) == "ERROR"
| extend msg_short = substring(tostring(p.message), 0, 80)
| summarize Count = count(), corr_ids = make_set(tostring(p.correlation_id), 5) by msg_short
| order by Count desc
| take 10
```

---

## Patrón 8 — Filtrar por logger/módulo

Cuando se quiere aislar logs de un controller o servicio específico:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| where tostring(p.logger_name) endswith "TalentoController"
| project TimeGenerated, level = tostring(p.level), msg = tostring(p.message)
| order by TimeGenerated desc
| take 50
```

---

## Patrón 9 — Logs de auditoría (acciones privilegiadas)

Para casos SOX. Identifica acciones críticas como aprobaciones, login con rol
elevado, modificaciones masivas:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| where Message has_any ("aprob", "LIDER", "DELETE", "UPDATE", "rol_admin")
| extend p = parse_json(Message)
| project TimeGenerated, level = tostring(p.level), msg = tostring(p.message), corr_id = tostring(p.correlation_id)
| order by TimeGenerated desc
```

---

## Patrón 10 — Health check rápido

Conteo de logs en última hora por nivel para ver pulso general:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| summarize Count = count() by level = tostring(p.level)
| order by Count desc
```

Resultado esperado en operación normal: INFO >> WARN >> ERROR (ratio aprox 75/20/5).

---

## Buenas prácticas

1. **Siempre usar `parse_json` antes de filtrar por campo** — extraer una vez, reusar.
2. **Limitar ventana temporal** (`ago(1h)`, `ago(24h)`) — evita queries costosas.
3. **Usar `tostring()` al extraer campos del JSON** — los tipos pueden ser ambiguos.
4. **No olvidar `take` u `order by ... | take N`** — KQL devuelve hasta 500K rows por default.
5. **El campo `correlation_id` es la pieza más valiosa** — permite reconstruir flujos completos.

## Cuándo NO usar query_log_analytics

- Para verificar estado actual de infraestructura (container Running/Stopped, App Service availability) → usar `run_awx_job_template` con los JTs de diagnóstico (36-39).
- Para ejecutar acciones (restart, etc.) → usar `run_awx_job_template` con los JTs de remediación (40-43).
- Para definiciones de códigos TLNT-XXX → buscar en `talento_error_catalog.md` del knowledge base.
