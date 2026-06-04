---
name: cm02-replicacion-logs-sura
description: "Caso de uso SURA/NTT cm02 — replicación de logs modo PULL con Ansible/AAP; arquitectura, mecanismo de credencial Vault y hallazgos abiertos pendientes de necesidad del usuario"
metadata: 
  node_type: memory
  type: project
  originSessionId: f115187f-6428-4a72-99a7-217b48806343
---

Proyecto `cm02-ansible-replicacion-logs` en `/Ansible/sura/1-automatizaciones-ntt-ansible-app-server-conf/`. Centraliza logs en **modo PULL**: `inmdeapplog.suramericana.com.co` jala vía rsync+SSH desde ~116 servidores WebLogic/WebSphere a `/syslog/logs/`. Usuario SSH `usersync`. Corre en **AAP** como 4 Job Templates (DESARROLLO+WebSphere, LABORATORIO, PRODUCCION_SALUD, PRODUCCION_SEGUROS) cada 40 min. 7 plays en `playbooks/rsync-logs-pull.yaml`; roles `log_sync_pull` y `log_sync_report`; 14 templates rsync en `group_vars/all.yml`; 116 `host_vars/` (217 directorios); genera reporte HTML email + Excel.

**Mecanismo de credencial (confirmado por usuario):** la llave `privkey.usersync` está cifrada con ansible-vault. AAP inyecta una **Credencial tipo Vault** del usuario `usersync` que aporta el password; el Play 1 la copia con `decrypt: true` a `/tmp/key_tmp_pull`. Si falta esa credencial, Play 1 falla en el copy/decrypt.

**Hallazgos abiertos (de mi análisis, a confirmar con el usuario):**
1. 🔴 `inventory/app_server_inventory_dns` CORRUPTO (bytes NUL en línea 1, sin grupos, sin inmdeapplog, solo 15/116 hosts) — pero README/Plan_Operativo dicen usarlo. El bueno es `inventory/app_server_inventory`. Generado por `scripts/inventario_dns.sh` que abortó a medias.
2. 🟠 Template `weblogic_logs` (82/217 usos) filtra `--include='WLS_*_yyyy-MM-dd-hh-mm.log'`: en rsync es glob literal, no formato de fecha → posiblemente no casa archivos reales. Verificar contra nombres reales y salida rsync.
3. 🟠 `extra_options` del host se agregan DESPUÉS de `--exclude='*'` del template → quedan sombreados (en rsync gana la primera regla que casa).
4. 🟡 rsync task tiene `retries`/`delay` sin `until:` y con `failed_when: false` → reintentos NO se ejecutan.
5. 🟡 `.gitignore` ignora `roles/log_sync/files/ssh` pero la llave está en `roles/log_sync_pull/files/ssh` (ruta no casa); mitigado por vault.
6. 🟡 Excel/email muestran `failed_pull_count`/`failed_push_count` que el modo PULL nunca puebla (residuo del diseño push/pull).

**Estado:** usuario confirmó contexto; expondrá la "necesidad" concreta en la siguiente conversación. Relacionado: [[talento-ecopetrol-rfp]] (otro frente NTT). Aplicar [[feedback-docs-over-assumptions]] al tocar rsync/AAP UI.
