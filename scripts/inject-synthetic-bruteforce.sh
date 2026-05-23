#!/usr/bin/env bash
# inject-synthetic-bruteforce.sh
#
# Inyecta eventos sinteticos de failed login al workspace de Log Analytics
# para garantizar que la card "Detección de Brute Force" tenga datos
# visibles durante el demo.
#
# Estrategia:
#   - Usa la Data Collector API de Azure Monitor (HMAC-SHA256 con workspace key).
#   - Manda 15 eventos custom hacia una tabla CustomLog_CL llamada
#     TalentoSyntheticLogins_CL (creada automaticamente la primera vez).
#
# Limitaciones:
#   - Requiere PRIMARY_KEY del workspace (no el workspace_id), que NO esta
#     en el .env actual. Si no esta, el script intenta usar Az CLI:
#       az monitor log-analytics workspace get-shared-keys ...
#   - Alternativa simple: dejar este script como template y, mientras tanto,
#     usar las failed logins reales que ya existen en el workspace
#     (sqlserver-ecopetrol-admin).
#
# Uso:
#   ./scripts/inject-synthetic-bruteforce.sh [N_EVENTS]

set -euo pipefail

cd "$(dirname "$0")/.."

# Cargar env
set -a
# shellcheck disable=SC1091
source .env
set +a

N_EVENTS="${1:-15}"
USER_BAD="${SYNTHETIC_USER:-test_brute_attacker}"

echo "▸ Generando ${N_EVENTS} eventos sinteticos de failed login para usuario: ${USER_BAD}"
echo ""

# Validar que az CLI esta y autenticado
if ! command -v az >/dev/null 2>&1; then
  echo "✗ az CLI no disponible. Aborta."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "✗ az login no realizado. Corre 'az login --use-device-code' primero."
  exit 1
fi

# Necesitamos el resource group y nombre real del workspace para el az CLI.
# El .env tiene LOG_ANALYTICS_WORKSPACE_ID (el guid), pero el az necesita el name+RG.
# Como fallback, lo extraemos via az graph query.

WS_INFO=$(az graph query -q "Resources | where type =~ 'microsoft.operationalinsights/workspaces' and properties.customerId =~ '${LOG_ANALYTICS_WORKSPACE_ID}' | project name, resourceGroup, location" --output json 2>/dev/null || true)

WS_NAME=$(echo "$WS_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['name'] if d.get('data') else '')" 2>/dev/null || true)
WS_RG=$(echo "$WS_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['resourceGroup'] if d.get('data') else '')" 2>/dev/null || true)

if [ -z "$WS_NAME" ] || [ -z "$WS_RG" ]; then
  echo "⚠ No se pudo resolver el workspace via Resource Graph."
  echo "  Asegurate de que el SP tiene rol Reader sobre el workspace o usa otro mecanismo."
  echo ""
  echo "  Alternativa manual:"
  echo "    1. Encuentra workspace_name y resource_group en Azure Portal."
  echo "    2. Re-corre el script con esos datos como vars:"
  echo "       WS_NAME=<name> WS_RG=<rg> $0"
  exit 1
fi

echo "▸ Workspace resuelto: $WS_NAME (RG: $WS_RG)"

# Obtener primary key
WS_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$WS_RG" \
  --workspace-name "$WS_NAME" \
  --query primarySharedKey -o tsv 2>/dev/null || true)

if [ -z "$WS_KEY" ]; then
  echo "✗ No se pudo obtener primarySharedKey. Verifica permisos."
  exit 1
fi

echo "▸ Primary key obtenida (no se imprime)"
echo ""
echo "▸ Inyectando eventos via Data Collector API..."

# Construir array JSON de eventos
EVENTS_JSON=$(python3 -c "
import json, datetime, random
events = []
now = datetime.datetime.utcnow()
for i in range(${N_EVENTS}):
    ts = (now - datetime.timedelta(minutes=random.randint(1, 60))).isoformat() + 'Z'
    events.append({
        'TimeGenerated': ts,
        'EventType': 'FailedLogin',
        'User': '${USER_BAD}',
        'Source': 'SyntheticDemoInjector',
        'Message': f\"Login failed for user '${USER_BAD}'. Attempt {i+1}. ClientConnectionId:synthetic-{i}\",
    })
print(json.dumps(events))
")

# Llamada a Data Collector API
WORKSPACE_ID="${LOG_ANALYTICS_WORKSPACE_ID}"
LOG_TYPE="TalentoSyntheticLogins"
DATE_HEADER=$(LC_ALL=C date -u +"%a, %d %b %Y %H:%M:%S GMT")
CONTENT_LENGTH=$(echo -n "$EVENTS_JSON" | wc -c)
STRING_TO_HASH="POST\n${CONTENT_LENGTH}\napplication/json\nx-ms-date:${DATE_HEADER}\n/api/logs"
SIGNATURE=$(printf '%b' "$STRING_TO_HASH" | openssl dgst -sha256 -mac HMAC -macopt "key:$(echo -n "$WS_KEY" | base64 -d | xxd -p -c 256)" -binary 2>/dev/null | base64)
AUTH="SharedKey ${WORKSPACE_ID}:${SIGNATURE}"

HTTP_CODE=$(curl -s -o /tmp/inject_resp.txt -w "%{http_code}" \
  -X POST "https://${WORKSPACE_ID}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01" \
  -H "Content-Type: application/json" \
  -H "Log-Type: ${LOG_TYPE}" \
  -H "x-ms-date: ${DATE_HEADER}" \
  -H "Authorization: ${AUTH}" \
  -d "$EVENTS_JSON")

if [ "$HTTP_CODE" = "200" ]; then
  echo "✓ ${N_EVENTS} eventos inyectados a tabla ${LOG_TYPE}_CL"
  echo "  Tarda ~3-5 minutos en aparecer en KQL (ingestion latency normal)."
else
  echo "✗ Inyeccion fallo: HTTP ${HTTP_CODE}"
  cat /tmp/inject_resp.txt | head -5
  exit 1
fi
