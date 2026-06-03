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

- Para verificar estado actual de infraestructura (container Running/Stopped, App Service availability) → usar `run_awx_job_template` con los JTs de diagnóstico (36-39).
- Para ejecutar acciones (restart, etc.) → usar `run_awx_job_template` con los JTs de remediación (40-43).
- Para definiciones de códigos TLNT-XXX → buscar en `talento_error_catalog.md` del knowledge base.

---

## Patrón 11 — Actividad por usuario específico (NUEVO)

> ⚠️ **BLOQUEADO — Hallazgo 2 abierto**. Este patrón **NO funciona** con los logs
> actuales porque el JSON estructurado no contiene campo `usuario` (verificado
> sobre 30,523 eventos JSON en 168h). Documentado aquí como referencia para
> cuando EAPPS instrumente el MDC. **No lo uses hasta entonces.** Para
> investigación forense actual, usa correlation_id (patrón 3).

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.usuario) == 'nvivas'   // FUTURO: cuando MDC esté instrumentado
| project
    TimeGenerated,
    level = tostring(p.level),
    codigo_error = tostring(p.codigo_error),
    msg = tostring(p.message),
    corr_id = tostring(p.correlation_id),
    logger = tostring(p.logger_name)
| order by TimeGenerated desc
| take 50
```

---

## Patrón 12 — Detección de brute force por usuario (BLOQUEADO)

> ⚠️ **BLOQUEADO — Hallazgo 2**. Mismo bloqueo que patrón 11: requiere campo
> `usuario` que no existe. Alternativa actual: ver el **VOLUMEN** agregado de
> TLNT-002/008/011 con patrón 4 (sin agrupar por usuario). Si el volumen tiene
> pico, escalar a investigación manual cruzando correlation_id con Azure AD.

Conteo de fallos de autenticación agrupados por usuario en una ventana. Los
códigos relevantes son TLNT-002 (credenciales inválidas), TLNT-008 (password
incorrecta) y TLNT-011 (intentos excedidos):

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(1h)
| extend p = parse_json(Message)
| where tostring(p.codigo_error) in ('TLNT-002', 'TLNT-008', 'TLNT-011')
| extend usuario = tostring(p.usuario)
| where isnotempty(usuario)
| summarize
    fails = count(),
    primer = min(TimeGenerated),
    ultimo = max(TimeGenerated),
    codes = make_set(tostring(p.codigo_error))
    by usuario
| where fails >= 5
| order by fails desc
```

Si `fails >= 5` por un usuario en ventana corta → posible brute force.

---

## Patrón 13 — Auditoría SOX por usuario (BLOQUEADO)

> ⚠️ **BLOQUEADO — Hallazgo 2**. Idéntica situación: sin campo `usuario`, no
> hay agrupación posible. Mantener este patrón aquí como referencia para
> cuando se cierre el Hallazgo.

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

## Patrón 14 — Top usuarios por errores en ventana (BLOQUEADO)

> ⚠️ **BLOQUEADO — Hallazgo 2**. Mismo motivo. Alternativa actual: top códigos
> con patrón 4 (agrupado por código en lugar de por usuario).

```kql
ContainerInstanceLog_CL
| where TimeGenerated > ago(24h)
| extend p = parse_json(Message)
| where tostring(p.level) == "ERROR" or tostring(p.level) == "WARN"
| where isnotempty(tostring(p.usuario))
| summarize
    total_errores = count(),
    distinct_codes = dcount(tostring(p.codigo_error)),
    top_codes = make_set(tostring(p.codigo_error), 5)
    by usuario = tostring(p.usuario)
| order by total_errores desc
| take 10
```
