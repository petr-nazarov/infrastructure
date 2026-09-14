// Prints the homelab-inventory (inventory-home) project as Markdown for pasting into an LLM.
// Read-only. Runs inside the swarm network, where the app needs no login (Authelia guards it outside):
//   just inventory-dump
const BASE = process.env.BASE ?? 'http://homelab-inventory:8798'
const PROJECT = Number(process.env.PROJECT ?? 1)

async function api(path, body) {
  const response = await fetch(BASE + path, body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`${path} -> ${response.status}: ${(await response.text()).slice(0, 300)}`)
  return response.json()
}

const workbook = await api(`/api/projects/${PROJECT}/workbook`)
const state = await api(`/api/projects/${PROJECT}/workspaces/${workbook.defaultWorkspaceId}`)
const catalogResponse = await api('/api/inventory-metadata/catalog')
const catalog = catalogResponse.catalog ?? catalogResponse
const definitions = catalog.definitions.filter((d) => !d.archivedAt)
const metadata = await api(`/api/projects/${PROJECT}/inventory-metadata/query`, {
  definitionIds: definitions.map((d) => d.id),
})
const metadataByKey = new Map(metadata.rows.map((row) => [`${row.itemType}:${row.legacyId}`, row]))

const TYPE_LABELS = {
  server: 'Server', nas: 'NAS', pcBuild: 'PC Build', switch: 'Switch', patchPanel: 'Patch Panel',
  monitor: 'Monitor', ups: 'UPS', powerStrip: 'Power Strip', cpu: 'CPU', ram: 'RAM', storage: 'Storage',
  gpu: 'GPU', network: 'Network Adapter', motherboard: 'Motherboard', cpuCooler: 'CPU Cooler',
  case: 'Case', powerSupply: 'Power Supply', soundCard: 'Sound Card', powerAdapter: 'Power Adapter',
}
const EQUIPMENT = new Set(['server', 'nas', 'pcBuild', 'switch', 'patchPanel', 'monitor', 'ups', 'powerStrip'])

const items = Object.values(state.items).filter((item) => !item.archivedAt)
const itemsByKey = new Map(items.map((item) => [item.key, item]))
const componentsByHost = new Map()
for (const assignment of state.assignments) {
  const list = componentsByHost.get(assignment.serverId) ?? []
  list.push(itemsByKey.get(assignment.itemId))
  componentsByHost.set(assignment.serverId, list.filter(Boolean))
}
const assigned = new Set(state.assignments.map((a) => a.itemId))

// ---------------------------------------------------------------- formatting
const join = (parts, separator = ' · ') => parts.filter((part) => part !== undefined && part !== null && part !== '').join(separator)
const title = (item) => join([item.manufacturer, item.model], ' ')
const PORT_TYPES = { rj45: 'RJ45', sfp: 'SFP', 'sfp-plus': 'SFP+', hdmi: 'HDMI', displayport: 'DisplayPort', 'mini-displayport': 'Mini DisplayPort',
  'ac-input': 'AC', 'ac-outlet': 'AC outlet', barrel: 'DC barrel' }

function speed(bps) {
  if (!bps) return ''
  return bps >= 1e9 ? `${bps / 1e9}G` : `${bps / 1e6}M`
}

function specValue(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function specsLine(specs = {}) {
  return join(Object.entries(specs).map(([key, value]) => `${key} ${specValue(value)}`))
}

function componentSummary(item) {
  const s = item.specs ?? {}
  const capacity = s.capacityTb ? `${s.capacityTb}TB` : s.capacityGb ? `${s.capacityGb}GB` : ''
  const clocks = join([s.baseClockGhz, s.boostClockGhz].map((v) => v && `${v}`), '–')
  switch (item.type) {
    case 'cpu':
      return join([s.cores && `${s.cores} cores`, s.threads && `${s.threads} threads`, clocks && `${clocks} GHz`])
    case 'ram':
      return join([capacity, s.generation, s.formFactor, s.speedMt && `${s.speedMt} MT/s`, s.ecc === true ? 'ECC' : ''])
    case 'storage':
      return join([capacity, s.interface, s.formFactor])
    case 'gpu':
      return join([s.vramGb && `${s.vramGb}GB VRAM`, s.pcie])
    default:
      return specsLine(s)
  }
}

function fieldLines(item) {
  const row = metadataByKey.get(item.key)
  if (!row) return []
  const values = definitions
    .map((d) => [d.name, row.values[String(d.id)]])
    .filter(([, value]) => value && (value.display ?? value.value) !== null)
    .map(([name, value]) => `${name}: ${value.display ?? value.value}`)
  return [
    values.length ? `- ${join(values)}` : '',
    row.tags.length ? `- Tags: ${row.tags.map((t) => t.name).join(', ')}` : '',
  ].filter(Boolean)
}

function portName(port) {
  return port.label?.trim() || `port ${port.slotNumber}`
}

function findPort(endpoint) {
  const owner = itemsByKey.get(endpoint.hostedItemId ?? endpoint.itemId)
  return owner?.ports?.find((port) => String(port.id) === String(endpoint.portId))
}

function endpointName(endpoint) {
  const host = itemsByKey.get(endpoint.itemId)
  const component = endpoint.hostedItemId ? itemsByKey.get(endpoint.hostedItemId) : undefined
  const port = findPort(endpoint)
  return join([host?.name ?? endpoint.itemId, component?.name, port ? portName(port) : `port #${endpoint.portId}`], ' ')
}

function peerOf(itemKey, hostedKey, portId) {
  for (const connection of state.connections) {
    for (const [self, other] of [[connection.from, connection.to], [connection.to, connection.from]]) {
      const hostedMatches = hostedKey ? self.hostedItemId === hostedKey : !self.hostedItemId
      if (self.itemId === itemKey && hostedMatches && String(self.portId) === String(portId)) {
        return join([`→ ${endpointName(other)}`, speed(connection.negotiatedSpeedBps), connection.label], ', ')
      }
    }
  }
  return ''
}

function portLines(item, owner = item, prefix = '') {
  return (owner.ports ?? [])
    .slice()
    .sort((a, b) => a.slotNumber - b.slotNumber)
    .map((port) => {
      const hostedKey = owner === item ? undefined : owner.key
      const details = join([
        PORT_TYPES[port.type] ?? port.type.toUpperCase(), port.speed, port.role && port.role !== 'access' ? port.role : '',
        port.ipAddress, port.notes,
      ], ', ')
      return `  - ${prefix}${portName(port)}: ${details} ${peerOf(item.key, hostedKey, port.id)}`.trimEnd()
    })
}

function ipSortKey(item) {
  const row = metadataByKey.get(item.key)
  const ipDefinition = definitions.find((d) => /^ip/i.test(d.name))
  const raw = ipDefinition && row?.values[String(ipDefinition.id)]?.value
  const match = /(\d+)\.(\d+)\.(\d+)\.(\d+)/.exec(raw ?? '')
  return match ? match.slice(1).reduce((acc, octet) => acc * 256 + Number(octet), 0) : Infinity
}

// ---------------------------------------------------------------- output
const out = []
out.push(`# ${workbook.project.name}`, '')
out.push(`Exported ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC from homelab-inventory. ` +
  'Devices are listed by IP; ports show what they are cabled to.', '')
if (workbook.project.description) out.push(workbook.project.description, '')

out.push('## Devices', '')
const equipment = items
  .filter((item) => EQUIPMENT.has(item.type))
  .sort((a, b) => ipSortKey(a) - ipSortKey(b) || a.name.localeCompare(b.name))
for (const item of equipment) {
  const classification = item.type === 'server'
    ? join([item.hardwareClass && `class ${item.hardwareClass}`, item.usageRole && `used as ${item.usageRole}`], ', ')
    : ''
  out.push(`### ${item.name}`)
  out.push(`- ${join([TYPE_LABELS[item.type] ?? item.type, title(item), classification])}`)
  out.push(...fieldLines(item))
  const specs = specsLine(item.specs)
  if (specs) out.push(`- Specs: ${specs}`)
  const components = componentsByHost.get(item.key) ?? []
  if (components.length) {
    out.push('- Components:')
    for (const component of components) {
      out.push(`  - ${TYPE_LABELS[component.type] ?? component.type}: ${join([component.name, componentSummary(component)], ' — ')}`)
    }
  }
  const ports = [
    ...portLines(item),
    ...components.flatMap((component) => portLines(item, component, `${component.name} `)),
  ]
  if (ports.length) out.push('- Ports:', ...ports)
  if (item.notes) out.push(`- Notes: ${item.notes.replace(/\n+/g, ' ')}`)
  out.push('')
}

const spare = items.filter((item) => !EQUIPMENT.has(item.type) && !assigned.has(item.key))
if (spare.length) {
  out.push('## Unassigned components', '')
  for (const item of spare) {
    out.push(`- ${TYPE_LABELS[item.type] ?? item.type}: ${join([item.name, componentSummary(item)], ' — ')}`)
  }
  out.push('')
}

out.push('## Cables', '')
for (const connection of state.connections) {
  const details = join([
    connection.type !== 'network' ? connection.type : '', speed(connection.negotiatedSpeedBps), connection.label,
  ], ', ')
  out.push(`- ${endpointName(connection.from)} ↔ ${endpointName(connection.to)}${details ? `, ${details}` : ''}`)
}
console.log(out.join('\n'))
