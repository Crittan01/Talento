"""Resolucion de secretos via Azure SDK (no subprocess, no hardcoded).

Encapsula:
  - api_key de Azure OpenAI para los LLM-judge evaluators
  - AWX_TOKEN productivo desde App Settings del Function App

Cache en memoria por proceso. La primera invocacion paga el roundtrip al
Azure Management API, las siguientes son free.

Permisos requeridos en la identidad de `az login`:
  - Cognitive Services User en el recurso aifoundry-is2
  - Contributor (o Website Contributor) en el resource group del Function App
"""
from __future__ import annotations

import logging
from typing import Optional

from azure.identity import AzureCliCredential, DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.web import WebSiteManagementClient

from .config import AppConfig

logger = logging.getLogger("eval.secrets")


class SecretsResolver:
    """Resuelve secretos productivos via Azure SDK con cache en memoria."""

    def __init__(self, config: AppConfig, credential=None) -> None:
        self.config = config
        # AzureCliCredential explicito: queremos el az login del usuario, no
        # otras credenciales que puedan estar en el env.
        self.credential = credential or AzureCliCredential()
        self._aoai_api_key: Optional[str] = None
        self._awx_token: Optional[str] = None

    # --------------------------------------------------------------------- AOAI
    def get_aoai_api_key(self) -> str:
        """Devuelve la api_key del recurso Azure OpenAI subyacente a Foundry.

        Necesario porque el SDK azure-ai-evaluation usa AsyncAzureOpenAI que
        no resuelve bien AAD via azure_ad_token_provider — el path soportado
        es pasar api_key explicita en model_config.
        """
        if self._aoai_api_key is not None:
            return self._aoai_api_key

        client = CognitiveServicesManagementClient(
            credential=self.credential,
            subscription_id=self.config.function_app.subscription_id,
        )
        keys = client.accounts.list_keys(
            resource_group_name=self.config.foundry.aoai_resource_group,
            account_name=self.config.foundry.aoai_resource_name,
        )
        if not keys.key1:
            raise RuntimeError(
                f"No se pudo obtener api_key de {self.config.foundry.aoai_resource_name}"
            )
        self._aoai_api_key = keys.key1
        logger.info(
            "AOAI api_key resuelto (sufijo %s***)", self._aoai_api_key[-4:]
        )
        return self._aoai_api_key

    # ---------------------------------------------------------------------- AWX
    def get_awx_token(self) -> str:
        """Devuelve el AWX_TOKEN productivo desde App Settings del Function App.

        El .env local apunta a un AWX de desarrollo distinto cuyo token devuelve
        HTTP 401 contra AWX prod. La fuente de verdad es App Settings.
        """
        if self._awx_token is not None:
            return self._awx_token

        client = WebSiteManagementClient(
            credential=self.credential,
            subscription_id=self.config.function_app.subscription_id,
        )
        # list_application_settings devuelve un objeto con .properties (dict)
        settings = client.web_apps.list_application_settings(
            resource_group_name=self.config.function_app.resource_group,
            name=self.config.function_app.name,
        )
        token = settings.properties.get("AWX_TOKEN")
        if not token:
            raise RuntimeError(
                f"AWX_TOKEN no encontrado en App Settings de {self.config.function_app.name}"
            )
        self._awx_token = token
        logger.info("AWX_TOKEN prod resuelto (sufijo %s***)", token[-4:])
        return token

    # ----------------------------------------------------------- conveniencia
    def model_config_for_evaluator(self) -> dict:
        """Construye el model_config para los Foundry evaluators."""
        return {
            "azure_endpoint": self.config.foundry.aoai_endpoint,
            "azure_deployment": self.config.foundry.model_deployment,
            "api_version": self.config.foundry.api_version,
            "api_key": self.get_aoai_api_key(),
            "type": "azure_openai",
        }
