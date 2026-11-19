// Key Vault with RBAC authorization. Holds only values that cannot be a
// managed identity. Purge protection is off so teardown can purge it.
param name string
param location string
param tags object
param principals array

var secretsUser = '4633458b-17de-408a-b874-0445c86b69e6'

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
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

resource roles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in principals: {
  scope: vault
  name: guid(vault.id, p.id, secretsUser)
  properties: {
    principalId: p.id
    principalType: p.type
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUser)
  }
}]

output uri string = vault.properties.vaultUri
