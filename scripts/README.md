# Scripts

| Script | What it does |
| --- | --- |
| `seed_data.py` | Creates the `case-chunks` index and ingests the synthetic PDFs (blob, layout, chunk, embed, index). |
| `entra_app.sh` | Creates the Entra app registration for sign-in, its Caseworker and Supervisor roles, assigns both to you, and saves `AUTH_CLIENT_ID`. |
| `apim_off.sh` | After a demo: points the app back at Foundry, then deletes and purges API Management. |
| `teardown.sh` | Deletes everything `azd provision` created and purges soft-deleted resources. |

The GitHub OIDC setup lands here later.
