# Catálogo de Códigos de Error TALENTO

Este documento contiene los códigos de error formales que emite la aplicación
TALENTO en sus logs estructurados (campo `error_code` o aparición textual del
código en el campo `message`). El agente IA debe consultar este catálogo cuando
identifique cualquier código `TLNT-XXX` para entregar al usuario una explicación
oficial y una acción concreta.

**Versión:** v2 — 15 códigos
**Fuente:** EAPPS / equipo de desarrollo TALENTO
**Última actualización:** 2026-06-02

---

## TLNT-001 — USUARIO_NO_ENCONTRADO

- **Descripción:** Usuario no encontrado en el directorio.
- **Módulo origen:** Autenticación / Login.
- **Solución para usuario final:** Verifique usuario o cámbielo.
- **Acción para soporte / agente:** Validar si el `userId` existe en la tabla
  `usuarios` y si está activo. Si no existe, revisar la sincronización con
  Active Directory (último ciclo de sync de AD).
- **Severidad típica:** WARN.
- **Frecuencia esperada:** alta (errores comunes de tipeo de usuarios).

---

## TLNT-002 — CREDENCIALES_INVALIDAS

- **Descripción:** Credenciales inválidas.
- **Módulo origen:** Autenticación / Login.
- **Solución para usuario final:** Revise usuario y contraseña.
- **Acción para soporte / agente:** Validar que el usuario no esté bloqueado
  (ver TLNT-009/010) antes de asumir error de tipeo. Si reincide con el mismo
  usuario, considerar TLNT-011 (intentos excedidos).
- **Severidad típica:** WARN.
- **Frecuencia esperada:** media-alta.

---

## TLNT-003 — PERMISO_DENEGADO

- **Descripción:** Permiso denegado para ejecutar la acción solicitada.
- **Módulo origen:** Autorización (post-login, validación de rol).
- **Solución para usuario final:** Solicite acceso a su líder.
- **Acción para soporte / agente:** Validar el rol del usuario en Active
  Directory contra el rol requerido por el endpoint. Caso típico: usuario
  intenta aprobar vacaciones sin rol `LIDER`.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** media.

---

## TLNT-004 — LOGIN_FALLIDO

- **Descripción:** Falta de campos requeridos para login (form incompleto).
- **Módulo origen:** Autenticación / Login.
- **Solución para usuario final:** Revisa los campos enviados al login.
- **Acción para soporte / agente:** Revisar payload del request — puede
  indicar problema en el frontend (campos no enviados) o ataque de fuzzing.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** baja (en uso normal).

---

## TLNT-005 — SIN_DIAS_SUFI

- **Descripción:** Usuario solicita días pero no tiene saldo suficiente.
- **Módulo origen:** Vacaciones / días de cumpleaños / calamidades.
- **Solución para usuario final:** Consulte su saldo de días.
- **Acción para soporte / agente:** Validar saldo del usuario consultando
  el módulo de saldo. Si el usuario insiste y considera que tiene días,
  verificar que el sync con nómina haya actualizado el saldo recientemente.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** media.

---

## TLNT-006 — VALIDACION_INTERRUP

- **Descripción:** Validación interrumpida (timeout, conexión, etc.).
- **Módulo origen:** Validaciones generales contra sistemas externos
  (SAP, SuccessFactors, AD).
- **Solución para usuario final:** Reintente la operación.
- **Acción para soporte / agente:** Probablemente error transitorio. Si
  recurre, revisar disponibilidad de los sistemas externos involucrados.
  Verificar logs por `correlation_id` para ver dónde se cortó.
- **Severidad típica:** WARN o ERROR según contexto.
- **Frecuencia esperada:** baja (depende salud de integraciones).

---

## TLNT-007 — ERROR_VALIDACION

- **Descripción:** Error inesperado en validación (excepción no controlada).
- **Módulo origen:** Cualquier validación.
- **Solución para usuario final:** Reporte al soporte.
- **Acción para soporte / agente:** Buscar el `correlation_id` en logs para
  ver el stack trace asociado. Probablemente requiere intervención de EAPPS
  (bug en código). Severidad alta.
- **Severidad típica:** ERROR.
- **Frecuencia esperada:** baja.

---

## TLNT-008 — PASSWORD_INCORRECTA

- **Descripción:** Contraseña incorrecta.
- **Módulo origen:** Autenticación / Login.
- **Solución para usuario final:** Verifique su contraseña o reinicie
  si la olvidó.
- **Acción para soporte / agente:** Si el mismo usuario repite varias veces
  → posible brute force, considerar bloqueo preventivo (TLNT-009/010/011).
- **Severidad típica:** WARN.
- **Frecuencia esperada:** alta.

---

## TLNT-009 — USUARIO_BLOQUEADO

- **Descripción:** Usuario bloqueado temporalmente (por intentos fallidos
  u otra política).
- **Módulo origen:** Autenticación / política de seguridad.
- **Solución para usuario final:** Espere el tiempo indicado o contacte
  a soporte si persiste.
- **Acción para soporte / agente:** Validar política de bloqueo (tiempo,
  causa). Si el usuario afirma que no debería estar bloqueado, revisar logs
  por `correlation_id` para ver qué disparó el bloqueo.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** baja-media.

---

## TLNT-010 — USUARIO_BLOQUEADO_PERMANENTE

- **Descripción:** Usuario bloqueado permanentemente.
- **Módulo origen:** Política de seguridad / Compliance.
- **Solución para usuario final:** Contacte a soporte para desbloqueo.
- **Acción para soporte / agente:** Requiere intervención humana — validar
  con seguridad / compliance la causa del bloqueo permanente antes de
  desbloquear. NO desbloquear automáticamente.
- **Severidad típica:** ERROR.
- **Frecuencia esperada:** muy baja.

---

## TLNT-011 — INTENTOS_EXCEDIDOS

- **Descripción:** Intentos de login excedidos en ventana corta.
- **Módulo origen:** Autenticación / política anti-brute-force.
- **Solución para usuario final:** Espere unos minutos e intente nuevamente.
- **Acción para soporte / agente:** Posible indicador de brute force.
  Validar IP origen + patrón temporal. Si es ataque real, considerar
  bloquear IP en NSG (acción de remediación).
- **Severidad típica:** WARN o ERROR si patrón sostenido.
- **Frecuencia esperada:** baja en uso normal, picos en ataques.

---

## TLNT-012 — CALAMIDAD_NO_ENCONTRADA

- **Descripción:** Calamidad no encontrada por el identificador dado.
- **Módulo origen:** Módulo de Calamidades.
- **Solución para usuario final:** Verifique el identificador de la calamidad.
- **Acción para soporte / agente:** Validar que el ID existe en la tabla
  `calamidades` y que pertenece al usuario. Si fue eliminada recientemente,
  revisar logs de auditoría.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** baja.

---

## TLNT-013 — INCAPACIDAD_NO_ENCONTRADA

- **Descripción:** Incapacidad no encontrada por el identificador dado.
- **Módulo origen:** Módulo de Incapacidades.
- **Solución para usuario final:** Verifique el identificador de la incapacidad.
- **Acción para soporte / agente:** Similar a TLNT-012 pero sobre tabla
  `incapacidades`.
- **Severidad típica:** WARN.
- **Frecuencia esperada:** baja.

---

## TLNT-014 — VACACIONES_NO_ENCONTRADAS

- **Descripción:** Registro de vacaciones no encontrado.
- **Módulo origen:** Módulo de Vacaciones.
- **Solución para usuario final:** Verifique el identificador del registro
  de vacaciones.
- **Acción para soporte / agente:** Validar ID en tabla `vacaciones`. Si la
  solicitud fue aprobada y enviada a nómina recientemente, puede haber
  desfase (consultar logs `Solicitud VACACIONES ID X enviada a nómina`).
- **Severidad típica:** WARN.
- **Frecuencia esperada:** baja-media.

---

## TLNT-015 — ERROR_CREAR_SOLICITUD

- **Descripción:** Error al crear la solicitud (cualquier tipo).
- **Módulo origen:** Cualquier módulo que cree solicitudes (vacaciones,
  calamidades, días de cumpleaños, etc.).
- **Solución para usuario final:** Revise los datos enviados e intente
  nuevamente.
- **Acción para soporte / agente:** Buscar `correlation_id` del request
  para ver el stack trace + payload. Causas típicas: validación de
  negocio, FK inválida, error en módulo destino. Puede requerir EAPPS si
  recurre.
- **Severidad típica:** ERROR.
- **Frecuencia esperada:** baja.

---

## Cómo usar este catálogo (instrucción para el agente)

Cuando identifiques un código `TLNT-XXX` en los logs:

1. **Busca el código en este documento** vía `file_search`.
2. **Cita textualmente la descripción y la solución para usuario final** cuando respondas al operador.
3. **Aplica la "Acción para soporte / agente"** como guía para decidir si
   ejecutar tools adicionales (`query_log_analytics` con el `correlation_id`,
   `run_awx_job_template` para remediación, etc.).
4. **Si el código aparece con frecuencia anormal** (ej. TLNT-011 muchas
   veces en pocos minutos desde mismas IPs), considéralo señal de ataque
   y propone acción.

## Códigos no listados

Si encuentras un código `TLNT-XXX` que no está en este catálogo, **indícalo
explícitamente al usuario** ("código no documentado en el catálogo actual")
y solicítale validar con EAPPS la definición. No inventes significados.
