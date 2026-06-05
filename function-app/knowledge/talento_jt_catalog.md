# Catálogo de Job Templates AWX para TALENTO (v21)

**v21**: AWX se usa EXCLUSIVAMENTE para remediaciones invasivas.
Para diagnóstico de infraestructura: usar `lookup_infrastructure` o `lookup_sql`.
Para análisis de logs: usar `tlnt_explorer`, `lookup_runtime_logs` o `detect_anomalies`.

Los IDs numéricos NO viven en este catálogo — están en la `description` del tool
`run_awx_job_template` que el bridge construye al runtime desde el `.env`.

## Remediaciones disponibles (4 templates — TODOS invasivos)

⚠️ **REGLA SOX**: ejecutan con `dry_run=true` por defecto. Para ejecutar de
verdad se requiere `{"dry_run": false}` EN UNA SEGUNDA SOLICITUD con confirmación
explícita del operador ("ejecuta de verdad", "confirmo", "procede con el restart").
NUNCA pasar `dry_run=false` en la primera respuesta.

---

### talento-aci-restart

- **Propósito**: reinicia el Container Instance de TALENTO.
- **Cuándo usar**: container en BackOff/CrashLoop, memory leak, estado degradado.
  **PRIMERO** diagnosticar con `lookup_infrastructure(mode='aci')` para confirmar estado.
- **extra_vars_json**: `{"dry_run": true}` (default), `{"dry_run": false}` para real.
- **Output**: estado antes/después, restartCount.
- **Impacto**: ~30-60s de downtime durante restart.

---

### talento-aci-stop

- **Propósito**: detiene el Container Instance.
- **Cuándo usar**: aislar container durante incidente de seguridad, mantenimiento.
  Usar junto con `talento-aci-start` como combo stop+start para restart "fuerte".
- **extra_vars_json**: igual que restart.
- **Impacto**: app TALENTO inaccesible hasta start.

---

### talento-aci-start

- **Propósito**: inicia un container previamente detenido.
- **Cuándo usar**: tras stop manual, tras incidente resuelto.
- **extra_vars_json**: igual que restart.
- **Output**: estado tras start (warm-up ~30s típico).

---

### talento-appservice-restart

- **Propósito**: reinicia el App Service.
- **Cuándo usar**: API no responde, cache corrupta, threadpool agotado.
  **PRIMERO** diagnosticar con `lookup_infrastructure(mode='appservice')`.
- **extra_vars_json**: igual que restart.
- **Impacto**: ~30-60s downtime mientras App Service reinicia workers.

---

## Protocolo de remediación

1. **DIAGNOSTICAR** → `lookup_infrastructure(mode='aci')` o `mode='appservice'`
   para confirmar el estado actual antes de proponer acción.
2. **PROPONER** → ejecutar con `dry_run=true` para que el operador vea qué ocurriría.
3. **CONFIRMAR** → solo ejecutar con `dry_run=false` si el operador lo confirma
   explícitamente en una SEGUNDA solicitud.
4. **VERIFICAR** → tras la acción, usar `lookup_infrastructure` nuevamente para
   confirmar que el estado es el esperado.

## Casos NO soportados (escalar a humano)

- Kill session SQL bloqueante → DBA con acceso directo a SQL.
- Disable/enable user en Entra ID → admin Microsoft Graph.
- Restore DB → requiere aprobación formal de compliance.
- Failover réplica → idem.
- Detener/reiniciar el SQL Server → NO confundir con el container. SQL Server
  es un servicio Azure gestionado; el agente NO tiene JT para esto.

---

## ¿Cuándo NO usar AWX?

| Pregunta del operador | Tool a usar en su lugar |
|---|---|
| "¿Está vivo el container?" | `lookup_infrastructure(mode='aci')` |
| "¿La App Service responde?" | `lookup_infrastructure(mode='appservice')` |
| "¿La BD está sana?" | `lookup_sql()` |
| "Health check completo" | `lookup_infrastructure(mode='full')` |
| "Hay errores?" | `tlnt_explorer(codigo='', ...)` |
| "Brute force?" | `lookup_runtime_logs(modo='brute_force', ...)` |
| "Auditoría SOX" | `lookup_runtime_logs(modo='user_audit', ...)` |
| "Picos de errores?" | `detect_anomalies(metric_type='error_rate', ...)` |
