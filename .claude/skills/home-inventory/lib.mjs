// Helpers for targeted homelab-inventory edits. run.sh prepends this file to your script.
// Every helper re-reads current state before writing, so edits made in the UI survive.
const BASE = process.env.INVENTORY_BASE ?? 'http://homelab-inventory:8798' // override to point at a sandbox
const PROJECT = 1

async function api(method, path, body) {
  const response = await fetch(BASE + path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  if (!response.ok) throw new Error(`${method} ${path} -> ${response.status}: ${text.slice(0, 800)}`)
  return text ? JSON.parse(text) : null
}

const workbook = () => api('GET', `/api/projects/${PROJECT}/workbook`)
const WORKSPACE = (await workbook()).defaultWorkspaceId
const workspace = () => api('GET', `/api/projects/${PROJECT}/workspaces/${WORKSPACE}`)

// Runtime keys look like "server:4"; the API paths want type and numeric id separately.
const splitKey = (key) => {
  const [type, id] = key.split(':')
  return { type, id: Number(id) }
}

// Finds a live item by exact name (optionally type). Throws if missing or ambiguous.
async function findItem(name, type) {
  const matches = Object.values((await workspace()).items)
    .filter((item) => item.name === name && (!type || item.type === type) && !item.archivedAt)
  if (matches.length !== 1) throw new Error(`expected one item named "${name}", found ${matches.length}`)
  return matches[0]
}

// The fields PUT /api/inventory/items accepts. PUT replaces the item, so always start from the current one.
const INPUT_FIELDS = [
  'type', 'name', 'hardwareClass', 'usageRole', 'subtype', 'manufacturer', 'secondaryManufacturer',
  'family', 'model', 'number', 'aliases', 'specs', 'smart', 'properties', 'ports', 'compatibility',
  'fixedComponents', 'notes',
]
const toInput = (item) => Object.fromEntries(
  INPUT_FIELDS.filter((field) => item[field] !== undefined).map((field) => [field, structuredClone(item[field])]),
)

// mutate(input) edits a copy of the current item in place; returns the saved item.
async function updateItem(key, mutate) {
  const current = (await workspace()).items[key]
  if (!current) throw new Error(`no item ${key}`)
  const input = toInput(current)
  mutate(input)
  const { type, id } = splitKey(key)
  await api('PUT', `/api/inventory/items/${type}/${id}`, { item: input })
  return (await workspace()).items[key]
}

// Creates a project item and returns its new runtime key.
async function createItem(input) {
  const before = new Set(Object.keys((await workspace()).items))
  await api('POST', `/api/projects/${PROJECT}/inventory/items`, { item: { scope: 'project', ...input } })
  const created = Object.keys((await workspace()).items).filter((key) => !before.has(key))
  if (created.length !== 1) throw new Error(`expected one new item, got ${created.join(', ')}`)
  return created[0]
}

async function catalog() {
  const response = await api('GET', '/api/inventory-metadata/catalog')
  const c = response.catalog ?? response
  return {
    raw: c,
    fields: Object.fromEntries(c.definitions.filter((d) => !d.archivedAt).map((d) => [d.name, d])),
    tags: Object.fromEntries(c.tags.filter((t) => !t.archivedAt).map((t) => [t.name, t])),
  }
}

// Custom field values by field name, plus tag names.
async function getMetadata(key) {
  const { type, id } = splitKey(key)
  const m = await api('GET', `/api/inventory/items/${type}/${id}/metadata`)
  const names = Object.fromEntries(m.definitions.map((d) => [d.id, d.name]))
  return {
    values: Object.fromEntries(m.values.map((v) => [names[v.definitionId], v.optionIds.length ? v.optionIds : v.value])),
    tags: m.tags.map((t) => t.name),
  }
}

// Merges into the current metadata: values {Field: value, Other: null to clear}; tags replaces the tag list if given.
// The PUT itself replaces everything, which is why this reads first.
async function setMetadata(key, { values = {}, tags } = {}) {
  const { fields, tags: tagIndex } = await catalog()
  const current = await getMetadata(key)
  const merged = { ...current.values, ...values }
  for (const name of Object.keys(merged)) if (!fields[name]) throw new Error(`no custom field "${name}"`)
  const tagNames = tags ?? current.tags
  for (const name of tagNames) if (!tagIndex[name]) throw new Error(`no tag "${name}"`)
  const { type, id } = splitKey(key)
  await api('PUT', `/api/inventory/items/${type}/${id}/metadata`, {
    values: Object.entries(merged)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([name, value]) => ({ definitionId: fields[name].id, value })),
    tagIds: tagNames.map((name) => tagIndex[name].id),
  })
  return getMetadata(key)
}

// mutate(state) edits placements / assignments / connections in place.
// Sends back the full state with its revision, so a concurrent UI edit makes this fail (409) instead of being lost.
async function updateCanvas(mutate) {
  const state = await workspace()
  mutate(state)
  return api('PUT', `/api/projects/${PROJECT}/workspaces/${WORKSPACE}`, state)
}

const nextId = (list) => Math.max(0, ...list.map((entry) => entry.id)) + 1

// Assigns components (runtime keys) to a host; skips ones already assigned anywhere.
async function assign(hostKey, componentKeys) {
  return updateCanvas((state) => {
    let id = nextId(state.assignments)
    for (const itemKey of componentKeys) {
      if (state.assignments.some((a) => a.itemId === itemKey)) continue
      state.assignments.push({
        id: id++, serverId: hostKey, itemId: itemKey,
        type: splitKey(itemKey).type, assignedAt: new Date().toISOString(),
      })
    }
  })
}

// Adds one cable between endpoints { itemId, portId[, hostedItemId] }.
// hostedItemId is the component key when the port lives on a PC build's motherboard or an assigned NIC/GPU.
async function connect(from, to, { speedBps, label, type = 'network' } = {}) {
  return updateCanvas((state) => {
    state.connections.push({
      id: nextId(state.connections), from, to, type,
      ...(speedBps ? { negotiatedSpeedBps: speedBps } : {}),
      ...(label ? { label } : {}),
      createdAt: new Date().toISOString(),
    })
  })
}

// Compact snapshot for before/after comparisons.
async function snapshot() {
  const state = await workspace()
  return JSON.stringify({ items: state.items, placements: state.placements, assignments: state.assignments, connections: state.connections })
}
