param location string
param token string
param tags object

resource speech 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ak-speech-${token}'
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'ak-speech-${token}'
    publicNetworkAccess: 'Enabled'
  }
}

output name string = speech.name
output endpoint string = speech.properties.endpoint
