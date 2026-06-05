# Runbook Operacional TALENTO (v21)

Procedimientos paso a paso para escenarios típicos. Consultar vía `file_search`
con palabras clave del escenario.

**v21 — routing de tools**:
- Estado infra (ACI, App Service, Storage, Network, Quotas) → `lookup_infrastructure`
- Estado SQL / databases → `lookup_sql`
- Anomalías estadísticas → `detect_anomalies`
- Actividad reciente (<3h): SOX, brute force → `lookup_runtime_logs`
- Histórico (>3h): usuario, correlación, TLNT → `user_activity` / `tlnt_explorer` / `lookup_correlation_id`
- Remediación invasiva (restart/stop/start) → `run_awx_job_template` (4 JTs)

---

## Escenario 1 — Spike de errores

**Síntoma**: alerta por tasa de ERROR elevada / operador reporta fallos en TALENTO.

**Pasos**:

1. Ejecutar `detect_anomalies(metric_type='error_rate', time_range_hours=24)`
   para confirmar el spike y ver cuándo comenzó.

2. Ejecutar `tlnt_explorer(codigo='', time_range_hours=6)` para ver los códigos
   de error más frecuentes en la ventana.

3. Para cada código TLNT-XXX top, consultar `file_search` con el código
   para citar su definición y acción sugerida.

4. Si el spike coincide con spikes de `auth_failures` → ejecutar
   `detect_anomalies(metric_type='auth_failures', ...)` para correlación.

5. Sintetizar: cantidad de errores, ventana, top códigos TLNT con definición,
   y siguiente paso sugerido.

**NO ejecutar** acción de remediación automáticamente.

---

## Escenario 2 — Container TALENTO en BackOff o CrashLoop

**Síntoma**: alerta de restartCount alto, o el operador reporta "TALENTO no responde".

**Pasos**:

1. Ejecutar `lookup_infrastructure(mode='aci')` para obtener:
   - `state` actual (Running/Terminated/Pending)
   - `restart_count`
   - `last_event_type` y `last_event_message`

2. Ejecutar `query_log_analytics` para ver últimos logs antes del crash:
   ```kql
   ContainerInstanceLog_CL
   | where TimeGenerated > ago(30m)
   | extend p = parse_json(Message)
   | where tostring(p.level) in ("ERROR", "WARN")
   | project TimeGenerated, msg = tostring(p.message)
   | order by TimeGenerated desc | take 20
   ```

3. Si los logs muestran OOM (OutOfMemoryError) → recomendar resize del container
   (manual, no automatizado por el agente).

4. Si los logs muestran error de conexión a BD:
   → ejecutar `lookup_sql()` para confirmar estado de SQL antes de restart.

5. Si los logs muestran error transitorio o no hay causa clara:
   → proponer restart con `run_awx_job_template` JT aci-restart en `dry_run=true`.
   Mostrar qué pasaría. Pedir confirmación EXPLÍCITA del operador.

6. NUNCA ejecutar restart automático sin confirmación humana.

**Output esperado**: diagnóstico + propuesta en dry-run + pregunta de confirmación.

---

## Escenario 3 — Cierre de nómina lento (degradación de performance)

**Síntoma**: usuarios reportan lentitud durante cierre mensual.

**Pasos**:

1. Ejecutar `lookup_sql()` para ver tier y estado de la BD.
   Si tier es S2 y la fecha es cerca al cierre mensual → probable saturación de DTUs.

2. Ejecutar `lookup_app_insights(modo='latency_p95', ...)` para ver endpoints lentos.

3. Ejecutar `lookup_app_insights(modo='slow_deps', ...)` para dependencias lentas.

4. Si confirma degradación de SQL:
   - Recomendar scale-up temporal (S2 → S3) durante la ventana de cierre.
   - Escalar a equipo de infraestructura (no hay JT para SQL scale).

5. Si la degradación es del container:
   - `lookup_infrastructure(mode='aci')` para validar restartCount y recursos.
   - Recomendar resize (manual).

**NUNCA** proponer restart durante cierre de nómina activo — puede dejar
transacciones inconsistentes.

---

## Escenario 4 — Posible brute force (TLNT-002 / TLNT-008 / TLNT-009 / TLNT-011)

**Síntoma**: alerta por aumento de logins fallidos o intentos excedidos.

**Pasos**:

1. Ejecutar `lookup_runtime_logs(modo='brute_force', usuario='', minutos=180, threshold=5)`.
   Devuelve usuarios sospechosos con severity HIGH/MEDIUM/LOW.

2. Si severity es HIGH:
   - Sintetizar al operador: usuarios afectados, cantidad de intentos.
   - Buscar en `file_search` definiciones de TLNT-002, TLNT-008, TLNT-009, TLNT-011.
   - Recomendar (NO ejecutar automáticamente):
     a. Bloquear IP en NSG (acción manual, no automatizada).
     b. Deshabilitar usuario en Entra ID si está comprometido (admin Entra ID).
     c. Notificar al SOC.

3. Correlacionar con `detect_anomalies(metric_type='auth_failures', ...)` para
   ver si hay spike estadístico que confirme el patrón.

4. Incluir `correlation_id`s en la respuesta para auditoría SOX.

---

## Escenario 5 — Investigación por correlation_id

**Síntoma**: operador da un correlation_id para investigar un caso puntual.

**Pasos**:

1. Llamar `lookup_correlation_id(correlation_id=..., time_range_hours=...)`.
   El bridge auto-detecta formato:
   - UUID con guiones → Spring Boot MDC (ContainerInstanceLog_CL)
   - Hex 32 chars sin guiones → App Insights OperationId (AppRequests/Traces/Exceptions)

2. Si devuelve 0 filas:
   - Ampliar la ventana temporal.
   - Verificar formato del correlation_id con el operador.
   - No seguir buscando sin más contexto.

3. Si hay filas:
   - Reconstruir la secuencia cronológica.
   - Identificar el primer ERROR/WARN.
   - Si hay código TLNT-XXX → buscar en `file_search` la definición.

4. Sintetizar: entrada de la petición, pasos ejecutados, punto de fallo,
   código TLNT con explicación y acción recomendada.

---

## Escenario 6 — Health check rutinario

**Síntoma**: operador o schedule periódico pregunta "cómo está TALENTO?".

**Pasos**:

1. Ejecutar `lookup_infrastructure(mode='full')` para obtener veredicto global
   HEALTHY/DEGRADED/CRITICAL con estado de ACI, App Service, Storage y Quotas.

2. Ejecutar `lookup_sql()` para estado de SQL Servers + databases.

3. Si `overall_severity` es HEALTHY y SQL está OK:
   - Reportar todos los componentes saludables + datos clave.

4. Si DEGRADED:
   - Identificar qué capa muestra problema.
   - Ejecutar `lookup_infrastructure` con el mode específico para detalle.
   - Sugerir validación adicional.

5. Si CRITICAL:
   - Identificar causa raíz con la tool específica + análisis de logs.
   - Sugerir acción concreta (no automatizar sin confirmación).

**NUNCA** ejecutar remediación tras health check sin que el operador lo pida.

---

## Escenario 7 — SQL degradado (slow queries / bloqueos / deadlocks)

**Síntoma**: lentitud reportada con evidencia de problema en base de datos.

**Pasos**:

1. Ejecutar `lookup_sql()` — si los Diagnostic Settings están activos en
   Log Analytics, devuelve automáticamente slow queries, bloqueos y deadlocks
   de las últimas 24h.

2. Si `diagnostics.available = false`:
   - El archivo indica cómo habilitarlos (Azure Portal → SQL Server →
     Monitoring → Diagnostic settings → enviar a Log Analytics workspace).
   - Mientras tanto, usar `lookup_app_insights(modo='slow_deps', ...)` para
     detectar dependencias lentas desde el lado de la aplicación.

3. Si hay slow queries identificadas:
   - Escalar al DBA con el detalle del query_hash y duration.
   - Recomendar análisis de índices (manual).

4. Si hay deadlocks:
   - Escalar al DBA para análisis de transacciones.
   - NO intentar matar sesiones — el agente no tiene esa capacidad.

---

## Escenario 8 — Anomalía estadística detectada

**Síntoma**: ELK dispara alerta por comportamiento inusual en métricas de TALENTO.

**Pasos**:

1. Ejecutar `detect_anomalies(metric_type='error_rate', time_range_hours=24)`
   para ver timestamps de anomalías con score.

2. Ejecutar `detect_anomalies(metric_type='auth_failures', time_range_hours=24)`.

3. Si hay SPIKEs en `auth_failures` → ejecutar `lookup_runtime_logs(modo='brute_force')`
   para identificar usuarios sospechosos.

4. Si hay SPIKEs en `error_rate` + spike simultáneo en `request_volume`:
   → probable sobrecarga de tráfico. Escalar a infra para autoscaling.

5. Si hay DIPs en `request_volume`:
   → posible caída del servicio. Ejecutar `lookup_infrastructure(mode='aci')`
   para verificar estado del container.

6. Correlacionar timestamps de anomalías con deployments recientes si aplica.

---

## Principios transversales del runbook (v21)

1. **Diagnóstico antes que acción**: usar `lookup_infrastructure`, `lookup_sql`
   o las tools de logs antes de proponer cualquier remediación.

2. **Dry-run por defecto**: cualquier acción invasiva se propone en dry-run
   primero. Solo se ejecuta real con confirmación explícita en segunda solicitud.

3. **Citar catálogo, no inventar**: si aparece código TLNT-XXX, consultar
   `talento_error_catalog.md` vía file_search y citar textualmente.

4. **Correlation ID es oro**: incluir siempre el correlation_id en la
   respuesta para trazabilidad y audit trail SOX.

5. **Reconocer límites**: si el problema requiere DBA, admin Entra ID o
   deploy de nueva versión, decirlo y escalar.

6. **AWX solo para remediación**: `run_awx_job_template` únicamente para
   restart/stop/start (4 JTs). Para diagnóstico → tools directas.

7. **Confirmaciones huérfanas**: solo ejecutar `dry_run=false` si en la
   conversación actual el agente propuso explícitamente la acción en dry-run
   y el operador la confirma. Sin propuesta previa = confirmación huérfana
   = rechazar y pedir aclaración.
