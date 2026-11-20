# Scripts

| Script | What it does |
| --- | --- |
| `seed_data.py` | Creates the `case-chunks` index and ingests the synthetic PDFs (blob, layout, chunk, embed, index). |
| `entra_app.sh` | Creates the Entra app registration for sign-in, its Caseworker and Supervisor roles, assigns both to you, and saves `AUTH_CLIENT_ID`. |
| `apim_off.sh` | After a demo: points the app back at Foundry, then deletes and purges API Management. |
| `github_oidc.sh` | One-time setup for the deploy workflow: GitHub OIDC identity (`azd pipeline config`), repository variables, and data roles for the eval gate. |
| `teardown.sh` | Deletes everything `azd provision` created and purges soft-deleted resources. |

