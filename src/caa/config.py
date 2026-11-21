"""Settings loaded from environment variables only. No secrets live here.

Locally, `azd env get-values > .env` writes the values that `azd provision`
produced. In Azure, the Container App sets the same names as environment
variables. Every value is an endpoint or a name, never a key: auth uses
DefaultAzureCredential (your `az login` locally, managed identity in Azure).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Case Assessment Assistant"
    environment: str = "local"

    # Empty defaults keep unit tests runnable without Azure. Code that talks to
    # Azure calls `require()` so a missing value fails with a clear message.
    azure_foundry_project_endpoint: str = ""
    azure_openai_endpoint: str = ""
    embedding_model_deployment: str = "text-embedding-3-small"
    chat_model_deployment: str = "gpt-5.4-mini"
    azure_search_endpoint: str = ""
    azure_search_index: str = "case-chunks"
    azure_docintel_endpoint: str = ""
    azure_storage_account_url: str = ""
    azure_storage_container: str = "case-documents"
    azure_cosmos_endpoint: str = ""
    azure_cosmos_database: str = "caa"

    # Key that API clients send to the mock agency portal. It stands in for the
    # OAuth client credentials a real vendor would issue, and also signs the
    # portal's webhooks. If empty: open when local, otherwise a random key is
    # made at startup (the mock portal and its only client share the process).
    portal_api_key: str = ""
    # Where our app reaches the portal API. The mock runs in this same container,
    # so the default calls it over localhost, which also skips Easy Auth (that
    # only guards traffic coming in through ingress). Point this at a real
    # external system and the same client code is used.
    portal_base_url: str = "http://127.0.0.1:8000"

    # Used only when environment is "local" and no Easy Auth header is present,
    # so you can click through the app on your machine with both roles.
    dev_user_name: str = "local-dev"
    dev_user_roles: str = "Caseworker,Supervisor"

    def require(self, *names: str) -> None:
        missing = [n.upper() for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(
                f"Missing settings: {', '.join(missing)}. Run `azd env get-values > .env`."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
