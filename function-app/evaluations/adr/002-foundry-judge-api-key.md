# ADR-002: Foundry LLM-judge con api_key resuelto via Azure SDK

## Status
Aceptado — 2026-06-02

## Context

El SDK `azure-ai-evaluation` instancia `IntentResolutionEvaluator`, `ToolCallAccuracyEvaluator`, `TaskAdherenceEvaluator` con un `model_config` dict. Las opciones de auth son:

1. `api_key` directa
2. `azure_ad_token_provider` (token AAD)
3. Implícita via `DefaultAzureCredential`

En la primera implementación intenté (2) con `get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")`. Resultado en la corrida de baseline (run_20260602_184446): la mayoría de los evaluators devolvieron `PermissionDenied 401` con el mensaje "Principal does not have access to API/Operation". El error proviene de `AsyncAzureOpenAI` del SDK OpenAI underlying — el async path no resuelve bien el token provider en algunas combinaciones de SDK version.

El path soportado y documentado por Microsoft Learn es `api_key`.

Una solución improvisada sería `subprocess.check_output(["az", "cognitiveservices", "account", "keys", "list", ...])`. Eso es macheteo: requiere `az` CLI instalado, no es composable, no testeable, no portable a CI.

## Decision

Resolver el api_key del recurso Azure OpenAI subyacente a Foundry mediante el **Azure SDK Python** (`azure-mgmt-cognitiveservices`):

```python
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
client = CognitiveServicesManagementClient(credential, subscription_id)
keys = client.accounts.list_keys(resource_group_name, account_name)
api_key = keys.key1
```

Encapsulado en `eval/secrets.py:SecretsResolver` con cache en memoria por proceso. El mismo patrón se usa para el `AWX_TOKEN` productivo desde App Settings del Function App (`azure-mgmt-web`).

## Consequences

**Pros:**
- Sin dependencia del `az` CLI en runtime — el SDK Python es autosuficiente.
- Cache local evita roundtrips repetidos al Management API.
- Testeable: `SecretsResolver` se puede mockear inyectando `credential`.
- Documentable: los permisos requeridos quedan explícitos en el ADR (no escondidos en un comando shell).
- Misma identidad (`az login` del usuario) para Foundry agent invoke y para resolver secretos — un solo punto de auth a configurar.

**Contras:**
- Dependencias nuevas: `azure-mgmt-cognitiveservices`, `azure-mgmt-web`. Son paquetes oficiales de Microsoft y de bajo peso.
- Requiere permisos extra: la identidad necesita `Cognitive Services User` (o equivalente) en el recurso AOAI y `Reader`/`Website Contributor` en el Function App.

## Permisos requeridos

Para que `SecretsResolver` funcione, la identidad de `AzureCliCredential()` (típicamente el usuario que hizo `az login`) debe tener:

- **`aifoundry-is2`** (Cognitive Services account): rol `Cognitive Services User` o `Cognitive Services Contributor` que permita `list_keys`.
- **`fa-solucion-talento`** (Function App): rol que permita `web_apps.list_application_settings` — `Reader` no basta; necesita `Website Contributor` o un custom role con `Microsoft.Web/sites/config/list/action`.

Si la identidad no tiene esos permisos, `SecretsResolver` levanta excepción explícita con instrucciones (no fallback silencioso).

## Alternatives considered

- **Azure Key Vault**: enterprise-grade pero overkill para el caso. Habría que crear el vault, migrar los secrets, configurar acceso. Postergado a Phase 2.
- **Variables de entorno `AZURE_OPENAI_API_KEY` y `AWX_TOKEN` explícitas**: simple pero requiere setup manual en cada máquina. No es DRY frente a App Settings.
- **subprocess `az`**: descartado por las razones del Context.

## References

- [Microsoft Learn — Azure AI Evaluation SDK](https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/agent-evaluate-sdk).
- AUDIT.md: sección 5 "Auditoría del LLM-judge de Foundry".
