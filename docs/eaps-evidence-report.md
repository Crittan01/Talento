# Evidencia de gaps de telemetria TALENTO
_Generado: 2026-06-01 19:16 UTC · Workspace: `9e0a97a6-6839-4507-aae4-e4d706d1c320` · Rango: ultimos 7 dias_

Este reporte es **evidencia empirica** del estado actual de la telemetria emitida por la app TALENTO (simulada por EAPS). Sustenta el pedido formal de robustecimiento al equipo EAPS — no es opinion, son datos del workspace real.

---

## 1. Inventario completo del workspace (ultimos N dias)

_Lista TODAS las tablas con datos. Identifica si Application Insights esta o no instrumentado._

Tablas con datos en los ultimos 7 dias: **4**
| Tabla | Registros | Primera | Ultima |
| --- | --- | --- | --- |
| AzureDiagnostics | 17207 | 2026-05-25T19:17:08.9400514Z | 2026-06-01T19:15:43.7979359Z |
| ContainerInstanceLog_CL | 230 | 2026-05-26T13:12:36.8965133Z | 2026-05-30T21:43:35.1350888Z |
| Usage | 144 | 2026-05-25T20:00:00Z | 2026-06-01T18:00:00Z |
| ContainerEvent_CL | 5 | 2026-05-30T21:42:57.9551364Z | 2026-05-30T21:43:26.0405241Z |

> ⚠️ **No hay tablas `App*` (Application Insights)**: la app TALENTO NO esta instrumentada con App Insights. Las tablas operativas estandar (`AppExceptions`, `AppRequests`, `AppTraces`, `AppDependencies`) estan ausentes. Esto es el **gap mas critico**.

---

## 2. Schema completo de las tablas pobladas

_Verifica si hay campos `custom_*` (lo que indicaria que EAPS ya empezo a estructurar)._

### ContainerInstanceLog_CL (19 columnas)

| Columna | Tipo |
| --- | --- |
| TenantId | string |
| SourceSystem | string |
| MG | string |
| ManagementGroupName | string |
| TimeGenerated | datetime |
| Computer | string |
| RawData | string |
| ContainerGroup_s | string |
| ContainerID_s | string |
| ContainerImage_s | string |
| ContainerName_s | string |
| Location_s | string |
| Message | string |
| OSType_s | string |
| ResourceGroup | string |
| Source_s | string |
| SubscriptionId | string |
| Type | string |
| _ResourceId | string |

_Columnas custom detectadas (sufijos LA): 7_

### ContainerEvent_CL (20 columnas)

| Columna | Tipo |
| --- | --- |
| TenantId | string |
| SourceSystem | string |
| MG | string |
| ManagementGroupName | string |
| TimeGenerated | datetime |
| Computer | string |
| RawData | string |
| ContainerGroup_s | string |
| ContainerGroupInstanceId_g | string |
| ContainerID_s | string |
| ContainerName_s | string |
| Count_s | string |
| Location_s | string |
| Message | string |
| OSType_s | string |
| Reason_s | string |
| ResourceGroup | string |
| SubscriptionId | string |
| Type | string |
| _ResourceId | string |

_Columnas custom detectadas (sufijos LA): 8_


---

## 3. Calidad del log: clasificacion de N=100 mensajes aleatorios

_Estima que fraccion del log es realmente util para diagnostico de negocio vs ruido._

Muestreo de N=100 mensajes aleatorios:

| Categoria | Count | % |
| --- | --- | --- |
| business_event | 48 | 48.0% |
| otro | 26 | 26.0% |
| error_or_warn | 22 | 22.0% |
| framework_boot | 3 | 3.0% |
| vacio_o_decorativo | 1 | 1.0% |
| stack_trace | 0 | 0.0% |


---

## 4. Codigos de error estructurados detectados

_Busca patrones `TLNT-XXXX`, `ERR-XXX`, `[CODE-XX]`, `error_code=XXX`. Indica si hay catalogo emitido._

Codigos detectados: **0**

> ⚠️ **EAPS no emite codigos de error estructurados** (no se encontraron patrones tipo `TLNT-XXXX`, `ERR-XXX`, `[CODE-XXX]`, ni `error_code=XXX`). El agente no puede citar 'el error X significa Y' porque no hay X. **Pedido Tier 1.2: catalogo de error codes + emisin en cada log de error/warn.**

---

## 5. Cardinalidad de templates de mensaje (top 30)

_Mide si pocos mensajes-template dominan (= logs estructurados) o hay alta variedad (= logs ad-hoc)._

Total logs en 7d: **230**
Top 30 templates cubren: **13.9%** del total

| Template | Count |
| --- | --- |
| No se pudo enviar la notificacion por correo: Authentication failed | 3 |
| <N>-05-26T13:14:45.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-1] c.n.e.t.controller.TalentoController     : Solicitud ... | 1 |
| <N>-05-26T13:12:36.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-2] c.n.e.t.controller.TalentoController     : Login exit... | 1 |
| <N>-05-26T13:29:55.<N>Z  INFO 18 --- [talento] [io-<N>-exec-10] c.n.e.t.controller.TalentoController     : Solicitud ... | 1 |
| <N>-05-26T13:14:45.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-1] c.n.e.t.controller.TalentoController     : Login exit... | 1 |
| <N>-05-26T13:29:41.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-8] c.n.e.t.controller.TalentoController     : Solicitud ... | 1 |
| <N>-05-26T13:29:41.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-8] c.n.e.t.controller.TalentoController     : Login exit... | 1 |
|  =========\|_\|==============\|___/=/_/_/_/ | 1 |
| <N>-05-27T15:23:21.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-4] c.n.e.t.controller.TalentoController     : Listando t... | 1 |
| <N>-05-30T21:42:57.<N>Z  INFO 18 --- [talento] [ionShutdownHook] o.s.boot.tomcat.GracefulShutdown         : Commencin... | 1 |
|   .   ____          _            __ _ _ | 1 |
|  /\\ / ___'_ __ _ _(_)_ __  __ _ \ \ \ \ | 1 |
| ( ( )\___ \| '_ \| '_\| \| '_ \/ _` \| \ \ \ \ | 1 |
|  \\/  ___)\| \|_)\| \| \| \| \| \|\| (_\| \|  ) ) ) ) | 1 |
|   '  \|____\| .__\|_\| \|_\|_\| \|_\__, \| / / / / | 1 |
| <N>-05-26T19:13:27.<N>Z  INFO 18 --- [talento] [nio-<N>-exec-5] c.n.e.t.controller.TalentoController     : Solicitud ... | 1 |
|  :: Spring Boot ::                (v4.0.6) | 1 |
| <N>-05-30T21:43:28.<N>Z  INFO 19 --- [talento] [           main] c.n.e.talento.TalentoApplication         : Starting ... | 1 |
| <N>-05-30T21:43:28.<N>Z  INFO 19 --- [talento] [           main] c.n.e.talento.TalentoApplication         : No active... | 1 |
| <N>-05-30T21:43:30.<N>Z  INFO 19 --- [talento] [           main] .s.d.r.c.RepositoryConfigurationDelegate : Bootstrap... | 1 |
| <N>-05-30T21:43:30.<N>Z  INFO 19 --- [talento] [           main] .s.d.r.c.RepositoryConfigurationDelegate : Finished ... | 1 |
| <N>-05-30T21:43:31.<N>Z  INFO 19 --- [talento] [           main] o.s.boot.tomcat.TomcatWebServer          : Tomcat in... | 1 |
| <N>-05-30T21:43:31.<N>Z  INFO 19 --- [talento] [           main] o.apache.catalina.core.StandardService   : Starting ... | 1 |
| <N>-05-30T21:43:31.<N>Z  INFO 19 --- [talento] [           main] o.apache.catalina.core.StandardEngine    : Starting ... | 1 |
| <N>-05-30T21:43:31.<N>Z  INFO 19 --- [talento] [           main] b.w.c.s.WebApplicationContextInitializer : Root WebA... | 1 |
| <N>-05-30T21:43:32.<N>Z  INFO 19 --- [talento] [           main] org.hibernate.orm.jpa                    : HHH<N>: P... | 1 |
| <N>-05-30T21:43:33.<N>Z  INFO 19 --- [talento] [           main] org.hibernate.orm.core                   : HHH<N>: H... | 1 |
| <N>-05-30T21:43:34.<N>Z  INFO 19 --- [talento] [           main] o.s.o.j.p.SpringPersistenceUnitInfo      : No LoadTi... | 1 |
| <N>-05-30T21:43:34.<N>Z  INFO 19 --- [talento] [           main] com.zaxxer.hikari.HikariDataSource       : HikariPoo... | 1 |
| <N>-05-30T21:43:35.<N>Z  INFO 19 --- [talento] [           main] com.zaxxer.hikari.pool.HikariPool        : HikariPoo... | 1 |

> ⚠️ **Alta cardinalidad de mensajes** (el top-30 cubre <60%). Sugiere logs muy ad-hoc, no estructurados. **Pedir a EAPS pattern de logs estructurados (JSON con `message_template` fijo + variables aparte).**

---

## 6. Correlation IDs / Distributed Tracing

_Detecta presencia de UUIDs, ClientConnectionId, request_id, traceparent. Esencial para seguir transacciones._

| Tipo de ID | Count | % de logs |
| --- | --- | --- |
| UUID generico | 1 | 0.4% |
| ClientConnectionId (SQL) | 1 | 0.4% |
| request_id / X-Request-ID / traceparent / trace_id | 0 | 0.0% |
| span_id | 0 | 0.0% |

Total logs analizados: **230**

> ⚠️ **NO hay correlation IDs ni distributed tracing.** El agente no puede seguir una transaccion HTTP -> microservicio -> BD -> SAP. **Pedir a EAPS: propagar `traceparent` (W3C Trace Context) o al menos `X-Request-ID` end-to-end. Integrar OpenTelemetry o Spring Sleuth.**

---

## 7. Distribucion de severidad

_Verifica si las severidades estan bien marcadas o si la mayoria es 'OTHER'._

| Severidad | Count | % |
| --- | --- | --- |
| INFO | 176 | 76.5% |
| WARN | 41 | 17.8% |
| OTHER | 13 | 5.7% |

Total: **230**


---

## 8. Cobertura funcional (categorias HR)

_Que fraccion del log es eventos de procesos reales (vacaciones, login, aprobaciones) vs framework._

| Categoria | Count | % |
| --- | --- | --- |
| otro | 163 | 70.9% |
| incapacidades | 23 | 10.0% |
| auth_login | 22 | 9.6% |
| boot_framework | 9 | 3.9% |
| calamidades | 8 | 3.5% |
| errores | 3 | 1.3% |
| aprobaciones | 2 | 0.9% |

Total: **230**


---

## 9. Metricas de latencia presentes en logs

_Cuantos logs incluyen duraciones/timing. Importante para responder preguntas de performance._

Logs con metricas de latencia (ms/duration/elapsed/took): **2** de 230 (0.9%)

> ⚠️ **<5% de logs incluyen timing.** El agente no puede responder 'cuanto tarda X' sin metricas. **Pedir a EAPS: Application Insights con request duration auto-track + custom metrics para operaciones criticas (cierre nomina, validacion).**

---

## 10. Detalle de ContainerEvent_CL

_Eventos de orquestacion de container (BackOff, Terminating, etc.) - util para diagnostico de infra._

Eventos de container distintos: **4**

| ContainerName_s | Reason_s | Count |
| --- | --- | --- |
| aci-centralecopetrol | Stopping | 2 |
| aci-centralecopetrol | Pulling | 1 |
| aci-centralecopetrol | Started | 1 |
| aci-centralecopetrol | Pulled | 1 |

---

## Conclusion: pedidos prioritarios para EAPS

Basado en lo observado en los 10 probes, el pedido formal a EAPS deberia priorizar:

1. **Instrumentar Application Insights** en la app TALENTO (si las tablas `App*` del Probe 1 estan vacias).
   - Spring Boot starter `applicationinsights-spring-boot-starter` o similar.
   - Conecta automaticamente exceptions, requests, dependencies, traces a las tablas estandar.

2. **Logs estructurados en JSON** con campos fijos: `timestamp`, `severity`, `correlation_id`, `user_id`, `business_action`, `entity_id`, `error_code`, `http_status`, `latency_ms`, `module`.
   - Implementacion sugerida: `logback-spring.xml` + `logstash-logback-encoder`.

3. **Catalogo de error codes** (Probe 4 confirma que no hay).
   - Entregar archivo MD/JSON con cada codigo + severity + causa + remediacion.
   - Subible al vector store del agente Foundry (`file_search` tool).

4. **Correlation IDs end-to-end** (Probe 6 mide deficit actual).
   - Propagar `traceparent` (W3C) o `X-Request-ID` a SAP / SuccessFactors / AD / Salud.

5. **Niveles de log diferenciados** (si Probe 8 muestra >50% framework noise).
   - `logging.level.org.springframework=WARN` (o INFO solo para clases propias).
   - Reduce coste de ingestion y mejora ratio signal/noise para el agente.

---

_Re-ejecutar este script `python3 scripts/probe-workspace.py` cuando EAPS entregue cambios para comparar el progreso._
