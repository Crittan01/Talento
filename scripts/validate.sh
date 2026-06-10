#!/usr/bin/env bash
# validate.sh — smoke tests pre-demo (v21)
# Verifica: .env OK, AWX alcanzable, Foundry token via SP, paquetes en venv, webapp importable.

set -uo pipefail

cd "$(dirname "$0")/.."

# Cargar env
set -a
# shellcheck disable=SC1091
source .env
set +a

# Venv Python — requerido para todos los checks de Python
PYTHON="/Ansible/agents/.venv/bin/python3"

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  printf "▸ %-50s " "$name"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "✓"
    PASS=$((PASS + 1))
  else
    echo "✗"
    FAIL=$((FAIL + 1))
  fi
}

echo "═══════════ talento-ecopetrol — validate.sh ═══════════"
echo ""

# 1. .env
check ".env existe y permisos 600"       "test -f .env && [ \$(stat -c '%a' .env) = '600' ]"
check "AZURE_TENANT_ID en .env"          "test -n \"\${AZURE_TENANT_ID:-}\""
check "AZURE_CLIENT_ID en .env"          "test -n \"\${AZURE_CLIENT_ID:-}\""
check "AZURE_CLIENT_SECRET en .env"      "test -n \"\${AZURE_CLIENT_SECRET:-}\""
check "AWX_TOKEN en .env"                "test -n \"\${AWX_TOKEN:-}\""
check "TEAMS_WEBHOOK_URL en .env"        "test -n \"\${TEAMS_WEBHOOK_URL:-}\""

# 2. AWX
check "AWX reachable (${AWX_URL})"       "curl -ks -o /dev/null -w '%{http_code}' --connect-timeout 5 ${AWX_URL}/api/v2/ping/ | grep -q 200"
check "AWX token valido"                 "curl -ks -H 'Authorization: Bearer ${AWX_TOKEN}' ${AWX_URL}/api/v2/me/ | ${PYTHON} -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get(\"count\",0)>0 else 1)'"

# 3. Foundry auth via SP (no requiere az login)
check "Foundry token via SP"             "curl -s -X POST \
  https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/token \
  -d 'grant_type=client_credentials&client_id=${AZURE_CLIENT_ID}&client_secret=${AZURE_CLIENT_SECRET}&resource=https://ai.azure.com/' \
  | ${PYTHON} -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get(\"access_token\") else 1)'"

# 4. ARM token via SP
check "ARM token via SP"                 "curl -s -X POST \
  https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/token \
  -d 'grant_type=client_credentials&client_id=${AZURE_CLIENT_ID}&client_secret=${AZURE_CLIENT_SECRET}&resource=https://management.azure.com/' \
  | ${PYTHON} -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get(\"access_token\") else 1)'"

# 5. Python deps (venv)
check "fastapi instalado (venv)"         "${PYTHON} -c 'import fastapi'"
check "uvicorn instalado (venv)"         "${PYTHON} -c 'import uvicorn'"
check "azure-ai-projects instalado"      "${PYTHON} -c 'import azure.ai.projects'"
check "azure-identity instalado"         "${PYTHON} -c 'import azure.identity'"
check "azure-mgmt-containerinstance"     "${PYTHON} -c 'import azure.mgmt.containerinstance'"
check "azure-monitor-query instalado"    "${PYTHON} -c 'import azure.monitor.query'"
check "openai instalado"                 "${PYTHON} -c 'import openai'"
check "requests instalado"               "${PYTHON} -c 'import requests'"

# 6. Webapp importable (venv + rutas correctas)
check "webapp imports OK"                "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp import app, scenarios, mock_events, event_bus, bridge_runner'"
check "bridge_l2 imports OK"             "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2'"
check "bridge_l2.run_cycle emit param"   "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2, inspect; assert \"emit\" in inspect.signature(bridge_l2.run_cycle).parameters'"
check "bridge_l2 CATALOG_VERSION v22"    "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert bridge_l2.CATALOG_VERSION.startswith(\"v22\"), bridge_l2.CATALOG_VERSION'"
check "report_incident tool existe"     "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert hasattr(bridge_l2, \"post_incident_to_panel\") and hasattr(bridge_l2, \"TOOL_REPORT_INCIDENT\")'"
check "PANEL_INCIDENTE_URL configurado"  "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert \"/api/incidente\" in bridge_l2.PANEL_INCIDENTE_URL'"
check "bridge_l2 JT_IDS tiene 6 JTs"    "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert len(bridge_l2.JT_IDS)==6, len(bridge_l2.JT_IDS)'"
check "lookup_infrastructure existe"     "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert callable(bridge_l2.lookup_infrastructure)'"
check "lookup_sql existe"                "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert callable(bridge_l2.lookup_sql)'"
check "detect_anomalies existe"          "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert callable(bridge_l2.detect_anomalies)'"

# 7. Scenarios v21
check "scenarios tiene 13 escenarios"   "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import list_scenarios; assert len(list_scenarios())==13, len(list_scenarios())'"
check "infra-health-check existe"        "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import get_scenario; assert get_scenario(\"infra-health-check\")'"
check "sql absorbido en infra-health"    "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import get_scenario; assert get_scenario(\"sql-health\") is None, \"sql-health sigue separado\"'"
check "anomaly-scan existe"              "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import get_scenario; assert get_scenario(\"anomaly-scan\")'"
check "sql-diagnostics-enable existe"   "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import get_scenario; assert get_scenario(\"sql-diagnostics-enable\")'"
check "nsg-block-ip existe"             "PYTHONPATH=.:function-app ${PYTHON} -c \
  'from webapp.scenarios import get_scenario; assert get_scenario(\"nsg-block-ip\")'"
check "RESOURCE_PROFILES v1/v2"          "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; assert set(bridge_l2.RESOURCE_PROFILES)=={\"v1\",\"v2\"}'"
check "_get_profile() devuelve v2"       "PYTHONPATH=function-app ${PYTHON} -c \
  'import bridge_l2; p=bridge_l2._get_profile(\"v2\"); assert p[\"aci_name\"]==\"aci-centralecopetrol2\"'"

echo ""
echo "═══════════ Resumen ═══════════"
echo "  Pass: ${PASS}"
echo "  Fail: ${FAIL}"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "✗ Hay checks fallidos. NO entres al demo sin resolverlos."
  exit 1
fi
echo ""
echo "✓ Todo OK — listo para 'make demo-local' o 'make mock'."
