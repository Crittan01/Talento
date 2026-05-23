# Guion del DEMO L1 para jefes (2-3 minutos)

## Objetivo de la sesión

Mostrar que tenemos un **agente operacional autónomo** para TALENTO que:
- Razona sobre preguntas de operación.
- Decide qué consultar.
- Se auto-corrige cuando una consulta falla.
- Entrega análisis estructurado en español.

## Setup previo (antes de entrar a la reunión)

1. Terminal abierta en `/Ansible/pruebas_locales/talento-ecopetrol`.
2. Confirmar `az login` activo: `az account show --output table` → debe mostrar `NTT DATA Colombia (IS)`.
3. (Opcional) Otra pestaña con el [portal de Foundry](https://ai.azure.com) abierta en el agente `talento-triage-agent` para mostrar versiones al final.

## Estructura del demo

### 1. Contexto (30 seg, verbal)

> "TALENTO opera 7x24, está bajo SOX, y hoy su soporte tarda en hacer RCA
> porque el conocimiento está fragmentado entre 4 empresas distintas
> (Asistia, Soportica, Talenia, Infraxis). Lo que vamos a mostrar es cómo
> un agente AI puede dar el primer nivel de análisis de incidentes en
> segundos, consumiendo los mismos logs que ya tenemos en Azure."

### 2. Demo en vivo (90 seg)

Correr en la terminal:

```bash
python3 bridge_l1.py
```

**Mientras carga (10 seg):** explicar visualmente lo que se ve:
- "El agente está en Azure AI Foundry, nosotros estamos local en WSL."
- "Le hacemos una pregunta operacional sobre errores recientes."

**Momentos clave a señalar:**

| Lo que aparece en pantalla | Lo que dices |
|---|---|
| `🤖 hop 1 → llama tool: query_log_analytics` con `union withsource=Tabla *` | "**El agente primero descubre qué tablas tienen datos.** No asume nada." |
| `4 filas` (resultado del descubrimiento) | "Encontró que ContainerInstanceLog_CL y ContainerEvent_CL son las que tienen tráfico en las últimas 24h." |
| `🤖 hop 2 → llama tool: query_log_analytics` con `getschema` | "Y antes de consultar, pide el esquema para no inventar columnas." |
| `🤖 hop 3 → llama tool` con query final (a veces 2 paralelas) | "Construye la KQL real. Si la pregunta es compleja, **pide múltiples tablas en paralelo**." |
| Respuesta final estructurada | "Hallazgo, hipótesis, diagnóstico, acción. En español. Listo para que un L2 actúe." |

### 3. Cierre (30 seg)

> "Lo que acabamos de ver es **L1** de 3 niveles. Hoy el agente consulta.
> En L2 (~1 día más de trabajo) le añadimos AWX como segunda herramienta:
> el agente no solo diagnostica, ejecuta el remedio. En L3 enchufamos un
> webhook desde Application Insights: el agente arranca solo cuando hay
> alerta, sin que un humano pregunte nada.
>
> Toda la infraestructura ya está en su sitio. El patrón es replicable
> para EasyGO (el otro caso del RFP) sin reinventar nada."

## Preguntas predefinidas (por si quieren más demo)

Las 3 preguntas siguen el mismo patrón: descubrimiento → getschema → query → síntesis. Datos validados:

| # | Pregunta | Hops | Tiempo aprox | Hallazgo del agente (validado) |
|---|---|---|---|---|
| 1 | Errores recientes (default) | 3 | ~15s | 1467 logs, errores Hibernate SQL, mensajes en blanco sin captura de excepciones |
| 2 | Container Instances | 3 (con calls paralelas) | ~20s | 10× "Authentication failed" en envío de correo, 6 BackOff, 6 Terminating exit-1 |
| 3 | Riesgo operativo + SOX | 3 (con calls paralelas) | ~35s | Excepciones Hibernate, conectividad BD Oracle, riesgo de continuidad de servicio |

Comandos rápidos:
```bash
python3 bridge_l1.py 1   # errores
python3 bridge_l1.py 2   # containers
python3 bridge_l1.py 3   # seguridad
```

O pregunta libre:
```bash
python3 bridge_l1.py "tu pregunta aquí"
```

## Preguntas que probablemente harán los jefes

| Pregunta | Respuesta corta |
|---|---|
| "¿Qué modelo usas?" | gpt-4o-mini en Global Standard, ~$0.15 por millón de tokens de input. Costo del demo: centavos por interacción. |
| "¿Quién entrenó al modelo con info de TALENTO?" | Nadie. El conocimiento operativo está en el **system prompt** + las consultas a los logs reales. Cambia solo editando el agente. |
| "¿Funciona si Log Analytics está vacío?" | El agente responde "no encontré datos" honestamente, no alucina. Probado. |
| "¿Por qué no usaste Copilot/X solución comercial?" | El agente vive en TU tenant. Datos no salen. Identidad es Managed Identity de tu suscripción. Costo controlado. |
| "¿Esto reemplaza al equipo de soporte?" | No. Acelera el L1 (diagnóstico inicial). Los L2/L3 humanos se enfocan en lo que realmente requiere intervención. |
| "¿Cómo se integra con AWX?" | L2: añadimos `run_awx_job` como segunda tool del agente. El agente decide qué playbook ejecutar. |

## Después del demo

Mostrar en el portal de Foundry:
1. Pestaña **Agentes** → `talento-triage-agent` → varias versiones listadas (cada `python3 bridge_l1.py` crea una nueva versión).
2. Click en la versión más reciente → mostrar la tool `query_log_analytics` registrada (visible aunque no se pueda editar desde portal).
3. Pestaña **Modelos + puntos de conexión** → `talento-gpt4o-mini` con estado Succeeded.

Eso cierra la narrativa: "no es magia, es infraestructura Azure desplegada en su tenant".
