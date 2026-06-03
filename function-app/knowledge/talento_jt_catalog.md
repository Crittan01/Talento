# Catálogo de Job Templates AWX para TALENTO

Este documento describe los 12 Job Templates disponibles en AWX Azure
(`http://172.210.65.202.nip.io`) que el agente puede invocar vía
`run_awx_job_template(template_id, extra_vars_json)`.

Los IDs corresponden al deployment ACTUAL en AWX Azure. Si se cambia de AWX
(ej. local), bump `CATALOG_VERSION` y re-subir este archivo.

---

## Categoría 1: Análisis de Logs (4 templates, NO invasivos)

Estos templates ejecutan KQL contra Log Analytics y devuelven análisis
agregado. NO modifican nada. Ejecutan en ~10-20s típicamente.

### JT 32 — talento-workspace-snapshot

- **Propósito**: inventario amplio del workspace (qué tablas tienen datos,
  schema, muestra).
- **Cuándo usar**: pregunta del tipo "qué hay en los logs", descubrimiento
  inicial, validación post-incidente.
- **extra_vars_json**: `{"time_range_hours": 24}` (default 24).
- **Output principal**: lista de tablas pobladas con conteos + top mensajes.

### JT 33 — talento-errors-analysis

- **Propósito**: análisis enfocado en ERROR/WARN agrupados por mensaje,
  containers afectados.
- **Cuándo usar**: "qué problemas tenemos", "errores en últimas N horas",
  diagnóstico de incidentes.
- **extra_vars_json**: `{"time_range_hours": 24}`.
- **Output**: `severity_status`, conteo errors/warnings, top mensajes,
  containers afectados.

### JT 34 — talento-sox-audit

- **Propósito**: auditoría SOX — logins por usuario, acciones privilegiadas
  con rol, incidentes de seguridad a nivel BD.
- **Cuándo usar**: "auditoría de accesos", "quién hizo qué", "cumplimiento
  SOX", "actividad sospechosa".
- **extra_vars_json**: `{"time_range_hours": 24}`.
- **Output**: `audit_status` (SECURITY_INCIDENT / AUDIT_REVIEW / NORMAL),
  logins agrupados, acciones privilegiadas, failed SQL logins.

### JT 35 — talento-brute-force-detector

- **Propósito**: detector específico de patrones de brute force (failed
  logins agrupados por usuario con umbral).
- **Cuándo usar**: "detectar brute force", "intentos de login fallidos",
  "ataques de fuerza bruta".
- **extra_vars_json**: `{"time_range_hours": 24, "failed_threshold": 5}`.
- **Output**: `bruteforce_severity` (HIGH/MEDIUM/LOW), lista de usuarios
  sospechosos, severity por IP.

---

## Categoría 2: Diagnóstico de Infraestructura (4 templates, NO invasivos)

Estos consultan el Azure ARM API para leer ESTADO de recursos. Solo lectura,
no modifican nada. Útil para complementar análisis de logs con estado real.

### JT 36 — talento-aci-state

- **Propósito**: estado actual del Container Instance de TALENTO.
- **Cuándo usar**: "está vivo el container?", investigación de crash loops,
  validación post-restart.
- **extra_vars_json**: `{}`.
- **Output**: state (Running/Terminated/Pending/...), restartCount, eventos
  recientes, CPU/memoria asignada, image.

### JT 37 — talento-appservice-state

- **Propósito**: estado del App Service (frontend/API).
- **Cuándo usar**: "la API responde?", health del App Service, availability.
- **extra_vars_json**: `{}`.
- **Output**: state (Running/Stopped), availability (Normal/Limited/...),
  host name, último deploy.

### JT 38 — talento-sql-health

- **Propósito**: estado del SQL Server + bases de datos.
- **Cuándo usar**: "la BD está sana?", investigación de problemas de
  performance, validación de tier.
- **extra_vars_json**: `{}`.
- **Output**: status del server, databases (Online/Offline), tier (S2/S3),
  tamaño usado.

### JT 39 — talento-full-health-check

- **Propósito**: orchestrator que ejecuta los 3 anteriores (ACI + App Service
  + SQL) en una sola corrida.
- **Cuándo usar**: pregunta amplia tipo "salud general de TALENTO", "health
  check completo", consulta inicial de un incidente sin causa identificada.
- **extra_vars_json**: `{}`.
- **Output**: `overall_severity` (HEALTHY/DEGRADED/CRITICAL), estado de cada
  capa, recomendación.

---

## Categoría 3: Remediación (4 templates, INVASIVOS con dry_run por defecto)

⚠️ **IMPORTANTE**: estos templates pueden modificar recursos productivos.
Por seguridad ejecutan en `dry_run=true` por defecto — solo simulan y reportan
qué SE EJECUTARÍA.

**Para ejecutar de verdad** se debe pasar `extra_vars_json` con
`{"dry_run": false}`. El agente NUNCA debe pasar `dry_run=false` sin
**confirmación explícita** del operador humano (segunda solicitud con
intent claro tipo "ejecuta de verdad" / "confirmo").

### JT 40 — talento-aci-restart

- **Propósito**: reinicia el Container Instance de TALENTO.
- **Cuándo usar**: container en BackOff/CrashLoop, memory leak detectado,
  estado degradado tras incidente.
- **extra_vars_json (dry-run)**: `{"dry_run": true}` (default).
- **extra_vars_json (real)**: `{"dry_run": false}` ← requiere confirmación.
- **Output**: estado antes/después, restartCount.
- **Impacto**: ~30-60s de downtime de la app durante restart.

### JT 41 — talento-aci-stop

- **Propósito**: detiene el Container Instance.
- **Cuándo usar**: aislar container durante incidente de seguridad, mantenimiento
  programado, preparación para start limpio (combo stop+start).
- **extra_vars_json**: igual que restart.
- **Output**: estado antes/después.
- **Impacto**: app TALENTO inaccesible hasta start. Azure deja de cobrar compute.

### JT 42 — talento-aci-start

- **Propósito**: inicia un container previamente detenido.
- **Cuándo usar**: tras stop manual, tras incidente resuelto, parte de combo
  stop+start como restart "fuerte".
- **extra_vars_json**: igual que restart.
- **Output**: estado tras start (warm-up ~30s típico).
- **Impacto**: container disponible. Idempotente si ya está Running.

### JT 43 — talento-appservice-restart

- **Propósito**: reinicia el App Service.
- **Cuándo usar**: API no responde, cache corrupta, threadpool agotado, tras
  cambio de configuración.
- **extra_vars_json**: igual que restart.
- **Output**: estado antes/después.
- **Impacto**: ~30-60s downtime mientras App Service reinicia workers.

---

## Protocolo del agente para usar los JTs

1. **Pregunta de salud/estado** → preferir JT 39 (full-health-check) si es amplia,
   o JTs específicos (36/37/38) si es focalizada.

2. **Pregunta de logs/errores** → preferir JTs de análisis (32-35) sobre KQL
   manual, porque los JTs ya implementan agregaciones probadas.

3. **Pregunta de remediación** ("reinicia X", "para Y"):
   - PRIMERO diagnosticar el estado actual con el JT de estado correspondiente.
   - DESPUÉS proponer la acción con `dry_run=true` para que el operador vea
     qué se haría.
   - SOLO ejecutar con `dry_run=false` si el operador lo confirma EXPLÍCITAMENTE
     en una segunda solicitud.

4. **Tras ejecutar acción** → consultar con KQL si los logs reflejan el cambio
   (ej. tras restart, esperar ~30s y verificar que aparecen logs nuevos).

5. **Si la acción falla** (HTTP no 200, timeout) → reportar honestamente al
   operador, NO reintentar automáticamente.

## Casos NO soportados por JTs (escalar a humano)

- Kill session SQL bloqueante → requiere usuario SQL con permisos, no es
  RBAC de Azure.
- Disable user en Entra ID → requiere permisos Microsoft Graph, otro admin.
- Restore DB a punto en el tiempo → DESTRUCTIVO, requiere aprobación humana
  formal (compliance).
- Failover a réplica secundaria → idem.
