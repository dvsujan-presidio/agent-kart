param location string
param token string
param tags object
param principalId string
param foundryName string
param speechName string

resource kv 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: 'kv-ak-${token}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// Key Vault Secrets Officer for the deploying user.
resource officer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, principalId, 'secrets-officer')
  scope: kv
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: foundryName }
resource speech 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: speechName }

resource foundryKey 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'model-api-key'
  properties: { value: foundry.listKeys().key1 }
  dependsOn: [officer]
}

resource speechKey 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: kv
  name: 'azure-speech-key'
  properties: { value: speech.listKeys().key1 }
  dependsOn: [officer]
}

output name string = kv.name
