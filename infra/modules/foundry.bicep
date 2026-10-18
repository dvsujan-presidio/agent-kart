// Microsoft Foundry (AIServices) account hosting OpenAI model deployments.
param location string
param token string
param tags object
param deployments array // [{ name, version, capacity }]

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ak-foundry-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'ak-foundry-${token}'
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

// Deploy sequentially: parallel model deployments on one account conflict.
@batchSize(1)
resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for d in deployments: {
  parent: account
  name: d.name
  sku: { name: 'GlobalStandard', capacity: d.capacity }
  properties: {
    model: { format: 'OpenAI', name: d.name, version: d.version }
  }
}]

output name string = account.name
output endpoint string = account.properties.endpoint
