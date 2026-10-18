# Azure setup

Two routes: create the resources by hand in the portal (fastest), or provision the base services with the Bicep in `infra/`.
Pick regions close to your users. The voice path is the latency-sensitive part, so keep **Speech** (and any future containers) near your users;
**Foundry** can be wherever your model quota is.

## Route A: portal

### 1. Microsoft Foundry and a model deployment
1. Portal, **Microsoft Foundry**, create a resource (kind AIServices) in your resource group. Note its name.
2. *Models + endpoints*, **Deploy base model**: choose an OpenAI chat model with structured-output support (the project was built on `gpt-5.6-sol`; `gpt-5.6-luna` also works), deployment type **Global Standard**.
3. Keep the **deployment name** identical to `MODEL_DEPLOYMENT` (and `MODEL_DEPLOYMENT_FAST`) in `.env`.
4. Copy a key from *Keys and Endpoint* into `MODEL_API_KEY`; set `FOUNDRY_RESOURCE`, `MODEL_ENDPOINT` (`https://<resource>.cognitiveservices.azure.com/`) and `MODEL_API_VERSION`.
5. Check: `make check-model`.

### 2. Azure AI Speech
Create a **Speech service** (S0, or F0 for a free tier). Copy a key and the region into `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`.

### 3. Optional but recommended
- **Key Vault** (RBAC mode) for `model-api-key`, `azure-speech-key`, the approval secret and LiveKit secret.
- **Application Insights** (workspace-based) for traces.
- **Cost Management budget** with alerts (for example 50% and 90%).

### 4. LiveKit Cloud (not Azure)
Create a project at cloud.livekit.io and copy `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` into `.env`.

## Route B: Bicep (`infra/`)
`infra/main.bicep` (resource-group scope) provisions the Foundry account and a model deployment, Speech, Key Vault, Log Analytics,
Application Insights and a budget alert. It compiles with `az bicep build`; it has not been deployed as part of this project.
```bash
az bicep build --file infra/main.bicep
az deployment group what-if -g <resource-group> -f infra/main.bicep \
  -p environmentName=dev principalId=<your-object-id> budgetContactEmail=<email>
```
Edit `modelDeployment` / `modelVersion` in `infra/main.bicep` to match the model available to your subscription.
Container Apps, a registry and Cosmos DB are a planned second phase and are not in the template yet.

## Responsible handling
Never commit keys. Keep `.env` local and use Key Vault in Azure. Rotate any key that was ever pasted into chat, a ticket or a commit.
