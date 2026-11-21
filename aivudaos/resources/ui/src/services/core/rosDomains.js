// App packages can declare the ROS domain under their own configuration namespace.
export function appDomainRows(apps, globalDomain) {
  const rows = []
  for (const app of apps) {
    const fields = []
    function visit(data, path = []) {
      for (const [key, value] of Object.entries(data || {})) {
        const parts = [...path, key]
        if (value && typeof value === 'object' && !Array.isArray(value)) {
          visit(value, parts)
          continue
        }
        const name = key.toLowerCase()
        const parent = path.at(-1)?.toLowerCase()
        if (['ros_domain_id', 'ros2_domain_id'].includes(name) ||
            (name === 'domain_id' && (!parent || ['ros', 'ros2', 'dds'].includes(parent)))) {
          fields.push({ path: parts.join('.'), value })
        }
      }
    }
    visit(app.data)
    if (!fields.length) fields.push({ path: '', value: -1 })
    for (const { path, value } of fields) {
      const inherited = value === -1 || value === '-1'
      const number = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value
      const valid = Number.isInteger(number) && number >= 0 && number <= 232
      rows.push({
        appId: app.app_id, name: app.name || app.app_id, path,
        domain: inherited ? globalDomain : valid ? number : null,
        source: inherited ? 'inherited' : valid ? 'override' : 'invalid',
      })
    }
  }
  return rows.sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path))
}
