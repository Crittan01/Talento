# Guía de Patrones KQL para Logs TALENTO

Este documento contiene patrones KQL probados para consultar los logs de TALENTO
en Log Analytics. El agente debe consultar esta guía vía `file_search` antes de
formular cualquier query.

## Schema de los logs TALENTO

La aplicación TALENTO emite logs JSON estructurados en `stdout`, que llegan a la
tabla `ContainerInstanceLog_CL`. Cada log tiene los siguientes campos dentro del
campo `Message` (string que es JSON parseable):

### Esquema REAL del JSON (validado por inspección directa del workspace en 168h)

```json
{
  "@timestamp":     "2026-06-03T17:59:44.609505202Z",
  "@version":       "1",
  "message":        "Eliminando registro de día cumpleaños con id 522",
  "logger_name":    "com.nttdata.ecopetrol.talento.controller.TalentoController",
  "thread_name":    "http-nio-8080-exec-26",
  "level":          "INFO|WARN|ERROR",
  "level_value":    20000,
  "correlation_id": "bce53a8b-6e33-4c84-8631-832315e7e8cb",
  "codigo_error":   "TLNT-008",          // campo dedicado, EN ESPAÑOL, 22.7% cobertura
  "modulo":         "talento"
}
```

### Campos top-level disponibles (cobertura medida en 30,523 eventos JSON / 168h)

| Campo | Cobertura | Cómo accederlo |
|---|---|---|
| `@timestamp`, `@version`, `level`, `level_value`, `message`, `modulo`, `logger_name`, `thread_name` | 100% | `tostring(p.<campo>)` |
| `correlation_id` | 99.5% | `tostring(p.correlation_id)` |
| `codigo_error` | 22.7% (6,943 filas) | `tostring(p.codigo_error)` |
| `tags` | 3.7% | `tostring(p.tags)` |

**IMPORTANTE — nombre del campo de código de error**: el campo es `codigo_error`
(en ESPAÑOL), NO `error_code` (inglés). EAPPS lo describió mal inicialmente.

**Nota histórica (compatibilidad)**: en logs viejos el código TLNT-XXX puede venir
embebido en el campo `message` en lugar de en `codigo_error`. Para máxima compatibilidad,
extraer con `coalesce(tostring(p.codigo_error), extract("(TLNT-[0-9]+)", 1, Message))`.

### **BLOQUEO conocido — campo de identidad de usuario**

El JSON estructurado **NO contiene** ningún campo de identidad (`usuario`, `user`,
`userName`, `principalName`, etc). EAPPS confirmó un campo `usuario` que en realidad
no existe en los logs emitidos. **Hallazgo 2 abierto**: instrumentar el logger Logback
para añadir el principal autenticado al MDC, de modo que aparezca como key top-level
del JSON. Hasta entonces, **cualquier query KQL que filtre por usuario devolverá 0 filas**.
Alternativa actual: cruzar `correlation_id` contra Azure AD signin logs o el API gateway
para resolver identidad manualmente.

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
agrupa por frecuencia. Usa el campo `error_code` dedicado cuando está poblado;
fallback a regex sobre `Message` para logs viejos:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| extend codigo = coalesce(tostring(p.codigo_error), extract("(TLNT-\\d+)", 1, Message))
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

- Estado de infraestructura (container, App Service, Storage, Network, Quotas) → `lookup_infrastructure(mode=...)`.
- Estado de SQL Servers y databases → `lookup_sql()`.
- Detección de anomalías estadísticas → `detect_anomalies(metric_type, ...)`.
- Actividad reciente (<3h): SOX, brute force → `lookup_runtime_logs(modo, ...)`.
- Trazabilidad por correlation_id → `lookup_correlation_id(correlation_id, ...)`.
- Análisis de códigos TLNT → `tlnt_explorer(codigo, ...)`.
- Performance y dependencias → `lookup_app_insights(modo, ...)`.
- Remediación invasiva → `run_awx_job_template(template_id, ...)`.
- Definiciones de códigos TLNT-XXX → `file_search` en `talento_error_catalog.md`.

`query_log_analytics` es el **escape hatch** para consultas que ninguna tool especializada cubre.

---

## Nota — Queries por usuario (bloqueadas — Hallazgo EAPPS abierto)

El JSON estructurado de TALENTO **NO contiene** campo de identidad de usuario
(`usuario`, `user`, `userName`, etc.). Verificado en 30,523 eventos / 168h.

**Alternativas actuales:**
- Actividad reciente por usuario → `lookup_runtime_logs(modo='user_audit', usuario='nvivas')` (buffer ACI ~3h)
- Actividad histórica → `user_activity(usuario='nvivas', time_range_hours=24)` (extrae usuario del campo `message` con regex)
- Brute force → `lookup_runtime_logs(modo='brute_force')` (agrupación por `usuario` en el buffer runtime)

Cuando EAPPS instrumente el MDC de Logback, el campo `usuario` aparecerá en el JSON
y estas queries KQL serán viables. Hasta entonces, NO escribir KQL que filtre por `usuario`.

---

## Patrones de Detección de Anomalías (v21)

> **NOTA v21**: El agente NO debe escribir estas queries manualmente.
> Usar la tool `detect_anomalies(metric_type, time_range_hours, bin_minutes)`.
> El bridge construye y ejecuta la KQL automáticamente.
> Estos patrones están aquí como referencia de lo que hace la tool internamente.

### Patrón 15 — Anomalía en tasa de errores (error_rate)

`detect_anomalies(metric_type='error_rate', time_range_hours=24, bin_minutes=10)`

```kql
ContainerInstanceLog_CL
| where TimeGenerated >= ago(24h)
| extend p = parse_json(Message)
| where tostring(p.level) == 'ERROR'
| make-series err_count=count() on TimeGenerated from ago(24h) to now() step 10m
| extend (anomalies, scores, baseline) = series_decompose_anomalies(err_count, 1.5)
| mv-expand TimeGenerated, err_count, anomalies, scores
| where toint(anomalies) != 0
| extend direction = iff(toint(anomalies) > 0, 'SPIKE', 'DIP')
| project TimeGenerated, err_count=toint(err_count), anomaly_score=round(todouble(scores),1), direction
```

**SPIKE** = pico anormal de errores. **DIP** = caída anormal (posible pérdida de tráfico).
Requiere ≥10 bins de datos (ventana mínima ~4h con bins de 10m).

---

### Patrón 16 — Anomalía en volumen de requests (request_volume)

`detect_anomalies(metric_type='request_volume', time_range_hours=24, bin_minutes=10)`

Fuente: tabla `AppRequests` en workspace 2 (`14135f7a-c66a-492c-8c8b-124cdea16c2d`).

```kql
AppRequests
| where TimeGenerated >= ago(24h)
| make-series req_count=count() on TimeGenerated from ago(24h) to now() step 10m
| extend (anomalies, scores, baseline) = series_decompose_anomalies(req_count, 1.5)
| mv-expand TimeGenerated, req_count, anomalies, scores
| where toint(anomalies) != 0
| extend direction = iff(toint(anomalies) > 0, 'SPIKE', 'DIP')
```

---

### Patrón 17 — Anomalía en fallos de autenticación (auth_failures)

`detect_anomalies(metric_type='auth_failures', time_range_hours=24, bin_minutes=10)`

```kql
ContainerInstanceLog_CL
| where TimeGenerated >= ago(24h)
| extend p = parse_json(Message)
| extend codigo = coalesce(tostring(p.codigo_error), extract('(TLNT-[0-9]+)', 1, Message))
| where codigo in ('TLNT-002', 'TLNT-008', 'TLNT-009', 'TLNT-011')
| make-series fail_count=count() on TimeGenerated from ago(24h) to now() step 10m
| extend (anomalies, scores, baseline) = series_decompose_anomalies(fail_count, 1.5)
| mv-expand TimeGenerated, fail_count, anomalies, scores
| where toint(anomalies) != 0
| extend direction = iff(toint(anomalies) > 0, 'SPIKE', 'DIP')
```

Un SPIKE en auth_failures con alta frecuencia → correlacionar con `lookup_runtime_logs(modo='brute_force')`.

---

### Patrón 18 — SQL Diagnostic Queries (cuando Diagnostic Settings activos)

> Solo disponibles cuando SQL Server tiene Diagnostic Settings apuntando a Log Analytics.
> La tool `lookup_sql()` los ejecuta automáticamente si hay datos.

```kql
// Slow queries (>1s, últimas 24h)
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where Category == 'QueryStoreRuntimeStatistics'
| extend duration_ms = todouble(max_duration_d) / 1000
| where duration_ms > 1000
| project TimeGenerated, database_s, query_hash_s, duration_ms, execution_count_d
| order by duration_ms desc | take 10

// Bloqueos
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where Category == 'Blocks'
| summarize count() by database_s, bin(TimeGenerated, 1h)

// Deadlocks
AzureDiagnostics
| where TimeGenerated >= ago(24h)
| where Category == 'Deadlocks'
| summarize count() by database_s
```
```
