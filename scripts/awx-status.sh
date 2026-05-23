#!/usr/bin/env bash
# awx-status.sh — resumen ejecutivo del estado de AWX
# Lista JTs (id, name, last status) + jobs de las ultimas 24h.

set -uo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a

HDR="Authorization: Bearer ${AWX_TOKEN}"

echo "═══════════ AWX status (${AWX_URL}) ═══════════"
echo ""

echo "── Projects ──"
curl -ks -H "$HDR" "${AWX_URL}/api/v2/projects/?page_size=10" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in d.get('results', []):
    print(f'  {p[\"id\"]:>3}  {p[\"name\"]:35s} status={p.get(\"status\",\"?\")}  scm_url={p.get(\"scm_url\",\"\")}')"

echo ""
echo "── Job Templates ──"
curl -ks -H "$HDR" "${AWX_URL}/api/v2/job_templates/?page_size=20" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for t in d.get('results', []):
    last = t.get('summary_fields',{}).get('last_job',{})
    last_status = last.get('status','—') if last else '—'
    print(f'  {t[\"id\"]:>3}  {t[\"name\"]:35s} last_status={last_status}  playbook={t.get(\"playbook\",\"\")}')"

echo ""
echo "── Jobs ultimas 24h (top 15) ──"
curl -ks -H "$HDR" "${AWX_URL}/api/v2/jobs/?page_size=15&order_by=-created" | python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta
d = json.load(sys.stdin)
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
shown = 0
for j in d.get('results', []):
    try:
        created = datetime.fromisoformat(j.get('created','').replace('Z','+00:00'))
        if created < cutoff:
            continue
    except ValueError:
        pass
    status_icon = {'successful': '✓', 'failed': '✗', 'running': '↻', 'pending': '…', 'canceled': '⊘', 'error': '!'}.get(j.get('status'), '?')
    print(f'  {j[\"id\"]:>5}  {status_icon} {j.get(\"status\",\"?\"):12s} {j.get(\"name\",\"\"):35s} elapsed={j.get(\"elapsed\",0):>6.1f}s  finished={j.get(\"finished\",\"—\")}')
    shown += 1
print(f'  ({shown} jobs en las ultimas 24h)')"

echo ""
echo "── Credentials ──"
curl -ks -H "$HDR" "${AWX_URL}/api/v2/credentials/?page_size=10" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('results', []):
    kind = c.get('summary_fields',{}).get('credential_type',{}).get('name','?')
    print(f'  {c[\"id\"]:>3}  {c[\"name\"]:35s} type={kind}')"

echo ""
