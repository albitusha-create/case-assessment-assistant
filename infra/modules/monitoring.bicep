// Log Analytics workspace plus workspace-based Application Insights.
param token string
param location string
param tags object

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-caa-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-caa-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableLocalAuth: false // ingestion via connection string; switch to Entra ingestion in production
  }
}

output logAnalyticsId string = logs.id
output logAnalyticsName string = logs.name
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
