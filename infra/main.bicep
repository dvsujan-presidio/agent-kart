// AgentKart infrastructure, phase 1: models, speech, secrets, observability, budget.
// Phase 2 (deployHosting=true) adds ACR, Container Apps and Cosmos; see docs/azure-setup.md.
targetScope = 'resourceGroup'

@description('Short environment name, used in resource names.')
param environmentName string

@description('Region for Microsoft Foundry (use the region where your Foundry resource lives).')
param foundryLocation string = 'eastus'

@description('Region for Speech, Key Vault, monitoring and (phase 2) Container Apps.')
param location string = 'centralindia'

@description('Object id of the deploying user; gets Key Vault Secrets Officer.')
param principalId string

@description('Email for the budget alert.')
param budgetContactEmail string

@description('Budget alert threshold in USD for this resource group.')
param budgetAmount int = 100

@description('Budget start; must be first of a month. Defaults to the current month.')
param budgetStart string = utcNow('yyyy-MM-01')

@description('Model used by planner, explainer and intake.')
param modelDeployment string = 'gpt-5.6-luna'
param modelVersion string = '2026-07-09'
@description('Capacity in thousands of tokens per minute.')
param modelCapacity int = 100

var token = toLower(uniqueString(resourceGroup().id, environmentName))
var tags = { 'azd-env-name': environmentName, app: 'agentkart' }

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: { location: location, token: token, tags: tags }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  params: {
    location: foundryLocation
    token: token
    tags: tags
    deployments: [
      { name: modelDeployment, version: modelVersion, capacity: modelCapacity }
    ]
  }
}

module speech 'modules/speech.bicep' = {
  name: 'speech'
  params: { location: location, token: token, tags: tags }
}

module vault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    token: token
    tags: tags
    principalId: principalId
    foundryName: foundry.outputs.name
    speechName: speech.outputs.name
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'agentkart-${environmentName}-budget'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: '${budgetStart}T00:00:00Z' }
    notifications: {
      actual50: { enabled: true, operator: 'GreaterThan', threshold: 50, contactEmails: [budgetContactEmail] }
      actual90: { enabled: true, operator: 'GreaterThan', threshold: 90, contactEmails: [budgetContactEmail] }
    }
  }
}

output FOUNDRY_RESOURCE string = foundry.outputs.name
output FOUNDRY_ENDPOINT string = foundry.outputs.endpoint
output MODEL_DEPLOYMENT string = modelDeployment
output MODEL_DEPLOYMENT_FAST string = modelDeployment
output AZURE_SPEECH_REGION string = location
output AZURE_SPEECH_ENDPOINT string = speech.outputs.endpoint
output AZURE_KEY_VAULT_NAME string = vault.outputs.name
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.connectionString
