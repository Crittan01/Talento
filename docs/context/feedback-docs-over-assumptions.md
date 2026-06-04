---
name: feedback-docs-over-assumptions
description: "Toda instrucción técnica al usuario debe basarse en documentación oficial citada, nunca en suposiciones, intuición o memoria entrenada"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 29bc6332-372a-456f-8211-b22061d864ec
---

Toda instrucción técnica que dé al usuario debe estar **respaldada por documentación oficial** del fabricante/proyecto correspondiente, no por suposiciones ni por memoria entrenada.

**Why:** Durante el proyecto talento-ecopetrol, al guiar el despliegue del modelo `gpt-4o-mini` en Azure AI Foundry, di pasos basados en mi conocimiento general (nombres de campos, valores de TPM, opciones de deployment) sin haber consultado Microsoft Learn. El usuario corrigió y pidió explícitamente: *"dame las instrucciones pero bajo la documentación oficial, no suposiciones, investiga"*. Eso evita errores en interfaces que cambian seguido (la UI de Foundry, Azure portal, etc.) y le da al usuario citas verificables que puede compartir con su equipo y con el cliente Ecopetrol.

**How to apply:** Antes de redactar pasos para cualquier procedimiento técnico (UI de Azure / AWX / AI Foundry / herramientas que cambian con frecuencia, APIs, configuraciones de productos, comandos de CLI), fetch la doc oficial con WebFetch sobre Microsoft Learn / docs del proyecto correspondiente. En la respuesta:

1. **Citar literalmente** los pasos clave entre comillas, preferiblemente con el texto original en inglés cuando aplique.
2. **Listar las fuentes** consultadas con URL al final.
3. **Marcar explícitamente** los campos/decisiones que la doc NO cubre y no inventar valores específicos — decir "el portal te ofrecerá un default, úsalo" en lugar de "pon 50K".
4. Si la doc oficial está en inglés y el UI del usuario en español, **traducir solo los nombres de botones/menús**, no las afirmaciones técnicas.
5. Si una URL del usuario es autenticada/privada (ej. ai.azure.com/nextgen/...), **decirlo y consultar la doc pública en su lugar** — no fingir que se accedió.

Esta regla aplica a todo el trabajo con [[talento-ecopetrol-rfp]] (Foundry, AWX, Log Analytics) y por defecto a cualquier proyecto futuro salvo que el usuario diga lo contrario.
