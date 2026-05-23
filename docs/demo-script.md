# Guión del DEMO L2 — talento-ecopetrol

**Audiencia**: jefes técnicos + gerencia de NTT (interna), luego cliente Ecopetrol.
**Duración**: 10-12 minutos (90s contexto + 4 escenarios de ~2 min + cierre).
**Objetivo**: demostrar que tenemos un agente AI operacional autónomo para
TALENTO que diagnostica, ejecuta automatización auditada y notifica al equipo.

---

## 0. Preparación previa (10 minutos antes de la reunión)

### Pre-checks técnicos

```bash
cd /Ansible/pruebas_locales/talento-ecopetrol

# 1. Verificar az login (debe estar como usuario ansible, no sudo)
az account show --output table
# Esperado: NTT DATA Colombia (IS), Subscription 7c5b032f-...

# 2. Conectividad AWX
curl -ks -o /dev/null -w "HTTP %{http_code}\n" https://192.168.250.20.nip.io/api/v2/ping/
# Esperado: HTTP 200

# 3. Conectividad Foundry (lanza un ciclo rápido sin setup)
python3 bridge_l2.py 3 --no-setup
# Esperado: ciclo termina en <30s con "successful"
```

Si los 3 pasan, está listo. Si alguno falla, NO entres a la reunión —
debugea primero.

### Pestañas a tener abiertas en el browser

1. **AWX UI**: `https://192.168.250.20.nip.io/#/jobs` filtrado por proyecto.
2. **Teams**: el canal donde llegan las adaptive cards.
3. **Foundry portal**: `https://ai.azure.com` → project `proj-foundry-is2` → agent `talento-triage-agent` (para mostrar versiones al final).
4. **Terminal**: `cd /Ansible/pruebas_locales/talento-ecopetrol` listo para teclear.

### Comando inicial recomendado

```bash
python3 bridge_l2.py 3 --no-setup
```

Lanza el smoke test (~5s) — confirma que todo conecta antes del demo real.
Si pasa, OK. Después borras el output con Ctrl+L y empiezas limpio.

---

## 1. Contexto verbal (90 segundos, mientras abres la terminal)

> "Lo que vamos a ver hoy responde directamente al caso técnico 4.1 del RFP
> de Ecopetrol — la parte que pide estrategia de monitoreo y de uso de
> inteligencia artificial para mejora continua sobre la solución TALENTO.
>
> TALENTO es la herramienta de talento humano de Ecopetrol — IaaS, 7x24,
> regulada por SOX. Su soporte hoy está fragmentado en 4 empresas distintas
> (Asistia, Soportica, Talenia, Infraxis). Cuando hay un incidente, el
> diagnóstico de primer nivel se demora porque cada empresa ve solo su
> pedazo.
>
> Lo que hicimos es montar un **agente AI en Azure AI Foundry — en el
> tenant de NTT DATA Colombia, no en uno externo — que diagnostica los
> mismos logs que ya tenemos en Azure, decide qué automatización ejecutar
> en AWX, y notifica al equipo en Teams. Todo en un solo ciclo, en
> segundos.
>
> Vamos a ver 4 preguntas reales que un L1 de soporte haría en su día a
> día. El agente decide solo qué herramienta usar, no es un menú scripted."

---

## 2. Los 4 escenarios en vivo

### Escenario 1 — Snapshot diagnóstico (≈2 min)

**La pregunta**: "¿Qué tenemos en el workspace de TALENTO ahora?"

**Comando**:
```bash
python3 bridge_l2.py 2 --no-setup
```

**Momentos clave a señalar**:

| En pantalla | Lo que dices |
|---|---|
| `🤖 hop 1 → llama tool: run_awx_job_template AWX template_id=48` | "Miren — el agente eligió ejecutar un Job Template en AWX, no responder de memoria. Decidió que necesita datos frescos." |
| `✓ AWX successful en X.Xs job_id=...` | "AWX ya corrió un playbook auditado en Git. Tenemos el job_id, podemos rastrearlo." |
| `🤖 hop 2 → llama tool: query_log_analytics` | "Y aquí el agente hace **cross-check** — no se queda solo con AWX, va directo a Log Analytics para validar. Comportamiento agentic, no scripted." |
| Síntesis final estructurada | "Hallazgo + Hipótesis + Diagnóstico + Acción. En español, técnico, listo para que un L2 lo accione." |

**Cambiar a Teams**: "Y mira el canal — la adaptive card recién llegó con
los hallazgos." Mostrar la card verde.

**Cambiar a AWX**: "Y aquí está el job en AWX — auditado, con su stdout,
quién lo lanzó, qué playbook corrió. Compliance happy."

---

### Escenario 2 — Análisis de errores críticos (≈2 min)

**La pregunta**: "¿Tenemos errores significativos en TALENTO?"

**Comando**:
```bash
python3 bridge_l2.py 4 --no-setup
```

**Momentos clave**:

| En pantalla | Lo que dices |
|---|---|
| `🤖 hop 1 → llama tool: run_awx_job_template template_id=49` | "Diferente pregunta, diferente tool. El agente eligió el **errors-analysis** específicamente, no el snapshot general." |
| `✓ AWX successful` | "Mismo patrón AWX — playbook auditado." |
| Síntesis: "114 errores, 77 warnings, audit_status CRITICAL" | "**Esto es real, no inventado**. Son logs reales de la app Spring Boot que está corriendo ahora mismo en `aci-centralecopetrol`. El agente no alucinó — consultó el dato." |
| Stack traces de Hibernate / SQL Server | "El agente identificó stack traces específicos de Hibernate al conectarse a SQL Server. Esto en una mesa de ayuda tradicional toma 30 minutos investigar." |

**Cambiar a Teams**: card **ROJA** con icono 🚨 "El equipo de soporte ya
está enterado del incidente, en su canal de operación, sin que un humano
haya escrito un correo."

---

### Escenario 3 — Auditoría SOX (≈2 min) ⭐ EL CIERRE

**La pregunta**: "TALENTO es regulado por SOX — auditen actividad de la última jornada".

**Comando**:
```bash
python3 bridge_l2.py 5 --no-setup
```

**Momentos clave** (este es el más importante por la palabra-clave del RFP):

| En pantalla | Lo que dices |
|---|---|
| `🤖 hop 1 → llama tool: run_awx_job_template template_id=50` | "**SOX audit**. Otra vez, el agente eligió la herramienta correcta — `talento-sox-audit`." |
| `audit_status: SECURITY_INCIDENT` | "Marcó automáticamente **SECURITY_INCIDENT**. Esto es lo que un auditor querría ver primero al abrir el reporte." |
| Logins de `nvivas` (11 REQUEST + 11 SUCCESS) | "Tracking por usuario. Nombres reales. 22 eventos de login. Y el agente puede decirme **quién** accedió, **cuántas veces**, **cuándo**." |
| 27 acciones privilegiadas | "Acciones con `rol=LIDER`: aprobaciones de día cumpleaños. Consultas masivas. Todo trazado. Para SOX, esto es oro." |
| 40 incidentes seguridad BD | "Y aquí lo crítico: 40 incidentes a nivel base de datos — failed logins de `sqlserver-ecopetrol-admin` con `ClientConnectionId` específicos. **Cada uno es trazable y auditable individualmente**." |

**Cambiar a Teams**: card **ROJA** con icono 🔐 "SOX Security Audit". "Esta
card va al canal del equipo de seguridad. Y este es el evento de auditoría
que el área de Cumplimiento de Ecopetrol va a buscar cuando audite."

**Frase de cierre del escenario**:
> "Lo que acabamos de ver en 25 segundos es lo que en muchas empresas
> toma 4 horas de un analista de seguridad. Y se puede ejecutar bajo demanda,
> programado, o disparado por una alerta. Esa es la pieza que cumple con
> el punto 9 del RFP — 'estrategia de uso de IA para mejora continua'."

---

### Escenario 4 — Pregunta libre (≈1-2 min) — improvisado

**Propósito**: demostrar que NO es scripted. El agente puede recibir cualquier
pregunta operativa.

**Sugeridas (elige una según el momento)**:

```bash
# Si los jefes quieren ver discriminación de containers
python3 bridge_l2.py "¿En qué container específico están concentrados los errores y qué porcentaje del total representa?" --no-setup

# Si quieren ver razonamiento sobre los logs reales
python3 bridge_l2.py "Dame los últimos 5 eventos de aprobación que se hicieron con rol LIDER, incluyendo qué se aprobó." --no-setup

# Si quieren ver análisis temporal
python3 bridge_l2.py "¿Qué hora del día es la más activa en TALENTO en las últimas 24h?" --no-setup
```

**Lo que dices**:
> "Esto no estaba en el guion. El agente decide qué KQL escribir y qué
> tabla consultar. Si la columna que asume no existe, pide el schema con
> `getschema` y se auto-corrige — esto lo vimos antes en construcción."

---

## 3. Cierre verbal (60 segundos)

> "En resumen, lo que tienen es:
>
> **Una pieza productiva-ready de automatización + agente AI** que:
> - Vive en el tenant de NTT (no en un servicio externo).
> - Usa modelos OpenAI desplegados en Foundry de Azure (gpt-4o-mini, centavos por interacción).
> - Tiene su propia Managed Identity (no compartimos credenciales).
> - Cada acción queda en AWX como Job auditado.
> - Notifica al equipo en Teams en tiempo real.
> - Extensible: añadir un nuevo escenario son ~30 minutos de trabajo (un
>   playbook + un job template + 5 líneas en el prompt del agente).
>
> Hoy demostramos 4 escenarios. Para Ecopetrol queremos llevar 8-10 que
> cubran los pain points específicos del documento — desde diagnóstico de
> lentitud en cierre de nómina hasta detección de cambios no autorizados
> en BD.
>
> Esto no es chat con tools. Es **agente operacional autónomo** integrado
> con el runtime de automatización que ya tenemos."

---

## 4. Preguntas anticipadas — y las respuestas

| Pregunta probable | Respuesta corta |
|---|---|
| ¿Cuánto cuesta operar esto al mes? | Modelo gpt-4o-mini en Global Standard: ~$0.15 USD por millón de tokens de input. Una interacción típica son ~3K tokens. **Estimado <$5 USD/mes** para uso operativo intensivo. AWX y Log Analytics ya están pagados aparte. |
| ¿Los datos salen del tenant? | **No**. Foundry vive en el tenant de NTT, Log Analytics también. Modelo se invoca en Azure US East 2 pero los inputs/outputs no se guardan ni se usan para entrenar (política Foundry). |
| ¿Quién entrenó al modelo con info de TALENTO? | **Nadie**. El conocimiento operativo de TALENTO está en el system prompt del agente (texto que editamos en código) + las consultas a los logs reales. **No hay fine-tuning**. Eso significa que si mañana cambia el modelo (de gpt-4o-mini a gpt-5), seguimos sirviendo en 1 click. |
| ¿Funciona si Log Analytics está vacío? | **Sí**, el agente responde "no encontré datos" honestamente. **Probado**: cuando el rango no devuelve nada, no alucina. |
| ¿Esto reemplaza al equipo de soporte? | **No**. Acelera el L1 (diagnóstico inicial) para que el L2/L3 humanos se enfoquen en lo que realmente requiere intervención. En el RFP, el caso 4.1 pide reducir el tiempo de RCA — esto lo ataca directo. |
| ¿Cómo se integra esto con el AWX que tiene Ecopetrol? | Igual que con este AWX local. El agente apunta al AWX que designemos. Cero código nuevo, solo apuntar a otra URL en config. |
| ¿Esto que vimos es producción? | **No es producción, es prototipo funcional**. El "bridge" Python que vemos correr en la terminal sería una Azure Function en producción (~5 horas de migración). La lógica es la misma. Lo hacemos así primero para iterar rápido y validar el patrón sin gastar tiempo de deploy. |
| ¿Y si la pregunta no encaja con ninguno de los 4 playbooks? | El agente puede **consultar Log Analytics directamente** con KQL improvisada (es la herramienta 1, `query_log_analytics`). Solo si necesita una acción concreta (snapshot, audit, restart, etc.) usa AWX. Ambas son tools registradas, decide caso a caso. |
| ¿Qué pasa si el cliente quiere agregar 50 escenarios más? | **Patrón replicable**: 1 playbook nuevo + 1 Job Template en AWX + 5 líneas en el prompt. ~30 min cada uno. Se factura por escenario implementado. |
| ¿Esto se conecta con Teams del cliente o con el nuestro? | Configurable. Hoy notifica al canal que el RFP designe. Soporta Incoming Webhooks y Workflows (Power Automate). |
| ¿Hay riesgo de que el agente ejecute algo destructivo? | Hoy todos los playbooks son **read-only** (snapshots, queries, audit). Cuando agreguemos remediaciones invasivas (restart container, scale up, revocar acceso), van con: (a) confirmación humana por defecto, (b) lista blanca de acciones permitidas, (c) auditoría completa en AWX. |
| ¿Por qué Foundry y no OpenAI directo? | Foundry da: agentes versionados, Managed Identity por agente, tool catalog managed (Azure Functions, Logic Apps, MCP), tracing integrado, publishing a Teams/M365 Copilot. Sin Foundry tendríamos que construir cada una de esas capas. |

---

## 5. Después del demo — mostrar el portal de Foundry (opcional, +60s)

Si los jefes quieren ver "la cocina":

1. Abrir [https://ai.azure.com](https://ai.azure.com) en pestaña.
2. Project `proj-foundry-is2` → menú lateral **Agentes**.
3. Click en `talento-triage-agent`.
4. Mostrar lista de versiones (8+ ahora). Decir: "Cada cambio queda
   snapshotted. Si una versión nueva degrada, rollback inmediato."
5. Abrir la versión más reciente. Mostrar las 2 tools registradas.
6. **Modelos + puntos de conexión**: mostrar `talento-gpt4o-mini` con
   estado Succeeded, en Global Standard, US East 2.
7. (Si hay tiempo) abrir la pestaña de **Trazado** del agente — Foundry
   guarda cada decisión, cada tool call, cada respuesta. **Eso es lo que
   un Compliance Officer querrá ver**.

---

## 6. Estado del repositorio (para si preguntan dónde está el código)

- **Repo**: `https://github.com/Crittan01/Talento` branch `develop`
- **Commits**: 8+ commits limpios, ningún secret en historia
- **Files**:
  - `bridge_l1.py` — versión inicial (solo Log Analytics)
  - `bridge_l2.py` — versión final (Log Analytics + AWX)
  - `playbooks/talento-workspace-snapshot.yml`
  - `playbooks/talento-errors-analysis.yml`
  - `playbooks/talento-sox-audit.yml`
  - `README.md`, `docs/demo-script.md`
- **AWX**: 4 Job Templates registrados, URL `https://192.168.250.20.nip.io`
- **Foundry**: project `proj-foundry-is2` en `aifoundry-is2` (rg-central-is2)

---

## 7. Roadmap inmediato post-demo (para el cierre con gerencia)

| Pieza | Esfuerzo | Cuándo |
|---|---|---|
| Migrar bridge Python → Azure Function | 5h | Para demo a cliente |
| Pedir rol Container Instance Contributor al admin Azure | (no nuestro) | Antes de demos invasivos |
| Añadir 4-5 escenarios más según pain points específicos del RFP | 4-6h | Antes de demo a cliente |
| Webhook automático: alerta App Insights → agente | 1 día | Después de demo |
| Publicar agente con endpoint estable + bot Teams | 2 días | Para integración con mesa de ayuda |

---

## Checklist final antes de entrar a la reunión

- [ ] `az account show` muestra NTT DATA Colombia (IS)
- [ ] Terminal en `/Ansible/pruebas_locales/talento-ecopetrol`
- [ ] Browser con AWX UI, Teams, Foundry portal abiertos
- [ ] `python3 bridge_l2.py 3 --no-setup` corrió OK en pre-check
- [ ] Pantalla limpia (Ctrl+L) antes de empezar
- [ ] Internet estable (Foundry requiere conectividad continua)
