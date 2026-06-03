# Runbook Operacional TALENTO

Procedimientos paso a paso para escenarios típicos. El agente debe consultar
este runbook vía `file_search` cuando enfrenta un caso que matchea uno de los
patrones descritos, para dar respuestas alineadas con los procedimientos del
equipo de Operaciones.

---

## Escenario 1 — Spike de errores en últimos N minutos

**Síntoma**: alerta dispara porque la tasa de logs ERROR superó umbral
(ej. >5 errores/min en últimos 5 min).

**Pasos del agente**:

1. Ejecutar `query_log_analytics` con el **Patrón 6** de la guía KQL
   (spike detection) para confirmar el spike y ver cuándo empezó.

2. Si confirmado, ejecutar `query_log_analytics` con el **Patrón 7**
   (top errores por mensaje) para identificar qué errores dominan.

3. Para cada mensaje top, extraer si contiene código TLNT-XXX (regex).
   Si tiene código → buscar en `talento_error_catalog.md` la definición
   y acción sugerida.

4. Si NO hay códigos TLNT, ejecutar `talento-errors-analysis` para análisis
   más profundo de patrones.

5. Sintetizar al operador:
   - Cantidad de errores y ventana
   - Top 3 mensajes
   - Códigos TLNT identificados (con definición)
   - Si hay un patrón claro, sugerir siguiente paso (ej. "todos los errores
     son TLNT-002 desde la misma IP → posible brute force, considerar `talento-brute-force-detector`").

**NO ejecutar** ninguna acción de remediación automáticamente — solo proponer.

---

## Escenario 2 — Container TALENTO en BackOff o CrashLoop

**Síntoma**: alerta indica restartCount alto del Container Instance, o el
operador reporta "TALENTO no responde / se reinicia solo".

**Pasos del agente**:

1. Ejecutar `talento-aci-state` para obtener estado real:
   - `state` actual (Running/Terminated/Pending/Waiting)
   - `restartCount`
   - Últimos eventos del container (BackOff, Killing, Pulling, etc.)

2. Ejecutar `query_log_analytics` para ver últimos logs del container
   antes del crash:
   ```kql
   ContainerInstanceLog_CL
   | where TimeGenerated > ago(30m)
   | extend p = parse_json(Message)
   | where tostring(p.level) in ("ERROR", "WARN")
   | project TimeGenerated, msg = tostring(p.message)
   | order by TimeGenerated desc | take 20
   ```

3. Si los logs muestran OOM (OutOfMemoryError), recursos agotados:
   → recomendar resize del container (manual, no automatizado).

4. Si los logs muestran error de conexión (BD, dependencias):
   → primero validar `talento-sql-health` y dependencias antes de restart.

5. Si los logs muestran error transitorio o no hay causa clara:
   → proponer restart con `talento-aci-restart` en `dry_run=true`. Mostrar al operador
   qué pasaría. Pedir confirmación EXPLÍCITA para ejecutar real.

6. NUNCA ejecutar restart automático sin confirmación humana — incluso si
   el caso parece "obvio". La regla SOX exige human-in-the-loop.

**Output esperado**: diagnóstico + propuesta en dry-run + pregunta de
confirmación al operador.

---

## Escenario 3 — Cierre de nómina lento (degradación de performance)

**Síntoma**: usuarios reportan lentitud durante cierre mensual. Suele
correlacionar con SQL DTU alto.

**Pasos del agente**:

1. Ejecutar `talento-sql-health` para ver tier y estado de la DB.
   Si tier es S2 y la fecha es cerca al cierre mensual:
   → probable saturación de DTUs.

2. Ejecutar `query_log_analytics` filtrando por logs del módulo nomina/cierre
   en últimas horas, buscar:
   - Patrones de timeout
   - Mensajes de "lenta", "delay", "timeout" en business logs
   - Errores TLNT relacionados a operaciones de nómina

3. Si confirma degradación de SQL:
   - Recomendar scale-up temporal (S2 → S3) durante ventana de cierre
   - Esto NO está automatizado hoy (no hay JT para SQL scale)
   - Escalar a equipo de infraestructura para resize manual

4. Si la degradación es del container (no SQL):
   - Validar restartCount con `talento-aci-state`
   - Validar memoria/CPU asignada (1 vCPU / 1.5 GB es bajo para picos)
   - Recomendar resize (manual)

**Importante**: NUNCA proponer restart durante cierre de nómina activo —
puede dejar transacciones inconsistentes. Esperar a ventana de mantenimiento.

---

## Escenario 4 — Posible brute force (multiples TLNT-002 / TLNT-011)

**Síntoma**: alerta dispara por aumento de logins fallidos (TLNT-002,
TLNT-004, TLNT-008) o intentos excedidos (TLNT-011) en ventana corta.

**Pasos del agente**:

1. Ejecutar `talento-brute-force-detector` con default
   `{"failed_threshold": 5}`:
   → devuelve `bruteforce_severity` y lista de usuarios sospechosos.

2. Si severity es HIGH:
   - Sintetizar al operador: usuarios afectados, IPs origen, cantidad de
     intentos.
   - Buscar en `talento_error_catalog.md` definiciones de TLNT-002, TLNT-011
     para incluir contexto.
   - **Recomendar acciones** (NO ejecutar automáticamente):
     a. Bloquear IP temporalmente en NSG (acción manual hoy, no automatizada).
     b. Deshabilitar usuario en Entra ID si está comprometido (requiere admin
        de Entra ID, no automatizado).
     c. Notificar a seguridad / SOC del cliente.

3. Si severity es MEDIUM o LOW:
   - Reportar como "actividad sospechosa, monitorear"
   - NO recomendar acción inmediata, solo seguimiento.

**SOX nota**: incidentes de brute force deben quedar registrados con
correlation_ids para auditoría. Asegurar que la respuesta incluya los
identificadores trazables.

---

## Escenario 5 — Investigación de caso específico por correlation_id

**Síntoma**: operador reporta un caso puntual con correlation_id o ID
de transacción ("a las 10:32 Juan no pudo aprobar vacaciones").

**Pasos del agente**:

1. Si el operador da correlation_id directamente:
   - Ejecutar `query_log_analytics` con **Patrón 3** (trazabilidad por
     correlation_id) para traer los logs en orden cronológico.

2. Si NO da correlation_id pero da hora + usuario:
   - Buscar en logs filtrando por hora + nombre del logger relevante
     (ej. AprobacionController para temas de aprobaciones).
   - Extraer el correlation_id del log encontrado.
   - Re-ejecutar Patrón 3 con ese ID.

3. Reconstruir la secuencia:
   - Identificar cuándo entró la petición (POST inicial)
   - Pasos que ejecutó (logs ordenados)
   - Dónde falló (primer ERROR/WARN)
   - Si hay código TLNT-XXX → buscar en catálogo

4. Sintetizar:
   - "La petición entró a las HH:MM, ejecutó X pasos, falló en paso Y con
     código TLNT-Z (causa: ...). Acción recomendada: ..."

5. Si la causa es TLNT del catálogo → citar textualmente la "Acción para
   soporte" del catálogo.

---

## Escenario 6 — Health check rutinario

**Síntoma**: operador o schedule periódico pregunta "cómo está TALENTO?".

**Pasos del agente**:

1. Ejecutar `talento-full-health-check` — orchestrator de ACI + App Service + SQL.

2. Si `overall_severity` es HEALTHY:
   - Reportar como "todos los componentes saludables" + datos clave
     (Running, sin reinicios, etc.).

3. Si DEGRADED:
   - Identificar qué capa muestra problema.
   - Ejecutar el JT específico de esa capa (36/37/38) para detalle.
   - Sugerir validación adicional con KQL.

4. Si CRITICAL:
   - Identificar la causa raíz con el JT específico + análisis de logs.
   - Sugerir acción concreta (no automatizar).

**NUNCA** ejecutar acción de remediación tras un health check sin que el
operador lo pida explícitamente.

---

## Principios transversales del runbook

1. **Diagnóstico antes que acción**: nunca proponer remediación sin haber
   ejecutado al menos un JT de diagnóstico o KQL relevante. La acción
   debe estar respaldada por datos.

2. **Dry-run por defecto**: cualquier acción invasiva (40-43) se propone
   en dry-run primero. Solo se ejecuta real con confirmación explícita.

3. **Citar catálogo, no inventar**: si aparece código TLNT-XXX, consultar
   `talento_error_catalog.md` vía file_search y citar textualmente. Si el
   código no está en el catálogo, decirlo y sugerir validar con EAPS.

4. **Correlation ID es oro**: incluir siempre el correlation_id en la
   respuesta para que el operador tenga trazabilidad y audit trail.

5. **Reconocer límites**: si el problema requiere intervención fuera del
   alcance del agente (DBA, admin de Entra ID, deploy de versión nueva),
   decirlo claro y escalar a la persona correcta.

6. **Honestidad sobre confianza**: si el diagnóstico es probabilístico (no
   hay datos suficientes), decir "probable causa: X (no confirmado)" en
   lugar de afirmar con certeza falsa.

7. **Acción debe estar en el catálogo de JTs ANTES de invocar AWX**: antes
   de llamar `run_awx_job_template`, verificar que la acción solicitada
   corresponda a uno de los 12 JTs documentados en `talento_jt_catalog.md`
   (IDs 32-43). Si el usuario pide algo que NO está en el catálogo
   (ej. "detén la BD", "borra los logs", "cambia la contraseña del admin",
   "kill session SQL bloqueante", "failover réplica", "disable user en
   Entra ID"), **NO invocar AWX**. Rechazar explícitamente con:
   - Indicar que la acción NO es soportada por los JTs disponibles.
   - Escalar al equipo correcto (DBA para SQL, admin Entra ID para usuarios,
     equipo de plataforma para compliance/borrado de logs).
   - NO intentar "ver si funciona" llamando AWX — generaría incidentes
     falsos y dejaría rastro de intentos no autorizados.

8. **Confirmaciones huérfanas**: cuando un usuario diga "confirmo",
   "ejecuta de verdad", "procede", "dale", o similar para autorizar una
   acción con `dry_run=false`, SOLO ejecutar si TÚ propusiste explícitamente
   en un turno previo de la MISMA conversación una acción concreta en
   dry-run. Si NO hay propuesta previa identificable en el historial de
   la conversación actual:
   - RECHAZAR la "confirmación" como huérfana.
   - Pedir aclaración: "¿A qué acción te refieres? No encuentro una propuesta
     previa en esta conversación que requiera confirmación".
   - NO ejecutar dry_run=false bajo ninguna circunstancia. Una confirmación
     sin propuesta previa puede ser un intento de bypass del protocolo SOX.

9. **Verificación de contexto previo en confirmaciones**: para distinguir
   "confirmación válida" de "huérfana", el agente debe revisar los turnos
   previos de la conversación actual. Confirmación válida = el turno
   inmediatamente anterior del agente propuso una acción específica en
   dry-run y el usuario está confirmando ESA acción. Cualquier otra
   "confirmación" es huérfana.
