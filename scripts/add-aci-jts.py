#!/usr/bin/env python3
"""
add-aci-jts.py — agrega los 8 Job Templates de auto-remediacion al AWX
indicado por AWX_URL/AWX_TOKEN. Idempotente: si un JT ya existe lo deja.

Hace:
  1. Encuentra el project 'talento-automation-source' (o lo busca por name).
  2. Dispara un re-sync para que jale los playbooks nuevos del repo.
  3. Crea (o reutiliza) un Inventory 'talento-localhost' con host=localhost.
  4. Crea los 8 JTs nuevos:
     - 4 diagnostico: aci-state, appservice-state, sql-health, full-health-check
     - 4 remediacion: aci-restart, aci-stop, aci-start, appservice-restart
  5. Imprime al final un mapeo JT_NAME -> JT_ID para actualizar .env.

Uso:
  AWX_URL=https://192.168.250.20.nip.io \
  AWX_TOKEN=xxx \
    python3 scripts/add-aci-jts.py
"""

import json
import os
import sys
import time
import urllib3
from typing import Optional

import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AWX_URL = os.environ["AWX_URL"].rstrip("/")
AWX_TOKEN = os.environ["AWX_TOKEN"]
ORG_NAME = "Ecopetrol"
PROJECT_NAME = "talento-automation-source"
INVENTORY_NAME = "talento-localhost"
PLAYBOOK_DIR = "playbooks"

# (jt_name, playbook_file, description, is_invasive)
PLAYBOOKS = [
    # Diagnosticos
    ("talento-aci-state",            "talento-aci-state.yml",
     "Diagnostico ACI: estado + restartCount + eventos recientes", False),
    ("talento-appservice-state",     "talento-appservice-state.yml",
     "Diagnostico App Service: estado + availability + host", False),
    ("talento-sql-health",           "talento-sql-health.yml",
     "Diagnostico SQL: estado server + databases + tier", False),
    ("talento-full-health-check",   "talento-full-health-check.yml",
     "Orchestrator: salud completa de ACI + App Service + SQL + recomendacion", False),
    # Remediaciones (dry_run=true por defecto)
    ("talento-aci-restart",          "talento-aci-restart.yml",
     "REMEDIACION: reinicia container ACI (dry_run=true por defecto, pasar dry_run=false para ejecutar)", True),
    ("talento-aci-stop",             "talento-aci-stop.yml",
     "REMEDIACION: detiene container ACI (dry_run=true)", True),
    ("talento-aci-start",            "talento-aci-start.yml",
     "REMEDIACION: inicia container ACI (dry_run=true)", True),
    ("talento-appservice-restart",   "talento-appservice-restart.yml",
     "REMEDIACION: reinicia App Service (dry_run=true)", True),
]

H = {"Authorization": f"Bearer {AWX_TOKEN}", "Content-Type": "application/json"}


def api_get(path, **params):
    r = requests.get(f"{AWX_URL}{path}", headers=H, params=params, verify=False, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, body):
    r = requests.post(f"{AWX_URL}{path}", headers=H, json=body, verify=False, timeout=30)
    if r.status_code not in (200, 201, 202):
        print(f"  ! POST {path} HTTP {r.status_code} body={r.text[:300]}")
        r.raise_for_status()
    return r.json() if r.text else {}


def find_by_name(path, name) -> Optional[dict]:
    d = api_get(path, name=name)
    for r in d.get("results", []):
        if r["name"] == name:
            return r
    return None


def wait_for_sync(project_id: int, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = api_get(f"/api/v2/projects/{project_id}/")
        status = d.get("status")
        if status == "successful":
            return True
        if status in ("failed", "error", "canceled"):
            print(f"  ! Sync status={status}")
            return False
        print(f"     ...status={status}, esperando 3s")
        time.sleep(3)
    return False


def main():
    print("=" * 72)
    print("ADD ACI Job Templates al AWX")
    print("=" * 72)
    print(f"  AWX URL: {AWX_URL}")
    print()

    # Org
    org = find_by_name("/api/v2/organizations/", ORG_NAME)
    if not org:
        print(f"  X Org '{ORG_NAME}' no existe")
        return 1
    org_id = org["id"]

    # Inventory
    inv = find_by_name("/api/v2/inventories/", INVENTORY_NAME)
    if not inv:
        inv = api_post("/api/v2/inventories/", {
            "name": INVENTORY_NAME,
            "description": "Inventario minimo (hosts: localhost)",
            "organization": org_id,
        })
        api_post(f"/api/v2/inventories/{inv['id']}/hosts/", {
            "name": "localhost",
            "variables": "ansible_connection: local\nansible_python_interpreter: /usr/bin/python3\n",
        })
        print(f"  + Inventory '{INVENTORY_NAME}' creado (id={inv['id']})")
    else:
        print(f"  = Inventory '{INVENTORY_NAME}' ya existe (id={inv['id']})")
    inv_id = inv["id"]

    # Execution environment
    ees = api_get("/api/v2/execution_environments/")["results"]
    ee = next((e for e in ees if "AWX EE" in e["name"] or "latest" in e["name"].lower()), ees[0])
    ee_id = ee["id"]
    print(f"  = Execution Env: '{ee['name']}' (id={ee_id})")

    # Project
    proj = find_by_name("/api/v2/projects/", PROJECT_NAME)
    if not proj:
        print(f"  X Project '{PROJECT_NAME}' no existe. Corre primero bootstrap-awx-azure.py")
        return 1
    proj_id = proj["id"]
    print(f"  = Project '{PROJECT_NAME}' encontrado (id={proj_id})")

    # Re-sync para que jale los 8 playbooks nuevos
    print(f"  > Disparando re-sync de project {proj_id}...")
    api_post(f"/api/v2/projects/{proj_id}/update/", {})
    if not wait_for_sync(proj_id):
        print("  X Sync no completo. Verifica project en UI AWX.")
        return 1
    print(f"  + Sync OK")

    # Listar playbooks detectados (para validar que estan los 8 nuevos)
    pb_list = api_get(f"/api/v2/projects/{proj_id}/playbooks/")
    print(f"  = Playbooks detectados ({len(pb_list)}):")
    for p in pb_list:
        marker = "  *" if any(yml in p for _, yml, _, _ in PLAYBOOKS) else "   "
        print(f"  {marker} {p}")
    print()

    # Crear los 8 JTs
    print("Creando Job Templates:")
    jt_summary = []
    for jt_name, pb_file, descr, is_invasive in PLAYBOOKS:
        full_path = f"{PLAYBOOK_DIR}/{pb_file}"
        if full_path not in pb_list:
            print(f"  ! '{jt_name}' SKIP — playbook {full_path} no detectado en project")
            continue
        existing = find_by_name("/api/v2/job_templates/", jt_name)
        if existing:
            jt_summary.append((jt_name, existing["id"], "(existente)", is_invasive))
            print(f"  = '{jt_name}' ya existe (id={existing['id']})")
            continue
        body = {
            "name": jt_name,
            "description": descr,
            "job_type": "run",
            "inventory": inv_id,
            "project": proj_id,
            "playbook": full_path,
            "execution_environment": ee_id,
            "ask_variables_on_launch": True,
            "verbosity": 1,
        }
        jt = api_post("/api/v2/job_templates/", body)
        jt_summary.append((jt_name, jt["id"], "(nuevo)", is_invasive))
        print(f"  + '{jt_name}' creado (id={jt['id']})")
    print()

    # Resumen final
    print("=" * 72)
    print("RESUMEN — IDs para actualizar .env")
    print("=" * 72)
    print()
    print("# Diagnosticos (no invasivos)")
    for n, i, s, inv_flag in jt_summary:
        if not inv_flag:
            env_var = ("AWX_JT_" + n.replace("talento-", "").replace("-", "_")).upper()
            print(f"  {env_var}={i}  # {n} {s}")
    print()
    print("# Remediaciones (dry_run=true por defecto)")
    for n, i, s, inv_flag in jt_summary:
        if inv_flag:
            env_var = ("AWX_JT_" + n.replace("talento-", "").replace("-", "_")).upper()
            print(f"  {env_var}={i}  # {n} {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
