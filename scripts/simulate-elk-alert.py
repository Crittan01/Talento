#!/usr/bin/env python3
"""simulate-elk-alert.py — Simulador del HUB de monitoreo ELK para TALENTO.

Reproduce exactamente lo que haria ELK en produccion: detecta una condicion
segun sus reglas, construye una alerta y la dispara contra el endpoint del
agente. Verifica que el agente investiga recursivamente y propone remediacion.

A diferencia de un mock, usa la MISMA logica normalize_payload del
function_app.py productivo y ejecuta el ciclo REAL del agente Foundry.

Uso:
  python3 scripts/simulate-elk-alert.py                 # corre las 5 alertas demo
  python3 scripts/simulate-elk-alert.py error_rate      # una alerta especifica
  python3 scripts/simulate-elk-alert.py --list          # lista alertas disponibles
  python3 scripts/simulate-elk-alert.py --http URL      # dispara por HTTP real al endpoint

Las alertas simulan reglas tipicas de ELK Watcher / Kibana alerting.
"""
import sys
import os
import json
import time
import argparse
from pathlib import Path

# Cargar .env + paths
ROOT = Path(__file__).resolve().parent.parent
FUNC_APP = ROOT / "function-app"
sys.path.insert(0, str(FUNC_APP))

os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
os.environ.setdefault("SSL_CERT_FILE", "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")

_env = dict(os.environ)
_envfile = ROOT / ".env"
if _envfile.exists():
    for line in _envfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        _env[k.strip()] = v.strip().strip('"').strip("'")
        os.environ[k.strip()] = _env[k.strip()]

import bridge_l2
bridge_l2.ENV.update(_env)
import function_app  # usa normalize_payload, el mismo del endpoint productivo


# ============================================================================
# Catalogo de alertas ELK simuladas — reglas tipicas del HUB de monitoreo.
# Cada una representa una condicion que ELK detectaria sobre los datos que
# recolecta del sistema TALENTO.
# ============================================================================
ELK_ALERTS = {
    "error_rate": {
        "_desc": "ELK Watcher: tasa de ERROR supero el umbral en ventana corta",
        "alert": {
            "source": "elk",
            "rule": "talento-error-rate-watcher",
            "severity": "high",
            "metric": "error_rate",
            "resource": "talento-app (aci-centralecopetrol2)",
            "context": {
                "value": 18,
                "threshold": 10,
                "unit": "errors/5min",
                "window": "5m",
                "index": "talento-logs-*",
            },
            "target_env": "v2",
        },
    },
    "auth_failures": {
        "_desc": "ELK Watcher: pico de fallos de autenticacion (posible brute force)",
        "alert": {
            "source": "elk",
            "rule": "talento-auth-bruteforce-watcher",
            "severity": "high",
            "metric": "auth_failures",
            "resource": "talento-app login",
            "context": {
                "value": 23,
                "threshold": 5,
                "unit": "failed_logins/3min",
                "window": "3m",
                "tlnt_codes": ["TLNT-002", "TLNT-008", "TLNT-009"],
            },
            "target_env": "v2",
        },
    },
    "sql_dtu": {
        "_desc": "ELK + Azure Monitor: DTU de SQL supero umbral durante cierre de nomina",
        "alert": {
            "source": "azuremonitor-via-elk",
            "rule": "talento-sql-dtu-watcher",
            "severity": "high",
            "metric": "sql_dtu",
            "resource": "sqlserver-ecopetrol2/ecopetroldb2",
            "context": {
                "value": 92,
                "threshold": 80,
                "unit": "DTU%",
                "window": "15m",
                "note": "coincide con ventana de cierre de nomina",
            },
            "target_env": "v2",
        },
    },
    "latency_p95": {
        "_desc": "ELK: latencia P95 de la app degradada",
        "alert": {
            "source": "elk",
            "rule": "talento-latency-watcher",
            "severity": "medium",
            "metric": "latency_p95",
            "resource": "talento-app endpoints",
            "context": {
                "value": 2400,
                "threshold": 1000,
                "unit": "ms",
                "window": "10m",
                "affected_endpoints": ["/api/vacaciones", "/api/nomina"],
            },
            "target_env": "v2",
        },
    },
    "container_restart": {
        "_desc": "ELK: el container reinicio varias veces (posible crash loop)",
        "alert": {
            "source": "elk",
            "rule": "talento-container-restart-watcher",
            "severity": "critical",
            "metric": "container_restart",
            "resource": "aci-centralecopetrol2",
            "context": {
                "value": 4,
                "threshold": 2,
                "unit": "restarts/30min",
                "window": "30m",
            },
            "target_env": "v2",
        },
    },
}


def _print_header(title):
    print("\n" + "═" * 78)
    print(f"  {title}")
    print("═" * 78)


def run_alert_local(key: str, alert_spec: dict) -> dict:
    """Ejecuta una alerta usando el ciclo real del agente (sin HTTP).
    Reproduce lo que hace el endpoint /api/run internamente."""
    from azure.ai.projects import AIProjectClient

    _print_header(f"ALERTA ELK: {key}")
    print(f"  {alert_spec['_desc']}")
    print(f"\n  Payload que ELK enviaria:")
    print("  " + json.dumps({"alert": alert_spec["alert"]}, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    # 1. normalize_payload — la MISMA funcion del endpoint productivo
    body = {"alert": alert_spec["alert"]}
    user_question = function_app.normalize_payload(body)
    target_env = alert_spec["alert"].get("target_env", "v2")

    print(f"\n  → Instruccion generada para el agente ({len(user_question)} chars):")
    print("  " + user_question[:300].replace("\n", "\n  ") + "...")

    # 2. Ejecutar el ciclo real del agente
    project = AIProjectClient(
        endpoint=bridge_l2.PROJECT_ENDPOINT,
        credential=bridge_l2.get_azure_credential(),
    )

    events = []
    tools_used = []

    def emit(ev):
        events.append(ev)
        t = ev.get("type")
        if t == "tool.call":
            tools_used.append(ev.get("tool"))
            print(f"    🛠️  hop → {ev.get('tool')} {str(ev.get('args',{}))[:70]}")
        elif t == "agent.hop":
            print(f"    🔄 Hop {ev.get('hop')} — razonando...")
        elif t == "tool.awx.done":
            print(f"    ✓ AWX job {ev.get('job_id')} status={ev.get('status')} (dry-run)")
        elif t == "tool.awx.error":
            print(f"    ⚠ AWX: {str(ev.get('error',''))[:60]}")

    print(f"\n  → Investigacion del agente (env={target_env}):")
    t0 = time.time()
    bridge_l2.run_cycle(
        project=project,
        agent_name=bridge_l2.AGENT_NAME,
        user_question=user_question,
        max_hops=8,
        emit=emit,
        force_extra_vars={"target_env": target_env},
    )
    elapsed = time.time() - t0

    final_text = next((e.get("text") for e in events if e.get("type") == "agent.final"), None)
    hops = len([e for e in events if e.get("type") == "agent.hop"])

    print(f"\n  ─── VEREDICTO DEL AGENTE ({elapsed:.1f}s, {hops} hops) ───")
    if final_text:
        print("  " + final_text.replace("\n", "\n  "))

    return {
        "alert": key,
        "tools_used": tools_used,
        "hops": hops,
        "elapsed": round(elapsed, 1),
        "final_text": final_text,
    }


def run_alert_http(key: str, alert_spec: dict, base_url: str, func_key: str = "") -> dict:
    """Dispara la alerta por HTTP real contra /api/elk/ingest (Monitor en Vivo).

    Esto reproduce EXACTAMENTE lo que ELK haria en produccion: un POST con el
    payload de alerta. El agente investiga y todo se visualiza en /monitor.
    Abre http://localhost:8000/monitor en el browser para verlo en tiempo real.
    """
    import requests
    _print_header(f"ALERTA ELK (HTTP → /api/elk/ingest): {key}")
    print(f"  {alert_spec['_desc']}")
    url = f"{base_url.rstrip('/')}/api/elk/ingest"
    params = {"code": func_key} if func_key else {}
    t0 = time.time()
    try:
        r = requests.post(url, params=params, json={"alert": alert_spec["alert"]},
                          timeout=120, verify=os.environ.get("REQUESTS_CA_BUNDLE", True))
    except Exception as exc:
        print(f"  ✗ Error de conexion: {exc}")
        return {"error": str(exc), "alert": key}
    elapsed = time.time() - t0
    print(f"  HTTP {r.status_code} ({elapsed:.1f}s)")
    if r.status_code in (200, 202):
        d = r.json()
        print(f"  status: {d.get('status')}")
        print(f"  incident_id: {d.get('incident_id')}")
        print(f"  → Abre http://localhost:8000/monitor para ver la investigacion EN VIVO")
        return {"alert": key, **d}
    else:
        print(f"  Error: {r.text[:200]}")
        return {"error": r.text, "alert": key}


def main():
    parser = argparse.ArgumentParser(description="Simulador de alertas ELK para TALENTO")
    parser.add_argument("alert", nargs="?", help="clave de alerta (o vacio para todas)")
    parser.add_argument("--list", action="store_true", help="lista las alertas disponibles")
    parser.add_argument("--http", metavar="URL", help="dispara por HTTP real al endpoint")
    parser.add_argument("--key", default="", help="function key para el endpoint HTTP")
    args = parser.parse_args()

    if args.list:
        _print_header("Alertas ELK disponibles")
        for k, v in ELK_ALERTS.items():
            print(f"  {k:<20} — {v['_desc']}")
        return

    to_run = [args.alert] if args.alert else list(ELK_ALERTS.keys())
    summary = []
    for key in to_run:
        spec = ELK_ALERTS.get(key)
        if not spec:
            print(f"✗ Alerta desconocida: {key} (usa --list)")
            continue
        if args.http:
            res = run_alert_http(key, spec, args.http, args.key)
        else:
            res = run_alert_local(key, spec)
        summary.append(res)

    # Resumen final
    _print_header("RESUMEN DE LA SIMULACION")
    for s in summary:
        if "error" in s:
            print(f"  ✗ {s.get('alert','?')}: {str(s['error'])[:60]}")
        elif "incident_id" in s:
            # Modo HTTP (asíncrono): el agente investiga en background
            print(f"  ✓ {s['alert']:<18} | ingestada → incident {s['incident_id']} | ver en /monitor")
        else:
            # Modo local (síncrono): tenemos hops y tools
            awx = "✓ remediacion propuesta" if any("awx" in str(t) for t in s.get("tools_used", [])) else "solo diagnostico"
            print(f"  ✓ {s['alert']:<18} | {s.get('hops','?')} hops | tools={s.get('tools_used',[])} | {awx}")

    if any("incident_id" in s for s in summary):
        print(f"\n  → Investigacion en vivo: http://localhost:8000/monitor")


if __name__ == "__main__":
    main()
