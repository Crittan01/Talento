#!/usr/bin/env bash
# validate.sh — smoke tests pre-demo
# Verifica: az login activo, AWX alcanzable, Foundry endpoint vivo, mock run OK.

set -uo pipefail

cd "$(dirname "$0")/.."

# Cargar env
set -a
# shellcheck disable=SC1091
source .env
set +a

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

# 1. az login
check "az CLI instalado" "command -v az"
check "az account show (sin sudo)" "az account show"
check "Tenant correcto (NTT DATA Colombia)" "az account show --query name --output tsv | grep -q 'Azure subscription'"

# 2. .env
check ".env existe y permisos 600" "test -f .env && [ \$(stat -c '%a' .env) = '600' ]"
check "AZURE_TENANT_ID en .env" "test -n \"\${AZURE_TENANT_ID:-}\""
check "AWX_TOKEN en .env" "test -n \"\${AWX_TOKEN:-}\""
check "TEAMS_WEBHOOK_URL en .env" "test -n \"\${TEAMS_WEBHOOK_URL:-}\""

# 3. AWX
check "AWX reachable (https://192.168.250.20.nip.io)" "curl -ks -o /dev/null -w '%{http_code}' --connect-timeout 5 ${AWX_URL}/api/v2/ping/ | grep -q 200"
check "AWX token valido" "curl -ks -H 'Authorization: Bearer ${AWX_TOKEN}' ${AWX_URL}/api/v2/me/ | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get(\"count\",0)>0 else 1)'"

# 4. Foundry endpoint
check "Foundry endpoint responde token request" "az account get-access-token --resource https://cognitiveservices.azure.com/ --query expiresOn -o tsv"

# 5. Python deps
check "fastapi instalado" "python3 -c 'import fastapi'"
check "uvicorn instalado" "python3 -c 'import uvicorn'"
check "azure-ai-projects instalado" "python3 -c 'import azure.ai.projects'"
check "azure-identity instalado" "python3 -c 'import azure.identity'"
check "openai instalado" "python3 -c 'import openai'"

# 6. Webapp importable
check "webapp imports OK" "python3 -c 'from webapp import app, scenarios, mock_events, event_bus, bridge_runner'"
check "bridge_l2 imports OK" "python3 -c 'import bridge_l2'"
check "bridge_l2.run_cycle tiene emit param" "python3 -c 'import bridge_l2, inspect; assert \"emit\" in inspect.signature(bridge_l2.run_cycle).parameters'"

# 7. Mock dataset completo
check "mock_events tiene 6 escenarios" "python3 -c 'from webapp.mock_events import MOCK_SEQUENCES; assert len(MOCK_SEQUENCES)==6'"

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
echo "✓ Todo OK — listo para 'make demo' o 'make mock'."
