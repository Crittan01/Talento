#!/usr/bin/env python3
"""
probe-aci-permissions.py — verifica que puede y no puede hacer el Service
Principal actual sobre Azure Container Instances y App Service en
rg-central-solucion-talento. NO ejecuta acciones destructivas: solo lee
estado y enumera permisos efectivos via Microsoft.Authorization/permissions.

Salida: docs/aci-permissions-report.md con cross-check de acciones
necesarias para auto-remediacion + recomendacion de rol a pedir.

Uso:
  python3 scripts/probe-aci-permissions.py
"""

import json
from fnmatch import fnmatch
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OUT_PATH = ROOT / "docs" / "aci-permissions-report.md"

RESOURCE_GROUP = "rg-central-solucion-talento"


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_PATH)
TENANT = ENV["AZURE_TENANT_ID"]
CLIENT = ENV["AZURE_CLIENT_ID"]
SECRET = ENV["AZURE_CLIENT_SECRET"]
SUBSCRIPTION = ENV["AZURE_SUBSCRIPTION_ID"]


# Acciones necesarias para auto-remediacion, agrupadas por nivel
REQUIRED_ACTIONS = [
    # (action, level, descr)
    ("Microsoft.ContainerInstance/containerGroups/read",
     "1-container", "Leer estado/config del container"),
    ("Microsoft.ContainerInstance/containerGroups/restart/action",
     "1-container", "Reiniciar container (REMEDIACION)"),
    ("Microsoft.ContainerInstance/containerGroups/stop/action",
     "1-container", "Detener container (REMEDIACION)"),
    ("Microsoft.ContainerInstance/containerGroups/start/action",
     "1-container", "Iniciar container (REMEDIACION)"),
    ("Microsoft.ContainerInstance/containerGroups/containers/logs/action",
     "1-container", "Leer logs en vivo del container"),
    ("Microsoft.Web/sites/read",
     "1-appservice", "Leer estado del App Service"),
    ("Microsoft.Web/sites/restart/action",
     "1-appservice", "Reiniciar App Service (REMEDIACION)"),
    ("Microsoft.Sql/servers/read",
     "2-sql", "Leer estado del SQL Server"),
    ("Microsoft.Sql/servers/databases/read",
     "2-sql", "Leer estado de la base de datos"),
    ("Microsoft.OperationalInsights/workspaces/read",
     "0-baseline", "Leer Log Analytics workspace (baseline)"),
    ("Microsoft.OperationalInsights/workspaces/query/action",
     "0-baseline", "Ejecutar KQL queries (baseline)"),
]


def get_arm_token() -> str:
    """OAuth2 token para Azure Resource Manager (management.azure.com)."""
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT,
            "client_secret": SECRET,
            "resource": "https://management.azure.com/",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def arm_get(url: str, headers: dict, timeout: int = 30) -> requests.Response:
    return requests.get(url, headers=headers, timeout=timeout)


def is_action_allowed(action: str, allowed_patterns: list, denied_patterns: list) -> bool:
    """Match an action against Azure RBAC wildcard patterns."""
    matched = False
    for pattern in allowed_patterns:
        if fnmatch(action, pattern):
            matched = True
            break
    if not matched:
        return False
    for npattern in denied_patterns:
        if fnmatch(action, npattern):
            return False
    return True


def main():
    print("=" * 72)
    print("PROBE - Permisos del Service Principal para auto-remediacion")
    print("=" * 72)
    print(f"  Subscription:  {SUBSCRIPTION}")
    print(f"  Resource Group: {RESOURCE_GROUP}")
    print(f"  Client ID:     {CLIENT[:8]}...{CLIENT[-4:]}")
    print()

    try:
        token = get_arm_token()
    except Exception as e:
        print(f"  X No se pudo obtener token ARM: {e}")
        return 1
    headers = {"Authorization": f"Bearer {token}"}
    print("  + Token ARM obtenido correctamente")
    print()

    # ------------------------------------------------------------------
    # Test 1 - Listar container groups en el RG (confirma read)
    # ------------------------------------------------------------------
    print("[1/4] Listar Container Instances en el RG...")
    url_list_aci = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.ContainerInstance/containerGroups"
        f"?api-version=2023-05-01"
    )
    r = arm_get(url_list_aci, headers)
    can_list_aci = False
    aci_names = []
    aci_states = {}
    if r.status_code == 200:
        items = r.json().get("value", [])
        can_list_aci = True
        for c in items:
            name = c["name"]
            aci_names.append(name)
            state = (c.get("properties", {})
                     .get("instanceView", {})
                     .get("state")) or "?"
            aci_states[name] = state
        print(f"  + OK ({r.status_code}) - {len(aci_names)} container(s): {aci_names}")
        for n, s in aci_states.items():
            print(f"      - {n}: state={s}")
    elif r.status_code == 403:
        print(f"  X FORBIDDEN ({r.status_code}) - el SP no puede listar containers")
    else:
        print(f"  ! Inesperado ({r.status_code}): {r.text[:200]}")
    print()

    # ------------------------------------------------------------------
    # Test 2 - Listar App Services en el RG
    # ------------------------------------------------------------------
    print("[2/4] Listar App Services en el RG...")
    url_list_web = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.Web/sites"
        f"?api-version=2023-12-01"
    )
    r = arm_get(url_list_web, headers)
    can_list_web = False
    web_names = []
    if r.status_code == 200:
        items = r.json().get("value", [])
        can_list_web = True
        web_names = [s["name"] for s in items]
        print(f"  + OK ({r.status_code}) - {len(web_names)} App Service(s): {web_names}")
    elif r.status_code == 403:
        print(f"  X FORBIDDEN ({r.status_code}) - el SP no puede listar App Services")
    else:
        print(f"  ! Inesperado ({r.status_code}): {r.text[:200]}")
    print()

    # ------------------------------------------------------------------
    # Test 3 - Enumerar permisos efectivos en el RG (READ-ONLY, no destructivo)
    # ------------------------------------------------------------------
    print("[3/4] Enumerar permisos efectivos en el RG...")
    url_perms = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.Authorization/permissions"
        f"?api-version=2022-04-01"
    )
    r = arm_get(url_perms, headers)
    actions_allowed = []
    actions_denied = []
    data_actions_allowed = []
    data_actions_denied = []
    if r.status_code == 200:
        for perm in r.json().get("value", []):
            actions_allowed.extend(perm.get("actions", []))
            actions_denied.extend(perm.get("notActions", []))
            data_actions_allowed.extend(perm.get("dataActions", []))
            data_actions_denied.extend(perm.get("notDataActions", []))
        print(f"  + OK ({r.status_code}) - {len(actions_allowed)} action pattern(s), "
              f"{len(actions_denied)} excluida(s), {len(data_actions_allowed)} dataAction(s)")
        if actions_allowed:
            print(f"      patterns: {actions_allowed[:5]}{'...' if len(actions_allowed) > 5 else ''}")
    else:
        print(f"  ! No se pudo enumerar permisos ({r.status_code}): {r.text[:200]}")
    print()

    # ------------------------------------------------------------------
    # Test 4 - Cross-check contra acciones requeridas
    # ------------------------------------------------------------------
    print("[4/4] Cross-check de acciones necesarias...")
    print()
    results = []
    for action, level, descr in REQUIRED_ACTIONS:
        allowed = is_action_allowed(action, actions_allowed, actions_denied)
        results.append((action, level, descr, allowed))
        icon = "+" if allowed else "-"
        short = "/".join(action.split("/")[-2:])
        print(f"  [{icon}] {level:14}  {short:42}  {descr}")
    print()

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------
    print("=" * 72)
    print("RESUMEN")
    print("=" * 72)
    levels = {"0-baseline", "1-container", "1-appservice", "2-sql"}
    for lvl in sorted(levels):
        lvl_results = [r for r in results if r[1] == lvl]
        ok = sum(1 for r in lvl_results if r[3])
        total = len(lvl_results)
        status = "completa" if ok == total else ("parcial" if ok > 0 else "BLOQUEADA")
        print(f"  Nivel {lvl}: {ok}/{total} acciones permitidas - {status}")
    print()

    missing = [r for r in results if not r[3]]
    if not missing:
        print("  ==> El SP YA tiene todos los permisos. NO hace falta escalar al admin.")
    else:
        print(f"  ==> Faltan {len(missing)} permisos. Hay que pedir al admin de Azure.")
    print()

    # ------------------------------------------------------------------
    # Generar reporte markdown
    # ------------------------------------------------------------------
    write_report(
        OUT_PATH,
        can_list_aci, aci_names, aci_states,
        can_list_web, web_names,
        actions_allowed, actions_denied,
        results,
    )
    print(f"Reporte: {OUT_PATH}")
    return 0


def write_report(path, can_list_aci, aci_names, aci_states,
                 can_list_web, web_names,
                 actions_allowed, actions_denied, results):
    lines = []
    lines.append("# Reporte — Permisos del Service Principal para auto-remediacion")
    lines.append("")
    lines.append("_Generado por `scripts/probe-aci-permissions.py` (READ-ONLY)._")
    lines.append("")
    lines.append(f"- **Subscription**: `{SUBSCRIPTION}`")
    lines.append(f"- **Resource Group**: `{RESOURCE_GROUP}`")
    lines.append(f"- **Service Principal (Client ID)**: `{CLIENT}`")
    lines.append("")

    # Inventario observable
    lines.append("## 1. Recursos visibles desde el SP")
    lines.append("")
    lines.append("### Container Instances")
    if can_list_aci:
        if aci_names:
            lines.append("| Nombre | Estado |")
            lines.append("|---|---|")
            for n in aci_names:
                lines.append(f"| `{n}` | `{aci_states.get(n, '?')}` |")
        else:
            lines.append("_(no hay container groups en este RG)_")
    else:
        lines.append("X **El SP no puede listar containers en el RG** — falta `Microsoft.ContainerInstance/containerGroups/read`.")
    lines.append("")
    lines.append("### App Services")
    if can_list_web:
        if web_names:
            lines.append("| Nombre |")
            lines.append("|---|")
            for n in web_names:
                lines.append(f"| `{n}` |")
        else:
            lines.append("_(no hay App Services en este RG)_")
    else:
        lines.append("X **El SP no puede listar App Services en el RG** — falta `Microsoft.Web/sites/read`.")
    lines.append("")

    # Cross-check
    lines.append("## 2. Cross-check de acciones necesarias para auto-remediacion")
    lines.append("")
    lines.append("| Nivel | Accion | Proposito | Permitido |")
    lines.append("|---|---|---|---|")
    for action, level, descr, allowed in results:
        icon = "OK" if allowed else "FALTA"
        lines.append(f"| {level} | `{action}` | {descr} | **{icon}** |")
    lines.append("")

    # Permisos efectivos (para auditoria)
    lines.append("## 3. Permisos efectivos enumerados")
    lines.append("")
    lines.append(f"El SP tiene {len(actions_allowed)} patron(es) de acciones permitidas en este RG:")
    lines.append("")
    if actions_allowed:
        lines.append("```")
        for p in sorted(set(actions_allowed)):
            lines.append(p)
        lines.append("```")
    else:
        lines.append("_(ninguno enumerable via API)_")
    if actions_denied:
        lines.append("")
        lines.append(f"Y {len(actions_denied)} patron(es) excluidas (notActions):")
        lines.append("")
        lines.append("```")
        for p in sorted(set(actions_denied)):
            lines.append(p)
        lines.append("```")
    lines.append("")

    # Recomendacion
    lines.append("## 4. Recomendacion: que pedir al admin de Azure")
    lines.append("")
    missing = [r for r in results if not r[3]]
    if not missing:
        lines.append("**No hace falta escalar.** El SP ya tiene todos los permisos necesarios.")
    else:
        lines.append(f"Faltan **{len(missing)} permisos** para cubrir el alcance completo.")
        lines.append("")
        lines.append("### Opcion A - rol built-in (rapido)")
        lines.append("")
        lines.append(f"Asignar `Contributor` al SP sobre `{RESOURCE_GROUP}`:")
        lines.append("")
        lines.append("```bash")
        lines.append("az role assignment create \\")
        lines.append(f"  --assignee {CLIENT} \\")
        lines.append("  --role Contributor \\")
        lines.append(f"  --scope /subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}")
        lines.append("```")
        lines.append("")
        lines.append("Pros: 1 click en portal o un comando az. Cons: amplio (incluye delete, write de todo).")
        lines.append("")
        lines.append("### Opcion B - custom role (restrictivo, recomendado)")
        lines.append("")
        lines.append("Crear `TalentoAutoRemediator` solo con las acciones faltantes:")
        lines.append("")
        lines.append("```json")
        lines.append("{")
        lines.append('  "Name": "TalentoAutoRemediator",')
        lines.append('  "Description": "Permisos minimos para auto-remediacion del agente IA de TALENTO",')
        lines.append(f'  "AssignableScopes": ["/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"],')
        lines.append('  "Actions": [')
        for i, (action, _, _, _) in enumerate(missing):
            sep = "," if i < len(missing) - 1 else ""
            lines.append(f'    "{action}"{sep}')
        lines.append('  ],')
        lines.append('  "NotActions": [],')
        lines.append('  "DataActions": [],')
        lines.append('  "NotDataActions": []')
        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("Crear y asignar:")
        lines.append("")
        lines.append("```bash")
        lines.append("az role definition create --role-definition role.json")
        lines.append("az role assignment create \\")
        lines.append(f"  --assignee {CLIENT} \\")
        lines.append('  --role "TalentoAutoRemediator" \\')
        lines.append(f"  --scope /subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}")
        lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Re-ejecutar `python3 scripts/probe-aci-permissions.py` despues de que el admin asigne el rol para confirmar._")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
