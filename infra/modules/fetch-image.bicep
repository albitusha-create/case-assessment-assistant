// Returns the image the web app runs now, or an empty string before the first
// deploy. It is its own module because a template cannot both read and
// deploy the same resource (ARM reports a circular dependency).
param name string
param exists bool

resource app 'Microsoft.App/containerApps@2024-03-01' existing = if (exists) {
  name: name
}

output image string = exists ? app!.properties.template.containers[0].image : ''
