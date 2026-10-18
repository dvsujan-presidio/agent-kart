param location string
param token string
param tags object

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-ak-${token}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-ak-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

output logAnalyticsId string = logs.id
output connectionString string = appi.properties.ConnectionString
