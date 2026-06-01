---
marp: true
theme: default
paginate: true
header: 'Auto-remediación y Observabilidad TALENTO · NTT DATA × Ecopetrol'
footer: 'Talento EAPPS · 2026-05-27'
style: |
  section { font-family: 'Segoe UI', sans-serif; font-size: 22px; padding: 40px 50px 60px; }
  header { font-size: 12px; }
  footer { font-size: 12px; }
  h1 { color: #004236; border-bottom: 3px solid #CCD32A; padding-bottom: 6px; font-size: 1.6em; margin-bottom: 12px; }
  h2 { color: #004236; font-size: 1.2em; }
  table { font-size: 0.78em; margin: 8px 0; }
  th, td { padding: 4px 8px; }
  code { background: #F4F4F4; color: #C7254E; padding: 1px 4px; font-size: 0.9em; }
  pre { font-size: 0.82em; margin: 6px 0; }
  blockquote { border-left: 4px solid #F7DB17; padding-left: 12px; color: #555; margin: 8px 0; }
  ul, ol { margin: 4px 0; }
  li { margin: 2px 0; }
  p { margin: 6px 0; }
---

# Auto-remediación y Observabilidad en TALENTO

**4 items + auto-remediación**

_Talento EAPPS — basada en datos reales del workspace_

<br>

NTT DATA / Caso técnico 4.1 — Soporte TALENTO con agente IA
2026-05-27

---

# La pregunta de fondo

> ¿Por qué necesitamos cambios sobre lo que ya tenemos funcionando?

Porque el agente que estamos construyendo amplifica lo que TALENTO ya hace, pero **necesita datos procesables** — no texto plano.

**Hoy** el agente puede operar con lo que hay, pero **adivinando con probabilidad**.
**Con 4 items** pasa a operar con **certeza determinística** — y entonces escala de 10 a miles de tickets/día sin sumar gente.

---

# Estado actual del workspace — datos reales (7d, 1.735 logs)

| Métrica | Valor | Impacto |
|---|:---:|---|
| Tablas `App*` (App Insights) | **0 datos** | Recurso **desplegado pero sin instrumentar** |
| Códigos de error (TLNT-XXX) | **0** | No hay catálogo formal |
| Logs con correlation ID | **0%** | Sin trazas distribuidas |
| Logs sin severidad clara | **61.6%** | Agente no distingue ERROR de INFO |
| Logs con métricas de latencia | **1%** | Imposible medir performance |

> En resumen: la app emite logs **como texto libre**, sin estructura, sin IDs de correlación, sin niveles confiables. El agente *puede* trabajar con esto — pero adivinando.

---

# Caso real — HOY (sin los 4 items)

**Usuario reporta:** *"a las 10:32 Juan no pudo aprobar vacaciones"*

El soporte de TALENTO ve esto en Log Analytics:

```
2026-05-27 10:32:14 Intentando aprobar vacaciones [vacacionesId=42, rol=USUARIO]
2026-05-27 10:32:14 Acceso denegado: Usuario sin permiso de lider [vacacionesId=42, rol=USUARIO]
2026-05-27 10:32:14 (otros 200 logs del mismo minuto, distintos usuarios)
```

**El ingeniero tiene que adivinar:**
- ¿Quién es "Juan"? ¿Por nombre? ¿Por numEmpleado?
- ¿Qué módulo es "vacaciones"? (texto libre)
- ¿Qué significa "Acceso denegado"? ¿Bug? ¿Feature? ¿Permiso mal?
- Si tocó SAP/AD también — **no hay forma de saberlo desde estos logs**

**MTTR típico: 30–60 minutos** por incidente. No escala.

---

# Caso real — MAÑANA (con los 4 items)

Mismo caso. El agente ve:

```json
{
  "timestamp": "2026-05-27T10:32:14Z",
  "level": "WARN",
  "user_id": "78001", "user_name": "Juan",
  "module": "vacaciones.aprobacion",
  "error_code": "TLNT-042",
  "correlation_id": "req-a1b2c3d4"
}
```

**El agente hace:**
1. Filtra por `correlation_id=req-a1b2c3d4` → trae **las 8 líneas exactas** de esa petición
2. Lee `error_code=TLNT-042` → consulta catálogo → *"requiere rol LIDER en AD"*
3. Consulta `AppDependencies` → ve la llamada a AD: `groupMembership=[]`, 80ms
4. Sintetiza: *"Juan no tiene rol LIDER en AD. Acción: pedir al admin AD agregarlo a TALENTO_LIDERES"*

**MTTR: 30 segundos.** Y escalable a 1.000 tickets/día sin sumar gente.

---

# Ítem 1 — Logs en formato JSON estructurado

**Por qué:** elimina el regex sobre texto plano, habilita filtros KQL nativos por campos tipados.

| Sin esto | Con esto |
|---|---|
| Agente hace **regex frágil** — se rompe si el dev cambia el formato | Agente hace **KQL nativo** sobre campos: `where level == "ERROR"` |
| `user=Juan` ambiguo (¿campo? ¿texto en el mensaje?) | `user_id="78001"` tipado, no ambiguo |
| **61.6% de logs sin severidad detectable** (medido) | `level=ERROR` es campo tipado, contable |

**Solucion:** 1 archivo `logback-spring.xml` + dependencia `logstash-logback-encoder`.
**Cambio de código de negocio:** cero — los `logger.info()` actuales siguen igual.

---

# Ítem 2 — Catálogo de códigos de error

**Por qué:** sin un código formal, el agente no puede explicar al usuario con confianza ni automatizar respuestas comunes.

| Sin esto | Con esto |
|---|---|
| Agente lee `"Acceso denegado"` → **infiere** significado por contexto | Lee `error_code="TLNT-042"` → consulta catálogo → tiene **definición oficial + acción recomendada** |
| Puede sonar **inventado** al explicar al usuario | Cita texto oficial |
| **0 códigos detectados hoy** (medido en 1.735 logs) | Los 20-50 códigos más comunes cubren el 80% de los tickets |

**Esfuerzo :** un MD o JSON con los códigos que ya emite la app:

```json
{ "TLNT-042": { "title": "Sin rol LIDER", "remediation": "Asignar grupo TALENTO_LIDERES en AD" } }
```

Compatible al **vector store del agente Foundry** para consulta automática.

---

# Ítem 3 — Application Insights (ya desplegado)

**Datos del inventario Azure:**

| Servicio | SKU | RG | Estado |
|---|---|---|---|
| **Azure Application Insights** | Basic | `rg-central-solucion-talento` | **APROVISIONADO** |

**Pero las tablas están vacías:** `AppRequests`, `AppExceptions`, `AppDependencies` = 0 rows. El recurso, no recibe datos.

| Sin esto | Con esto |
|---|---|
| Solo vemos los `logger.info` que el dev **escribió a mano** | Vemos **automáticamente**: cada request HTTP con latencia, cada excepción con stack trace completo, cada llamada a SAP/SQL/AD con duración |
| Solo **1% de logs trae latency** (medido) | Cada request en `AppRequests` trae `duration` exacto |

**Esfuerzo :** 1 dependencia (`applicationinsights-spring-boot-starter` en `pom.xml`) + 1 variable de entorno con el connection string.

---

# Ítem 4 — Correlation ID

**Por qué:** una petición de un usuario toca varios sistemas (TALENTO → SAP → AD → Salud). Sin un ID común, **imposible reconstruir el flujo completo**.

| Sin esto | Con esto |
|---|---|
| Filtrar por usuario+hora → trae **decenas de líneas no relacionadas** del mismo minuto | Filtrar por `correlation_id=req-X` → **exactamente** los 8 pasos de esa petición |
| Imposible seguir a SAP/AD/Salud — cada sistema usa su propio ID | El **mismo ID** viaja en cabecera HTTP → buscar en todos los sistemas = vista end-to-end |
| **0% de logs con correlation ID hoy** (medido) | Cualquier incidente multi-sistema se resuelve en 1 query |

**Esfuerzo :** 1 dependencia `spring-cloud-starter-sleuth` (auto-instrumenta) **o** un `Filter` Java de ~20 líneas.

---

# Cómo se conecta todo: la auto-remediación

Los 4 items habilitan **diagnóstico preciso**. La auto-remediación cierra el loop **actuando**.

**Ciclo HOY:**
```
incidente → usuario reporta → soporte diagnostica (30 min)
         → soporte llama a Encargado → Encargado reinicia (5+ min más)
```

**Ciclo MAÑANA:**
```
incidente → agente detecta + diagnostica + propone restart en dry-run
         → humano aprueba con un click → ejecuta (30s)
```

**Importante:** la auto-remediación **sin los 4 items previos es peligrosa** — el agente puede reiniciar por la razón equivocada. Por eso los 4 items son **prerequisito** de la auto-remediación responsable.

---

# Auto-remediación en acción — ya construida y probada

Ya tenemos cableado el flujo end-to-end contra el AWX local. Datos del último test:

| Escenario | JT | Job AWX | Status | Tiempo |
|---|---|---|---|---|
| Health Check Completo | 55 | 437 | HEALTHY | 8.9s |
| Estado Container | 52 | 438 | HEALTHY | 7.2s |
| Estado App Service | 53 | 439 | HEALTHY | 5.2s |
| Salud BD | 54 | 440 | HEALTHY | 6.7s |
| Auto-remediar restart (DRY-RUN) | 56 | 441 | simulado | 15.5s |

**Recursos diagnosticados en tiempo real:**
- `aci-centralecopetrol` (1 vCPU/1.5 GB, Running, 0 restarts)
- `app-central-ecopetrol` (Running, availability Normal)
- `sqlserver-ecopetrol/ecopetroldb` (S2, Online)

El agente sintetiza todo en markdown estructurado para el operador.

---

# Patrón de seguridad — dry-run por defecto

Cada playbook invasivo **NO ejecuta nada** sin confirmación explícita.

| Modo | Qué hace | Cómo se invoca |
|---|---|---|
| **Dry-run** (default) | Lee estado actual, muestra la URL que SE llamaría, **no ejecuta** | `ansible-playbook talento-aci-restart.yml` |
| **Real** (explícito) | Ejecuta la acción destructiva + verifica estado después | `-e dry_run=false` |

```
DRY-RUN — NO se ejecutará restart real
Target: aci-centralecopetrol | Estado: Running (restartCount=0)
URL: POST .../containerGroups/aci-centralecopetrol/restart
→ Para ejecutar de verdad: -e dry_run=false
```

**Imposible que el agente actúe solo** — siempre hay confirmación humana. Card a Teams en ambos casos (DRY-RUN = amarilla, REAL = roja).

---

# Valor agregado — números concretos

| Métrica | Hoy | Con los 4 items + agente |
|---|---|---|
| MTTR típico por ticket de soporte | **30–60 min** | **30 seg – 2 min** |
| Tickets que el agente puede resolver solo | **~30%** (adivinando) | **~80%** (determinístico) |
| Capacidad de escala | Linear (cada ticket = 1 humano) | Sub-linear (1 agente = N tickets) |
| Trazabilidad audit / SOX | Manual, retrospectiva | Automática en `set_stats` por cada acción |
| Tiempo de implementación | — | **5–10 días-persona** total para los 4 items |

**Inversión vs retorno:** ~10 días-persona dejan al equipo de soporte trabajando con **2-3× la capacidad actual sin contratar gente**.

---

# Roadmap recomendado — prioridad por costo/impacto

| # | Item | Esfuerzo EAPPS | Impacto en el agente | Cuándo |
|---|---|---|---|---|
| 1 | **App Insights instrumentado** | 30 min (1 dep + 1 env var) | Alto — desbloquea AppRequests/Exceptions/Dependencies | Esta semana |
| 2 | **Correlation ID (Sleuth)** | 1 hora (1 dep) | Alto — habilita trazas end-to-end | Esta semana |
| 3 | **Logs JSON estructurados** | 2 horas (logback config) | Medio — mejora calidad pero hay alternativa parcial | Próxima semana |
| 4 | **Catálogo error codes** | 1-3 días (documentar) | Alto pero gradual — empezar con top 20 | Iterativo |

**Quick wins:** los 2 primeros (~1.5 h totales) ya generan **mejora visible** del agente.

---

# Lo que pedimos cerrar en esta reunión

Tres compromisos concretos:

1. **Quién** del equipo EAPPS queda como **interlocutor técnico** para esto (no diluir en "el equipo").

2. **Fecha tentativa** de activación de **Application Insights** específicamente.
   _Es el más fácil — si esto no se compromete, las demás son ilusorias._

3. **Próxima reunión técnica** (30 min) con el dev de TALENTO para mirar el `pom.xml` y diseñar las 2-3 líneas de cambio juntos.

> *"Estos 4 items son higiene operativa estándar para apps Spring Boot en producción. Con ellos, juntos llevamos TALENTO a un nivel de observabilidad que mañana cualquier equipo agradece. El agente que construimos amplifica el trabajo que ustedes ya hicieron."*

---

# Apéndice — qué ya está construido del lado nuestro

| Componente | Status |
|---|---|
| Agente IA Foundry → Log Analytics + AWX | Operativo |
| Dashboard web (11 escenarios accionables) | Operativo |
| 12 Job Templates en AWX (análisis + diagnóstico + remediación) | Creados |
| Auto-remediación dry-run + notificación Teams | Probado |
| Permisos Azure RBAC (`rol_custom_solution`) | Asignados |
| Probes empíricos del workspace (datos de este deck) | Ejecutados |

**Lo único que nos falta para escalar a producción real son los 4 items.** Todo lo demás está listo.
