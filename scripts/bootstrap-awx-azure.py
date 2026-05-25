#!/usr/bin/env python3
"""
bootstrap-awx-azure.py — crea de cero (o re-utiliza si existe) Inventory,
Project y los 4 Job Templates en el AWX de Azure. Idempotente.

Uso:
  AWX_URL=http://172.210.65.202.nip.io \
  AWX_TOKEN=xxxx \
    python3 scripts/bootstrap-awx-azure.py

Salida: imprime al final un bloque con los IDs (project, JT) para
actualizar .env apuntando al AWX nuevo.
"""

import json
import os
import sys
import time
from typing import Optional

import requests

AWX_URL = os.environ["AWX_URL"].rstrip("/")
AWX_TOKEN = os.environ["AWX_TOKEN"]
ORG_NAME = "Ecopetrol"
GIT_REPO = "https://github.com/Crittan01/Talento.git"
GIT_BRANCH = "develop"
# Subpath de los playbooks dentro del repo (la raiz del repo es la carpeta
# talento-ecopetrol/, no el monorepo). AWX detecta playbooks/talento-*.yml
PLAYBOOK_DIR = "playbooks"

PLAYBOOKS = [
    ("talento-workspace-snapshot",      "talento-workspace-snapshot.yml",
     "Snapshot/auditoria amplia del workspace TALENTO (inventario de tablas)"),
    ("talento-errors-analysis",         "talento-errors-analysis.yml",
     "Analisis de errores y warnings agrupados con notificacion Teams"),
    ("talento-sox-audit",               "talento-sox-audit.yml",
     "Auditoria SOX: logins, acciones criticas, incidentes BD (rango configurable)"),
    ("talento-brute-force-detector",    "talento-brute-force-detector.yml",
     "Detector enfocado de brute-force con umbral por usuario"),
]

H = {"Authorization": f"Bearer {AWX_TOKEN}", "Content-Type": "application/json"}


def api_get(path, **params):
    r = requests.get(f"{AWX_URL}{path}", headers=H, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, body):
    r = requests.post(f"{AWX_URL}{path}", headers=H, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  ❌ POST {path} → HTTP {r.status_code}")
        print(f"     Body enviado: {json.dumps(body)[:300]}")
        print(f"     Respuesta:    {r.text[:500]}")
        r.raise_for_status()
    return r.json()


def find_by_name(path, name) -> Optional[dict]:
    """Busca un objeto por nombre exacto en cualquier listing AWX."""
    d = api_get(path, name=name)
    for r in d.get("results", []):
        if r["name"] == name:
            return r
    return None


def wait_for_project_sync(project_id: int, timeout: int = 120) -> bool:
    """Espera a que el proyecto termine el primer sync (status=successful)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = api_get(f"/api/v2/projects/{project_id}/")
        status = d.get("status")
        if status == "successful":
            return True
        if status in ("failed", "error", "canceled"):
            print(f"  ❌ Project sync status={status}")
            return False
        print(f"     ...status={status}, esperando 3s")
        time.sleep(3)
    print(f"  ⚠ Timeout esperando sync (>{timeout}s)")
    return False


def main():
    print("=" * 72)
    print("BOOTSTRAP AWX Azure — TALENTO automation")
    print("=" * 72)
    print(f"  AWX URL:    {AWX_URL}")
    print(f"  Org:        {ORG_NAME}")
    print(f"  Git repo:   {GIT_REPO}  (branch: {GIT_BRANCH})")
    print()

    # Resolver Organization ID
    org = find_by_name("/api/v2/organizations/", ORG_NAME)
    if not org:
        print(f"  ❌ Organization '{ORG_NAME}' no existe. Crearla manualmente primero.")
        return 1
    org_id = org["id"]
    print(f"  ✓ Org '{ORG_NAME}' encontrada (id={org_id})")
    print()

    # Resolver Execution Environment (prefiere 'AWX EE (latest)')
    ees = api_get("/api/v2/execution_environments/")["results"]
    ee = next((e for e in ees if e["name"] == "AWX EE (latest)"), None) or ees[0]
    ee_id = ee["id"]
    print(f"  ✓ Execution Environment: '{ee['name']}' (id={ee_id})")
    print()

    # ------------------------------------------------------------------
    # 1. Inventory: talento-localhost (un host = localhost via local conn)
    # ------------------------------------------------------------------
    print("[1/4] Inventory 'talento-localhost'...")
    inv = find_by_name("/api/v2/inventories/", "talento-localhost")
    if inv:
        print(f"  ↻ ya existe (id={inv['id']}), reutilizando")
    else:
        inv = api_post("/api/v2/inventories/", {
            "name": "talento-localhost",
            "description": "Inventario minimo para playbooks que corren en hosts: localhost",
            "organization": org_id,
        })
        print(f"  ✓ creada (id={inv['id']})")

        # Crear host 'localhost' dentro de la inventory
        host = api_post(f"/api/v2/inventories/{inv['id']}/hosts/", {
            "name": "localhost",
            "variables": "ansible_connection: local\nansible_python_interpreter: /usr/bin/python3\n",
        })
        print(f"  ✓ host 'localhost' creado (id={host['id']})")
    inv_id = inv["id"]
    print()

    # ------------------------------------------------------------------
    # 2. Project: talento-automation-source (apunta al repo Git)
    # ------------------------------------------------------------------
    print("[2/4] Project 'talento-automation-source'...")
    proj = find_by_name("/api/v2/projects/", "talento-automation-source")
    if proj:
        print(f"  ↻ ya existe (id={proj['id']}), disparando re-sync")
        api_post(f"/api/v2/projects/{proj['id']}/update/", {})
    else:
        proj = api_post("/api/v2/projects/", {
            "name": "talento-automation-source",
            "description": "Playbooks Ansible para automatizacion/observabilidad de TALENTO",
            "organization": org_id,
            "scm_type": "git",
            "scm_url": GIT_REPO,
            "scm_branch": GIT_BRANCH,
            "scm_clean": False,
            "scm_delete_on_update": False,
            "scm_update_on_launch": False,
            "default_environment": ee_id,
        })
        print(f"  ✓ creado (id={proj['id']}) — iniciando primer sync")
    proj_id = proj["id"]

    print(f"  ⏳ Esperando sync del proyecto...")
    ok = wait_for_project_sync(proj_id)
    if not ok:
        print("  ❌ Sync no completo. Reviar UI del AWX → Projects → talento-automation-source")
        return 1
    print(f"  ✓ Sync OK")
    print()

    # ------------------------------------------------------------------
    # 3. Job Templates (uno por playbook)
    # ------------------------------------------------------------------
    print("[3/4] Job Templates (4)...")
    jt_summary = []
    for jt_name, playbook_file, descr in PLAYBOOKS:
        full_path = f"{PLAYBOOK_DIR}/{playbook_file}"
        jt = find_by_name("/api/v2/job_templates/", jt_name)
        if jt:
            print(f"  ↻ '{jt_name}' ya existe (id={jt['id']}), reutilizando")
        else:
            jt = api_post("/api/v2/job_templates/", {
                "name": jt_name,
                "description": descr,
                "job_type": "run",
                "inventory": inv_id,
                "project": proj_id,
                "playbook": full_path,
                "execution_environment": ee_id,
                "ask_variables_on_launch": True,  # bridge inyecta extra_vars
                "ask_limit_on_launch": False,
                "verbosity": 1,
                "use_fact_cache": False,
            })
            print(f"  ✓ '{jt_name}' creado (id={jt['id']})")
        jt_summary.append((jt_name, jt["id"], full_path))
    print()

    # ------------------------------------------------------------------
    # 4. Resumen para actualizar .env
    # ------------------------------------------------------------------
    print("=" * 72)
    print("✅ BOOTSTRAP COMPLETO")
    print("=" * 72)
    print()
    print("Valores para actualizar en .env (apuntar al AWX de Azure):")
    print()
    print(f"  AWX_URL={AWX_URL}")
    print(f"  AWX_TOKEN=<el token que usaste>")
    print(f"  AWX_ORG_ID={org_id}")
    print()
    print("Mapeo de Job Templates (anotar para actualizar scenarios.py):")
    print()
    for jt_name, jt_id, path in jt_summary:
        print(f"  - {jt_name:35} → JT id={jt_id} → {path}")
    print()
    print("Project ID:", proj_id, " (usar en `make awx-sync` si quieres re-sync)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
