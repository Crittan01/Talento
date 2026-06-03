"""mock_events — secuencias pregrabadas para modo demo seguro.

Cada entrada es una lista de tuplas (delay_segundos, evento) que se
reproduce secuencialmente. Los timings imitan un run real para que la
demo se sienta natural.

Activacion:
  - `FORCE_MOCK=1` en env, o
  - URL `?mock=1` en el browser

Util cuando:
  - Internet flaqueando antes de la reunion
  - AWX/Foundry caidos
  - Ensayos de la demo sin gastar tokens/jobs reales
"""
from __future__ import annotations

# Eventos mock para snapshot (JT 48) — refleja artifacts reales observados
_SNAPSHOT = [
    (0.2, {"type": "agent.received", "question": "[mock] Snapshot del workspace",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "run_awx_job_template",
           "args": {"template_id": 48, "extra_vars": {"time_range_hours": 24}}}),
    (2.0, {"type": "tool.awx.launched", "template_id": 48, "job_id": 9001,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9001"}),
    (5.0, {"type": "tool.awx.polling", "job_id": 9001, "status": "running", "elapsed_seconds": 3.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9001, "status": "running", "elapsed_seconds": 6.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9001, "status": "running", "elapsed_seconds": 9.0}),
    (2.0, {"type": "tool.awx.done", "hop": 1, "job_id": 9001, "status": "successful",
           "elapsed_seconds": 11.2,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9001",
           "artifacts": {
               "time_range_hours": 24,
               "n_tables_with_data": "4",
               "top_table_name": "ContainerInstanceLog_CL",
               "top_table_rows": "1467",
               "schema_cols": "19",
               "sample_count": "10",
               "all_tables_summary": [
                   ["ContainerInstanceLog_CL", 1467],
                   ["ContainerEvent_CL", 30],
                   ["Usage", 8],
                   ["AzureDiagnostics", 1],
               ],
           }}),
    (2.0, {"type": "agent.final", "elapsed_seconds": 18.4,
           "text": (
               "### Hallazgo\n"
               "El workspace de TALENTO tiene 4 tablas con datos en las ultimas 24 horas:\n"
               "- ContainerInstanceLog_CL: 1.467 registros (tabla mas activa)\n"
               "- ContainerEvent_CL: 30 eventos\n"
               "- Usage: 8 entradas administrativas\n"
               "- AzureDiagnostics: 1 evento\n\n"
               "### Hipotesis\n"
               "1. Toda la telemetria operativa esta concentrada en logs de container.\n"
               "2. Application Insights aun no esta instrumentado por la app demo (EAPS).\n\n"
               "### Pasos de diagnostico\n"
               "- Validar que la instrumentacion de App Insights esta planeada por EAPS.\n"
               "- Continuar con analisis de errores (template 49) o auditoria SOX (template 50)."
           )}),
    (0.3, {"type": "done"}),
]

# Eventos mock para errors-analysis (JT 49)
_ERRORS = [
    (0.2, {"type": "agent.received", "question": "[mock] Errores en TALENTO",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "run_awx_job_template",
           "args": {"template_id": 49, "extra_vars": {"time_range_hours": 24}}}),
    (2.0, {"type": "tool.awx.launched", "template_id": 49, "job_id": 9002,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9002"}),
    (4.0, {"type": "tool.awx.polling", "job_id": 9002, "status": "running", "elapsed_seconds": 4.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9002, "status": "running", "elapsed_seconds": 7.0}),
    (3.0, {"type": "tool.awx.done", "hop": 1, "job_id": 9002, "status": "successful",
           "elapsed_seconds": 12.5,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9002",
           "artifacts": {
               "time_range_hours": 24,
               "total_errors": "114",
               "total_warnings": "77",
               "severity_status": "CRITICAL",
               "top_messages": [
                   ["\tat org.hibernate.exception.internal.SQLStateConversionDelegate.convert(SQLStateConversionDelegate.java:63) ~[hibernate-core-7.2.12.Final.jar!/:7.2.12.Final]", 12],
                   ["\tat org.hibernate.exception.internal.StandardSQLExceptionConverter.convert(StandardSQLExceptionConverter.java:34) ~[hibernate-core-7.2.12.Final.jar!/:7.2.12.Final]", 12],
                   ["\tat com.microsoft.sqlserver.jdbc.SQLServerException.makeFromDatabaseError(SQLServerException.java:270) ~[mssql-jdbc-12.8.1.jre11.jar!/:na]", 12],
                   ["No se pudo enviar la notificacion por correo: Authentication failed", 10],
                   ["Login failed for user 'sqlserver-ecopetrol-admin'", 6],
               ],
               "affected_containers": [["aci-centralecopetrol", 191]],
           }}),
    (2.0, {"type": "agent.final", "elapsed_seconds": 18.7,
           "text": (
               "### Hallazgo\n"
               "Severidad **CRITICAL**: 114 errores + 77 warnings en las ultimas 24h.\n"
               "Concentrados en el container aci-centralecopetrol (191 eventos criticos).\n\n"
               "### Hipotesis\n"
               "1. Stack traces de Hibernate apuntan a problemas de conectividad con SQL Server.\n"
               "2. Fallos repetidos de envio de email por authentication failed (10x).\n"
               "3. Failed logins SQL del usuario sqlserver-ecopetrol-admin sugieren credenciales\n"
               "   incorrectas o usuario revocado.\n\n"
               "### Acción correctiva\n"
               "- Validar credenciales del usuario sqlserver-ecopetrol-admin.\n"
               "- Revisar configuracion SMTP del servicio de notificaciones.\n"
               "- Adaptive card enviada al canal Teams del equipo operativo."
           )}),
    (0.3, {"type": "done"}),
]

# Eventos mock para SOX audit (JT 50)
_SOX = [
    (0.2, {"type": "agent.received", "question": "[mock] Auditoria SOX TALENTO",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "run_awx_job_template",
           "args": {"template_id": 50, "extra_vars": {"time_range_hours": 24}}}),
    (2.0, {"type": "tool.awx.launched", "template_id": 50, "job_id": 9003,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9003"}),
    (4.0, {"type": "tool.awx.polling", "job_id": 9003, "status": "running", "elapsed_seconds": 4.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9003, "status": "running", "elapsed_seconds": 7.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9003, "status": "running", "elapsed_seconds": 10.0}),
    (2.0, {"type": "tool.awx.done", "hop": 1, "job_id": 9003, "status": "successful",
           "elapsed_seconds": 14.3,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9003",
           "artifacts": {
               "time_range_hours": 24,
               "audit_status": "SECURITY_INCIDENT",
               "total_login_events": "22",
               "unique_users": "1",
               "total_privileged_actions": "27",
               "total_security_incidents": "40",
               "login_breakdown": [["nvivas", "REQUEST", 11], ["nvivas", "SUCCESS", 11]],
               "privileged_breakdown": [
                   ["CONSULTA_MASIVA", "", 17],
                   ["APROBAR", "LIDER", 10],
               ],
               "security_incidents": [
                   ["Login failed for user 'sqlserver-ecopetrol-admin'. ClientConnectionId:42dfab51-010d-4314-89cc-5f251428c161", 6],
                   ["SQLServerException.makeFromDatabaseError", 12],
                   ["org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'entityManagerFactory'", 6],
                   ["No se pudo enviar la notificacion por correo: Authentication failed", 10],
               ],
           }}),
    (2.0, {"type": "agent.final", "elapsed_seconds": 20.5,
           "text": (
               "### Hallazgo\n"
               "Estado **SECURITY_INCIDENT** — TALENTO con 40 incidentes de seguridad BD\n"
               "en las ultimas 24h. Usuario auditado: nvivas (22 eventos de login).\n\n"
               "Actividad privilegiada: 17 consultas masivas + 10 aprobaciones con rol=LIDER.\n\n"
               "### Hipotesis\n"
               "1. Failed logins SQL del usuario sqlserver-ecopetrol-admin pueden indicar\n"
               "   credenciales caducadas o intento de acceso no autorizado.\n"
               "2. ClientConnectionIDs trazables — auditables individualmente por SOX.\n"
               "3. Volumen de aprobaciones con rol=LIDER esta dentro de lo esperado.\n\n"
               "### Acción correctiva\n"
               "- Investigar causa de los failed logins SQL antes de la siguiente auditoria.\n"
               "- Adaptive card enviada al canal de seguridad."
           )}),
    (0.3, {"type": "done"}),
]

# Eventos mock para brute-force (JT 51)
_BRUTE_FORCE = [
    (0.2, {"type": "agent.received", "question": "[mock] Brute force detector",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "run_awx_job_template",
           "args": {"template_id": 51, "extra_vars": {"time_range_hours": 24, "failed_threshold": 5}}}),
    (2.0, {"type": "tool.awx.launched", "template_id": 51, "job_id": 9004,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9004"}),
    (4.0, {"type": "tool.awx.polling", "job_id": 9004, "status": "running", "elapsed_seconds": 4.0}),
    (3.0, {"type": "tool.awx.polling", "job_id": 9004, "status": "running", "elapsed_seconds": 7.0}),
    (3.0, {"type": "tool.awx.done", "hop": 1, "job_id": 9004, "status": "successful",
           "elapsed_seconds": 10.9,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9004",
           "artifacts": {
               "time_range_hours": 24,
               "failed_threshold": 5,
               "bruteforce_severity": "HIGH",
               "suspicious_users_count": "1",
               "suspicious_users": [["sqlserver-ecopetrol-admin", 18]],
               "total_failed_logins": 18,
               "total_db_failed": 12,
               "top_messages": [
                   ["Login failed for user 'sqlserver-ecopetrol-admin'. ClientConnectionId:42dfab51", 6],
                   ["Login failed for user 'sqlserver-ecopetrol-admin'. ClientConnectionId:8caeb58a", 4],
                   ["Login failed for user 'sqlserver-ecopetrol-admin'. ClientConnectionId:71fdce92", 2],
               ],
           }}),
    (2.0, {"type": "agent.final", "elapsed_seconds": 17.1,
           "text": (
               "### Hallazgo\n"
               "Severidad **HIGH**: detectado patron de brute force contra el usuario\n"
               "sqlserver-ecopetrol-admin con 18 intentos fallidos (umbral=5).\n\n"
               "12 failed logins llegaron hasta la capa de SQL Server con ClientConnectionIds\n"
               "distintos — sugiere origen automatizado.\n\n"
               "### Acción correctiva inmediata\n"
               "1. Bloquear temporalmente la cuenta sqlserver-ecopetrol-admin.\n"
               "2. Revisar logs de red para identificar IPs origen.\n"
               "3. Rotar credenciales del usuario afectado.\n"
               "4. Adaptive card roja enviada al canal de seguridad."
           )}),
    (0.3, {"type": "done"}),
]

# Eventos mock para payroll-slow (JT 49 con ventana corta)
_PAYROLL_SLOW = [
    (0.2, {"type": "agent.received", "question": "[mock] Lentitud cierre nomina",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "run_awx_job_template",
           "args": {"template_id": 49, "extra_vars": {"time_range_hours": 4}}}),
    (2.0, {"type": "tool.awx.launched", "template_id": 49, "job_id": 9005,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9005"}),
    (4.0, {"type": "tool.awx.polling", "job_id": 9005, "status": "running", "elapsed_seconds": 4.0}),
    (3.0, {"type": "tool.awx.done", "hop": 1, "job_id": 9005, "status": "successful",
           "elapsed_seconds": 8.7,
           "awx_url": "https://192.168.250.20.nip.io/#/jobs/playbook/9005",
           "artifacts": {
               "time_range_hours": 4,
               "total_errors": "42",
               "total_warnings": "23",
               "severity_status": "WARN",
               "top_messages": [
                   ["SQLException: Timeout expired", 8],
                   ["Connection pool exhausted, waiting for a free connection", 12],
                   ["Slow query detected, execution_time=4300ms", 5],
               ],
               "affected_containers": [["aci-centralecopetrol", 65]],
           }}),
    (2.0, {"type": "agent.final", "elapsed_seconds": 14.2,
           "text": (
               "### Hallazgo\n"
               "Lentitud confirmada en ventana de 4 horas. **42 errores + 23 warnings**\n"
               "con patron tipico de cierre de nomina:\n"
               "- 12x Connection pool exhausted\n"
               "- 8x SQLException Timeout expired\n"
               "- 5x Slow queries (>4 segundos)\n\n"
               "### Hipotesis (ordenada por probabilidad)\n"
               "1. Pool de conexiones BD saturado por queries lentas concurrentes.\n"
               "2. Queries de calculo de nomina sin indices apropiados.\n"
               "3. Recursos del container insuficientes para el pico de demanda.\n\n"
               "### Acción recomendada\n"
               "- Inmediato: aumentar tamanio del pool de conexiones.\n"
               "- Corto plazo: revisar queries lentas e indices.\n"
               "- Largo plazo: escalar el container durante ventanas de cierre."
           )}),
    (0.3, {"type": "done"}),
]

# Mock para pregunta libre — generic
_FREE_TEXT = [
    (0.2, {"type": "agent.received", "question": "[mock] Pregunta libre",
           "agent": "talento-triage-agent", "max_hops": 4}),
    (0.6, {"type": "agent.connecting"}),
    (1.0, {"type": "agent.hop", "hop": 1}),
    (1.4, {"type": "tool.call", "hop": 1, "tool": "query_log_analytics",
           "args": {"query": "union withsource=Tabla * | where TimeGenerated > ago(24h) | summarize count() by Tabla"}}),
    (1.8, {"type": "tool.kql.done", "hop": 1, "rows": 4, "elapsed_seconds": 1.6}),
    (1.5, {"type": "agent.final", "elapsed_seconds": 5.3,
           "text": (
               "### Hallazgo\n"
               "Pregunta libre procesada. El agente eligio query directo de Log Analytics\n"
               "(no requirio AWX). Encontradas 4 tablas pobladas en 24h.\n\n"
               "(Esto es respuesta mock — en modo real el agente decide segun el contexto\n"
               "que tool usar y devuelve una sintesis especifica de la pregunta.)"
           )}),
    (0.3, {"type": "done"}),
]

# Mock simple para correlation-trace (free-text con UUID)
_CORRELATION = [
    (0.0, {"type": "agent.received", "question": "Investigar correlation_id"}),
    (0.2, {"type": "agent.hop", "hop": 1}),
    (0.3, {"type": "tool.call", "hop": 1, "tool": "file_search",
           "args": {"query": "patron 3 trazabilidad correlation_id"}}),
    (0.5, {"type": "tool.call", "hop": 1, "tool": "query_log_analytics",
           "args": {"query": "ContainerInstanceLog_CL | where ... correlation_id == '8f660c47-...'"}}),
    (1.0, {"type": "tool.kql.done", "hop": 1, "rows": 12, "elapsed_seconds": 1.2}),
    (1.2, {"type": "agent.final",
           "text": ("### Hallazgo\n"
                    "Reconstrui 12 eventos para correlation_id 8f660c47.\n"
                    "Entrada: POST /api/vacaciones a las 10:32:18.\n"
                    "Fallo en el paso 7 con TLNT-014 (VACACIONES_NO_ENCONTRADAS).\n"
                    "\n(Mock — en modo real consulta KQL patron 3 contra LA)")}),
    (0.2, {"type": "done"}),
]

# Mock simple para tlnt-lookup (free-text con codigo TLNT)
_TLNT_LOOKUP = [
    (0.0, {"type": "agent.received", "question": "Consultar codigo TLNT"}),
    (0.2, {"type": "agent.hop", "hop": 1}),
    (0.3, {"type": "tool.call", "hop": 1, "tool": "file_search",
           "args": {"query": "TLNT-007 ERROR_VALIDACION"}}),
    (0.6, {"type": "agent.final",
           "text": ("### TLNT-007 — ERROR_VALIDACION\n"
                    "**Descripcion:** Error inesperado en validacion (excepcion no controlada).\n"
                    "**Modulo:** Cualquier validacion.\n"
                    "**Solucion para usuario:** Reporte al soporte.\n"
                    "**Accion soporte:** Buscar correlation_id en logs para stack trace. Severidad ERROR.\n"
                    "\n(Mock — en modo real cita textualmente desde knowledge base)")}),
    (0.2, {"type": "done"}),
]

# Mock para user-activity (free-text con username)
_USER_ACTIVITY = [
    (0.0, {"type": "agent.received", "question": "Investigar actividad usuario"}),
    (0.2, {"type": "agent.hop", "hop": 1}),
    (0.3, {"type": "tool.call", "hop": 1, "tool": "file_search",
           "args": {"query": "actividad por usuario patron 11 KQL"}}),
    (0.5, {"type": "tool.call", "hop": 1, "tool": "query_log_analytics",
           "args": {"query": "ContainerInstanceLog_CL | where ... p.usuario == 'nvivas'"}}),
    (1.0, {"type": "tool.kql.done", "hop": 1, "rows": 23, "elapsed_seconds": 1.0}),
    (1.2, {"type": "agent.final",
           "text": ("### Hallazgo\n"
                    "Actividad del usuario 'nvivas' en 24h: 23 eventos.\n"
                    "- 2 logins exitosos\n"
                    "- 5 logins fallidos (4× TLNT-008 password incorrecta, "
                    "1× TLNT-011 intentos excedidos) → POSIBLE BRUTE FORCE\n"
                    "- 14 listados de usuarios (rol consulta)\n"
                    "- 2 errores TLNT-007 (ERROR_VALIDACION) sin patron claro\n"
                    "\n### Hipotesis\n"
                    "Cuenta posiblemente bajo ataque. Recomiendo revisar IPs origen "
                    "y considerar bloqueo temporal.\n"
                    "\n(Mock — en modo real consulta patron 11 contra LA con datos reales)")}),
    (0.2, {"type": "done"}),
]

MOCK_SEQUENCES = {
    "system-status": _SNAPSHOT,
    "errors-production": _ERRORS,
    "sox-audit": _SOX,
    "brute-force": _BRUTE_FORCE,
    "payroll-slow": _PAYROLL_SLOW,
    "correlation-trace": _CORRELATION,
    "tlnt-lookup": _TLNT_LOOKUP,
    "user-activity": _USER_ACTIVITY,
    "free-text": _FREE_TEXT,
}


def get_events(scenario_id: str):
    """Devuelve lista [(delay, evento)] para el scenario. Vacio si no existe."""
    return MOCK_SEQUENCES.get(scenario_id, [])
