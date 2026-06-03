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
  "@timestamp":     "2026-06-03T17:59:44.609505202Z",
  "@version":       "1",
  "message":        "Login fallido: contraseña incorrecta para usuario 'nvivas'",
  "logger_name":    "com.nttdata.ecopetrol.talento.services.impl.LoginServiceImpl",
  "thread_name":    "http-nio-8080-exec-3",
  "level":          "INFO|WARN|ERROR",
  "level_value":    20000,
  "correlation_id": "bce53a8b-6e33-4c84-8631-832315e7e8cb",
  "usuario":        "nvivas",            // campo dedicado cuando el evento tiene contexto de usuario
  "error_code":     "TLNT-008",          // campo dedicado cuando el evento es un error catalogado
  "modulo":         "talento"
}
```

### Campos clave para parsing

| Campo | Cuando aparece | Cómo accederlo |
|---|---|---|
| `usuario` | Eventos con contexto de usuario (login, listing, aprobaciones, errores con usuario asociado) | `tostring(p.usuario)` |
| `error_code` | Logs con un error catalogado del catálogo TLNT-XXX | `tostring(p.error_code)` |
| `correlation_id` | TODOS los logs de petición HTTP (~99.5% cobertura) | `tostring(p.correlation_id)` |
| `logger_name` | TODOS los logs | `tostring(p.logger_name)` |
| `level` | TODOS los logs | `tostring(p.level)` |

**Nota histórica (compatibilidad)**: en logs viejos el código TLNT-XXX puede venir
embebido en el campo `message` en lugar de en `error_code`. Para máxima compatibilidad,
extraer con `coalesce(tostring(p.error_code), extract("(TLNT-[0-9]+)", 1, Message))`.

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
| extend codigo = coalesce(tostring(p.error_code), extract("(TLNT-\\d+)", 1, Message))
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

---

## Patrón 11 — Actividad por usuario específico (NUEVO)

Cuando el operador pregunta por la actividad de un usuario concreto. Usa el
campo `usuario` dedicado del JSON (poblado en eventos de login, listing,
errores con contexto de usuario):

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.usuario) == 'nvivas'
| project
    TimeGenerated,
    level = tostring(p.level),
    error_code = tostring(p.error_code),
    msg = tostring(p.message),
    corr_id = tostring(p.correlation_id),
    logger = tostring(p.logger_name)
| order by TimeGenerated desc
| take 50
```

Útil para auditoría SOX por usuario y para investigar quejas individuales.

---

## Patrón 12 — Detección de brute force por usuario (NUEVO)

Conteo de fallos de autenticación agrupados por usuario en una ventana. Los
códigos relevantes son TLNT-002 (credenciales inválidas), TLNT-008 (password
incorrecta) y TLNT-011 (intentos excedidos):

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| where tostring(p.error_code) in ('TLNT-002', 'TLNT-008', 'TLNT-011')
| extend usuario = tostring(p.usuario)
| where isnotempty(usuario)
| summarize
    fails = count(),
    primer = min(TimeGenerated),
    ultimo = max(TimeGenerated),
    codes = make_set(tostring(p.error_code))
    by usuario
| where fails >= 5
| order by fails desc
```

Si `fails >= 5` por un usuario en ventana corta → posible brute force.

---

## Patrón 13 — Auditoría SOX por usuario (NUEVO)

Acciones críticas auditables agrupadas por usuario. Útil para certificación
SOX y compliance:

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where isnotempty(tostring(p.usuario))
| extend usuario = tostring(p.usuario), msg = tostring(p.message)
| extend tipo_accion = case(
    msg has_cs "Login exitoso", "login_ok",
    msg has_cs "Login fallido", "login_fail",
    msg has_cs "Listando", "listing",
    msg has_cs "Aprob", "aprobacion",
    msg has_cs "Modific" or msg has_cs "Actualiz", "modificacion",
    "otro"
)
| summarize total = count() by usuario, tipo_accion
| order by usuario asc, tipo_accion asc
```

---

## Patrón 14 — Top usuarios por errores en ventana (NUEVO)

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.level) == "ERROR" or tostring(p.level) == "WARN"
| where isnotempty(tostring(p.usuario))
| summarize
    total_errores = count(),
    distinct_codes = dcount(tostring(p.error_code)),
    top_codes = make_set(tostring(p.error_code), 5)
    by usuario = tostring(p.usuario)
| order by total_errores desc
| take 10
```
