// Monthly cost budget on the resource group, with alerts at 50% and 100%.
param amount int
param contactEmail string
@description('First day of the current month; budgets must start on the 1st.')
param startDate string = '${utcNow('yyyy-MM')}-01'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-caa'
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: { startDate: startDate }
    notifications: {
      actual50: { enabled: true, operator: 'GreaterThan', threshold: 50, contactEmails: [ contactEmail ] }
      actual100: { enabled: true, operator: 'GreaterThan', threshold: 100, contactEmails: [ contactEmail ] }
    }
  }
}
