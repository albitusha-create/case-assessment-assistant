// Container Apps environment, a private registry and the web app.
// The app runs as the user-assigned identity, pulls its image with that
// identity (no registry passwords), and scales to zero when idle.
// Sign-in (Easy Auth) is turned on once authClientId is set; see
// scripts/entra_app.sh.
param token string
param location string
param tags object
param identityId string
param identityPrincipalId string
param logAnalyticsName string
param appSettings array
@secure()
param appInsightsConnectionString string

@description('Client id of the Entra app registration. Empty means sign-in is not configured yet, so every page returns 401.')
param authClientId string

@description('True after the first `azd deploy`, so a later `azd provision` keeps the deployed image instead of resetting it to the placeholder.')
param exists bool

var appName = 'ca-caa-${token}'
var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crcaa${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identityPrincipalId, acrPull)
  properties: {
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-caa-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource existingApp 'Microsoft.App/containerApps@2024-03-01' existing = if (exists) {
  name: appName
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  // azd finds the app to deploy to by this tag.
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
      }
      registries: [ { server: registry.properties.loginServer, identity: identityId } ]
      secrets: [ { name: 'appinsights-connection-string', value: appInsightsConnectionString } ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: exists ? existingApp!.properties.template.containers[0].image : placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(appSettings, [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
          ])
        }
      ]
      // Zero when idle keeps the cost at zero inside the monthly free grant.
      // One replica at most: a demo needs no more, and it caps spend.
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
  dependsOn: [ pullRole ]
}

// Easy Auth: Container Apps signs the user in with Entra ID before a request
// reaches the app, then passes the user's claims (including app roles) in the
// X-MS-CLIENT-PRINCIPAL header. No client secret: sign-in uses the ID token
// only, which is all the app needs. /healthz stays open for probes.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (!empty(authClientId)) {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: [ '/healthz' ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          openIdIssuer: '${az.environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
      }
    }
  }
}

output registryEndpoint string = registry.properties.loginServer
output appName string = app.name
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
