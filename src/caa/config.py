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
