"""Configuracion centralizada del eval pipeline.

Single source of truth para endpoints, deployments, thresholds, paths.
No usa os.environ en medio del codigo — todo se inyecta via AppConfig.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .schemas import CategoryThresholds


# Ubicaciones del paquete
PACKAGE_ROOT = Path(__file__).resolve().parent
EVALUATIONS_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = EVALUATIONS_ROOT.parent
ENV_FILE = PROJECT_ROOT.parent / ".env"


@dataclass(frozen=True)
class FoundryConfig:
    """Coordenadas del recurso Azure AI Foundry."""
    project_endpoint: str = (
        "https://aifoundry-is2.services.ai.azure.com/api/projects/proj-foundry-is2"
    )
    aoai_endpoint: str = "https://aifoundry-is2.openai.azure.com/"
    aoai_resource_name: str = "aifoundry-is2"
    aoai_resource_group: str = "rg-central-is2"
    agent_name: str = "talento-triage-agent"
    model_deployment: str = "talento-gpt4o-mini"
    api_version: str = "2024-08-01-preview"


@dataclass(frozen=True)
class FunctionAppConfig:
    """Coordenadas del Function App productivo (para obtener App Settings)."""
    name: str = "fa-solucion-talento"
    resource_group: str = "rg-central-solucion-talento"
    subscription_id: str = "7c5b032f-7879-4ec3-a2ed-978b444f6755"


@dataclass(frozen=True)
class RunnerConfig:
    """Parametros de ejecucion del runner."""
    max_hops_per_turn: int = 8
    tool_output_truncate_chars: int = 8000
    case_timeout_seconds: int = 180


@dataclass(frozen=True)
class PathsConfig:
    """Paths del paquete."""
    package_root: Path = PACKAGE_ROOT
    evaluations_root: Path = EVALUATIONS_ROOT
    project_root: Path = PROJECT_ROOT
    env_file: Path = ENV_FILE
    dataset_jsonl: Path = EVALUATIONS_ROOT / "dataset" / "golden_dataset.jsonl"
    results_dir: Path = EVALUATIONS_ROOT / "results"


@dataclass(frozen=True)
class AppConfig:
    """Configuracion compuesta del eval pipeline.

    Todos los modulos reciben una instancia de AppConfig en lugar de leer
    os.environ ad-hoc. Esto facilita tests y override desde CLI.
    """
    foundry: FoundryConfig = field(default_factory=FoundryConfig)
    function_app: FunctionAppConfig = field(default_factory=FunctionAppConfig)
    runner: RunnerConfig = field(default_factory=RunnerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    thresholds: CategoryThresholds = field(default_factory=CategoryThresholds)


def load_dotenv_safely(env_file: Path) -> dict:
    """Carga .env como dict (sin aplicar a os.environ).

    Las vars AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET son del SP que el bridge
    usa para Log Analytics. NO afectan al auth de Foundry porque usamos
    AzureCliCredential explicito en SecretsResolver y AIProjectClient.
    """
    if not env_file.exists():
        return {}
    out = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def apply_env_for_bridge(env_vars: dict) -> None:
    """Aplica vars del .env a os.environ.

    El bridge_l2 hace `ENV = dict(os.environ)` al import — entonces este apply
    DEBE ocurrir ANTES de importar bridge_l2. Si bridge ya fue importado, el
    override real va en bridge_l2.ENV directamente (ver BridgeToolExecutor).
    """
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
