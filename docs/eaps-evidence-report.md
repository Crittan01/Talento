# Evidencia de gaps de telemetria TALENTO
_Generado: 2026-05-28 22:36 UTC · Workspace: `9e0a97a6-6839-4507-aae4-e4d706d1c320` · Rango: ultimos 7 dias_

Este reporte es **evidencia empirica** del estado actual de la telemetria emitida por la app TALENTO (simulada por EAPS). Sustenta el pedido formal de robustecimiento al equipo EAPS — no es opinion, son datos del workspace real.

---

## 1. Inventario completo del workspace (ultimos N dias)

_Lista TODAS las tablas con datos. Identifica si Application Insights esta o no instrumentado._

Tablas con datos en los ultimos 7 dias: **4**
| Tabla | Registros | Primera | Ultima |
| --- | --- | --- | --- |
| AzureDiagnostics | 5295 | 2026-05-23T00:32:20.5706237Z | 2026-05-28T22:34:41.1874199Z |
| ContainerInstanceLog_CL | 1787 | 2026-05-22T13:33:47.1021456Z | 2026-05-27T15:23:21.4882531Z |
| Usage | 66 | 2026-05-22T14:00:00Z | 2026-05-28T22:00:00Z |
| ContainerEvent_CL | 35 | 2026-05-22T13:09:23.5890619Z | 2026-05-24T05:28:25.9052897Z |

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
| otro | 42 | 42.0% |
| business_event | 26 | 26.0% |
| error_or_warn | 17 | 17.0% |
| framework_boot | 14 | 14.0% |
| stack_trace | 1 | 1.0% |
| vacio_o_decorativo | 0 | 0.0% |

> ⚠️ **Solo 26.0% de los logs son eventos de negocio identificables.** El resto es ruido de framework/stack traces. Para el agente, esto significa que la mayoria del log es 'inutil' para diagnostico funcional. **Pedir a EAPS niveles de log diferenciados o filtros logback que reduzcan ruido.**

---

## 4. Codigos de error estructurados detectados

_Busca patrones `TLNT-XXXX`, `ERR-XXX`, `[CODE-XX]`, `error_code=XXX`. Indica si hay catalogo emitido._

Codigos detectados: **0**

> ⚠️ **EAPS no emite codigos de error estructurados** (no se encontraron patrones tipo `TLNT-XXXX`, `ERR-XXX`, `[CODE-XXX]`, ni `error_code=XXX`). El agente no puede citar 'el error X significa Y' porque no hay X. **Pedido Tier 1.2: catalogo de error codes + emisin en cada log de error/warn.**

---

## 5. Cardinalidad de templates de mensaje (top 30)

_Mide si pocos mensajes-template dominan (= logs estructurados) o hay alta variedad (= logs ad-hoc)._

Total logs en 7d: **1,787**
Top 30 templates cubren: **23.2%** del total

| Template | Count |
| --- | --- |
| 	at org.springframework.boot.SpringApplication.run(SpringApplication.java:<N>) ~[spring-boot-4.0.6.jar!/:4.0.6] | 36 |
| 	at org.hibernate.engine.jdbc.spi.SqlExceptionHelper.convert(SqlExceptionHelper.java:<N>) ~[hibernate-core-7.2.12.Fin... | 24 |
| 	at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.initializeBean(AbstractAutowireCapab... | 18 |
| 	at org.springframework.orm.jpa.AbstractEntityManagerFactoryBean.buildNativeEntityManagerFactory(AbstractEntityManage... | 18 |
| 	at org.hibernate.resource.transaction.backend.jdbc.internal.DdlTransactionIsolatorNonJtaImpl.getIsolatedConnection(D... | 18 |
| No se pudo enviar la notificacion por correo: Authentication failed | 13 |
| 	at org.springframework.beans.factory.support.AbstractBeanFactory.doGetBean(AbstractBeanFactory.java:<N>) ~[spring-be... | 12 |
| 	at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.invokeInitMethods(AbstractAutowireCa... | 12 |
| 	at org.springframework.boot.SpringApplication.refresh(SpringApplication.java:<N>) ~[spring-boot-4.0.6.jar!/:4.0.6] | 12 |
| 	at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.doCreateBean(AbstractAutowireCapable... | 12 |
| 	at org.springframework.boot.SpringApplication.refreshContext(SpringApplication.java:<N>) ~[spring-boot-4.0.6.jar!/:4... | 12 |
| 	at org.springframework.orm.jpa.AbstractEntityManagerFactoryBean.afterPropertiesSet(AbstractEntityManagerFactoryBean.... | 12 |
| 	at org.springframework.boot.loader.launch.Launcher.launch(Launcher.java:64) ~[app.jar:0.0.1-SNAPSHOT] | 12 |
| 	at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory.createBean(AbstractAutowireCapableBe... | 12 |
| 	at org.springframework.beans.factory.support.AbstractBeanFactory.lambda$doGetBean$0(AbstractBeanFactory.java:<N>) ~[... | 12 |
| 	at org.hibernate.exception.internal.SQLStateConversionDelegate.convert(SQLStateConversionDelegate.java:63) ~[hiberna... | 12 |
| 	at org.springframework.beans.factory.support.DefaultSingletonBeanRegistry.getSingleton(DefaultSingletonBeanRegistry.... | 12 |
| 	at org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean.createNativeEntityManagerFactory(LocalContaine... | 12 |
| 	at org.springframework.context.support.AbstractApplicationContext.finishBeanFactoryInitialization(AbstractApplicatio... | 12 |
| 	at org.springframework.orm.jpa.vendor.SpringHibernateJpaPersistenceProvider.createContainerEntityManagerFactory(Spri... | 12 |
| 	at org.springframework.boot.loader.launch.JarLauncher.main(JarLauncher.java:40) ~[app.jar:0.0.1-SNAPSHOT] | 12 |
| 	at com.nttdata.ecopetrol.talento.TalentoApplication.main(TalentoApplication.java:10) ~[!/:0.0.1-SNAPSHOT] | 12 |
| 	at java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(Unknown Source) ~[na:na] | 12 |
| 	at java.base/java.lang.reflect.Method.invoke(Unknown Source) ~[na:na] | 12 |
| 	at org.hibernate.exception.internal.StandardSQLExceptionConverter.convert(StandardSQLExceptionConverter.java:34) ~[h... | 12 |
| 	at org.springframework.boot.loader.launch.Launcher.launch(Launcher.java:<N>) ~[app.jar:0.0.1-SNAPSHOT] | 12 |
| 	at org.springframework.context.support.AbstractApplicationContext.refresh(AbstractApplicationContext.java:<N>) ~[spr... | 12 |
| 	at org.springframework.beans.factory.support.AbstractBeanFactory.getBean(AbstractBeanFactory.java:<N>) ~[spring-bean... | 12 |
| 	at org.springframework.boot.web.server.servlet.context.ServletWebServerApplicationContext.refresh(ServletWebServerAp... | 12 |
| 	at org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean.afterPropertiesSet(LocalContainerEntityManager... | 12 |

> ⚠️ **Alta cardinalidad de mensajes** (el top-30 cubre <60%). Sugiere logs muy ad-hoc, no estructurados. **Pedir a EAPS pattern de logs estructurados (JSON con `message_template` fijo + variables aparte).**

---

## 6. Correlation IDs / Distributed Tracing

_Detecta presencia de UUIDs, ClientConnectionId, request_id, traceparent. Esencial para seguir transacciones._

| Tipo de ID | Count | % de logs |
| --- | --- | --- |
| UUID generico | 62 | 3.5% |
| ClientConnectionId (SQL) | 62 | 3.5% |
| request_id / X-Request-ID / traceparent / trace_id | 0 | 0.0% |
| span_id | 0 | 0.0% |

Total logs analizados: **1,787**

> ⚠️ **NO hay correlation IDs ni distributed tracing.** El agente no puede seguir una transaccion HTTP -> microservicio -> BD -> SAP. **Pedir a EAPS: propagar `traceparent` (W3C Trace Context) o al menos `X-Request-ID` end-to-end. Integrar OpenTelemetry o Spring Sleuth.**

---

## 7. Distribucion de severidad

_Verifica si las severidades estan bien marcadas o si la mayoria es 'OTHER'._

| Severidad | Count | % |
| --- | --- | --- |
| OTHER | 1,069 | 59.8% |
| INFO | 477 | 26.7% |
| WARN | 127 | 7.1% |
| EXCEPTION | 90 | 5.0% |
| ERROR | 24 | 1.3% |

Total: **1,787**

> ⚠️ **59.8% de logs sin severidad detectable.** Spring Boot suele incluir ` INFO `/` WARN `/` ERROR ` en el formato estandar; este % sugiere logs sin patron consistente. **Pedir a EAPS: log pattern unificado con severity en posicion fija.**

---

## 8. Cobertura funcional (categorias HR)

_Que fraccion del log es eventos de procesos reales (vacaciones, login, aprobaciones) vs framework._

| Categoria | Count | % |
| --- | --- | --- |
| otro | 844 | 47.2% |
| boot_framework | 695 | 38.9% |
| auth_login | 154 | 8.6% |
| incapacidades | 39 | 2.2% |
| errores | 25 | 1.4% |
| calamidades | 20 | 1.1% |
| aprobaciones | 10 | 0.6% |

Total: **1,787**


---

## 9. Metricas de latencia presentes en logs

_Cuantos logs incluyen duraciones/timing. Importante para responder preguntas de performance._

Logs con metricas de latencia (ms/duration/elapsed/took): **18** de 1,787 (1.0%)

> ⚠️ **<5% de logs incluyen timing.** El agente no puede responder 'cuanto tarda X' sin metricas. **Pedir a EAPS: Application Insights con request duration auto-track + custom metrics para operaciones criticas (cierre nomina, validacion).**

---

## 10. Detalle de ContainerEvent_CL

_Eventos de orquestacion de container (BackOff, Terminating, etc.) - util para diagnostico de infra._

Eventos de container distintos: **7**

| ContainerName_s | Reason_s | Count |
| --- | --- | --- |
| aci-centralecopetrol | Started | 10 |
| aci-centralecopetrol | BackOff | 6 |
| aci-centralecopetrol | Terminating | 6 |
| aci-centralecopetrol | Pulling | 4 |
| aci-centralecopetrol | Stopping | 4 |
| aci-centralecopetrol | Pulled | 4 |
| aci-centralecopetrol | Killing | 1 |

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
