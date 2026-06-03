"""ToolExecutor Protocol + implementaciones.

ADR-004: el AgentRunner recibe un ToolExecutor por inyeccion, no llama directo
al bridge.

  - BridgeToolExecutor: produccion local (delega a bridge_l2 con env correcto).
    Requiere conectividad directa a AWX y a Log Analytics.
  - HttpToolExecutor: invoca el endpoint /api/tool/exec del Function App
    productivo. Util cuando el cliente local no tiene conectividad a AWX o LA
    pero el Function App si (esta dentro de Azure).
  - MockToolExecutor: tests (respuestas predefinidas, sin red).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional, Protocol

import requests

from .config import AppConfig
from .secrets import SecretsResolver

logger = logging.getLogger("eval.tool_executor")


class ToolExecutor(Protocol):
    """Interfaz minima para ejecutar los tools del agente."""

    def execute_kql(self, query: str) -> dict: ...
    def execute_awx(self, template_id: int, extra_vars: dict) -> dict: ...


class BridgeToolExecutor:
    """Delega a bridge_l2 con la configuracion correcta inyectada.

    El bridge captura ENV = dict(os.environ) al import — por eso despues del
    import mutamos bridge.ENV directamente para garantizar AWX productivo
    y demas overrides (en lugar de tocar os.environ, que ya esta congelado
    en el snapshot de bridge.ENV).
    """

    AWX_URL_PROD = "http://172.210.65.202.nip.io"

    def __init__(self, config: AppConfig, secrets: SecretsResolver) -> None:
        self.config = config
        self.secrets = secrets
        self._bridge = None

    def _ensure_bridge(self):
        """Lazy import + override de bridge.ENV (no os.environ)."""
        if self._bridge is not None:
            return self._bridge

        # Cargar bridge_l2 desde su directorio
        import sys
        function_app_dir = str(self.config.paths.evaluations_root.parent)
        if function_app_dir not in sys.path:
            sys.path.insert(0, function_app_dir)
        import bridge_l2

        # Override directo del ENV snapshot del bridge (no os.environ)
        bridge_l2.ENV["AWX_URL"] = self.AWX_URL_PROD
        bridge_l2.ENV["AWX_TOKEN"] = self.secrets.get_awx_token()

        self._bridge = bridge_l2
        return self._bridge

    def execute_kql(self, query: str) -> dict:
        bridge = self._ensure_bridge()
        return bridge.execute_kql(query)

    def execute_awx(self, template_id: int, extra_vars: dict) -> dict:
        bridge = self._ensure_bridge()
        return bridge.run_awx_job_template(template_id, extra_vars=extra_vars)


class HttpToolExecutor:
    """Delega la ejecucion de tools al Function App productivo.

    El Function App expone /api/tool/exec que invoca bridge_l2.execute_kql /
    run_awx_job_template internamente. Esto permite que un cliente sin acceso
    a AWX/LA delegue al Function App (que si tiene acceso desde Azure VNet).

    El function key se obtiene via `az functionapp keys list` (la identidad
    de az login debe tener permiso de lectura sobre el Function App).
    """

    TOOL_KQL = "query_log_analytics"
    TOOL_AWX = "run_awx_job_template"

    def __init__(
        self,
        config: AppConfig,
        request_timeout_s: int = 120,
    ) -> None:
        self.config = config
        self.base_url = (
            f"https://{config.function_app.name}-akdhbnczhvaxfde0."
            "centralus-01.azurewebsites.net"
        )
        self.timeout = request_timeout_s
        self._key: Optional[str] = None

    def _function_key(self) -> str:
        if self._key is not None:
            return self._key
        # Resolver via az CLI (mismo patron que SecretsResolver,
        # az functionapp keys list no esta en azure-mgmt-web stable API)
        out = subprocess.check_output(
            [
                "az", "functionapp", "keys", "list",
                "-n", self.config.function_app.name,
                "-g", self.config.function_app.resource_group,
                "--query", "functionKeys.default",
                "-o", "tsv",
            ],
            text=True, timeout=60,
        ).strip()
        if not out:
            raise RuntimeError("No se pudo obtener function key")
        self._key = out
        logger.info("Function key resuelto (sufijo %s***)", out[-4:])
        return out

    def _post_tool(self, tool: str, args: dict) -> dict:
        url = f"{self.base_url}/api/tool/exec?code={self._function_key()}"
        try:
            resp = requests.post(
                url,
                json={"tool": tool, "args": args},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return {
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "tool": tool,
                }
            return resp.json()
        except requests.exceptions.RequestException as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}", "tool": tool}

    def execute_kql(self, query: str) -> dict:
        return self._post_tool(self.TOOL_KQL, {"query": query})

    def execute_awx(self, template_id: int, extra_vars: dict) -> dict:
        return self._post_tool(
            self.TOOL_AWX,
            {"template_id": template_id, "extra_vars": extra_vars},
        )


class MockToolExecutor:
    """Implementacion para tests. Respuestas predefinidas o via callables."""

    def __init__(
        self,
        kql_response: Any = None,
        awx_response: Any = None,
        kql_handler: Callable[[str], dict] = None,
        awx_handler: Callable[[int, dict], dict] = None,
    ) -> None:
        self.kql_response = kql_response or {"rows": 0, "columns": [], "data": []}
        self.awx_response = awx_response or {"status": "successful", "job_id": 99999}
        self.kql_handler = kql_handler
        self.awx_handler = awx_handler
        self.calls: List[Dict[str, Any]] = []

    def execute_kql(self, query: str) -> dict:
        self.calls.append({"type": "kql", "query": query})
        if self.kql_handler:
            return self.kql_handler(query)
        return self.kql_response

    def execute_awx(self, template_id: int, extra_vars: dict) -> dict:
        self.calls.append({"type": "awx", "template_id": template_id, "extra_vars": extra_vars})
        if self.awx_handler:
            return self.awx_handler(template_id, extra_vars)
        return self.awx_response
