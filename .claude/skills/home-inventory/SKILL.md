---
name: home-inventory
description: Read and edit the data inside the homelab-inventory app (inventory-home) - devices, specs, components, ports, cables, canvas positions, custom fields (Hostname, IP Address, OS, SSH User, Services) and tags - through its API, without losing edits the user made in the UI. Use when the user asks to add, change, rename, fill in, fix or check anything "in the inventory" / "in inventory-home" / "in homelab-inventory", record hardware facts from a host, or cable devices on the canvas. Not for deploying the app itself (that's roles/docker/deploy-docker-swarm).
argument-hint: "<what to change>"
allowed-tools: [Bash, Read, Edit, Write, Grep, AskUserQuestion]
---

# /home-inventory - edit the data in inventory-home

`$ARGUMENTS` says what to change. `SKILL` below means
`.claude/skills/home-inventory`. Its helpers are tested against app **0.16.14**.
If the app was upgraded, re-check anything that fails against the source (step 9).

The user edits this app in the browser all the time, often while you work.
Everything below is built around one rule: **read the current state, change only
the thing asked, write it back, and prove nothing else moved.**

---

## 1. Where the data lives

| What | Where |
| --- | --- |
| App | swarm stack `home`, service `homelab-inventory`, image `mriverodorta/homelab-inventory:stable`, port 8798, on home-edge (swarm manager) |
| Public URL | `https://inventory-home.<public_top_domain>` behind Authelia forward auth |
| Data | `~/<remote_data>/homelab-inventory/` on home-edge; the one that matters is `databases/homelab-inventory.sqlite` (+ `-wal`, `-shm`) |
| Compose / deploy | `roles/docker/deploy-docker-swarm/templates/compose/homelab-inventory.yml.j2` (commit `ef27948`) |

The app's own login is **disabled** (`/api/auth/status` → `"mode":"disabled"`).
Authelia is the only gate. So from inside the attachable overlay network
`home_local_net` the API needs no credentials. Every helper here uses that path:
it runs a throwaway container on home-edge on that network.

**Never write the SQLite file directly.** The schema has 250+ tables, triggers
and revision counters, and the running app keeps caches. Use the API. Reading a
*copy* of the DB for forensics is fine (step 8).

## 2. Look before you touch

- **Overview:** `just inventory-dump` writes `tmp/inventory.md`, a Markdown view of
  every device with its fields, components, ports and what each port is cabled to.
  Start here to find names and spot what's missing.
- **Exact JSON:** `SKILL/api.sh GET <path>` prints the response (exits non-zero on HTTP ≥ 400):
  - `/api/projects/1/workbook` - project (name, `description`) and workspaces. The canvas is `defaultWorkspaceId` (2).
  - `/api/projects/1/workspaces/2` - **the main document**: `revision`, `items`, `placements`, `assignments`, `connections`.
  - `/api/inventory/items/<type>/<id>/metadata` - one item's custom field values and tags.
  - `/api/inventory-metadata/catalog` - custom field definitions and tags.
  - `/api/health` - `persistence.database.integrity` should be `"ok"`.
- Pipe through `jq`, e.g. `SKILL/api.sh GET /api/projects/1/workspaces/2 | jq '.items["server:1"]'`.

## 3. Data model

Items are keyed by **runtime key** `"<type>:<id>"` (`server:1`, `switch:3`). The
id is per type and assigned by the app, so find items by **name** (`findItem`),
never by guessing ids.

**Equipment types** (shown as cards on the canvas): `server`, `nas`, `pcBuild`,
`switch`, `patchPanel`, `monitor`, `ups`, `powerStrip`.
**Component types** (assigned into a host): `cpu`, `ram`, `storage`, `gpu`,
`network`, `motherboard`, `cpuCooler`, `case`, `powerSupply`, `soundCard`, `powerAdapter`.
The app has no router, AP or laptop type. Here routers and APs are `switch`, and
laptops / TV box are `server` with `usageRole` `workstation` / `other`.

Item fields: `name`, `manufacturer`, `model`, `family`, `number`,
`secondaryManufacturer`, `aliases`, `notes` (newlines kept), `specs`, `ports`,
`compatibility`; servers also `hardwareClass` (`desktop|workstation|server`) and
`usageRole` (`server|desktop|workstation|other`).

`specs` keys per type (values the UI offers in brackets):

| type | keys |
| --- | --- |
| server | `formFactor` [Tiny, Mini, Micro, Compact, Small, SFF, Tower, Rack Server, Mini-ITX, Micro-ATX, ATX, …], `networkSlot` [On board, PCIe, M.2 A+E], `wireless` [Yes, No] |
| switch | `management` [Unmanaged, Smart / Web-managed, Layer 2 Managed, Layer 2+ Managed, Layer 3 Managed, Controller / Cloud-managed], `switchingCapacityGbps`, `fanless` (bool) |
| pcBuild | `operatingSystem`, `role` |
| cpu | `cores`, `threads`, `baseClockGhz`, `boostClockGhz` (+ `family`, `number` fields) |
| ram | `capacityGb`, `generation` [DDR3, DDR3L, DDR4, DDR5, LPDDR4, LPDDR5], `formFactor` [SO-DIMM, DIMM, LP-DIMM, Onboard], `moduleType`, `speedMt`, `ecc`, `rank`, `voltageVolts` |
| storage | `capacityGb` **or** `capacityTb`, `interface` [NVMe, SATA, SAS, eMMC, USB], `formFactor` [2230, 2242, 2260, 2280, 2.5", 3.5", eMMC] |
| gpu | `vramGb`, `formFactor`, `slotWidth`, `pcie` [PCIe 4.0 x16, …] |
| motherboard | `chipset`, `formFactor`, `boardRevision`, `wifiGeneration`, `bluetooth` |
| nas | `driveBays`, `m2Slots`, `formFactor`, `platformFamily`, `powerConfiguration` [internal-psu, external-adapter], … |

**Ports** live on the item: `{ id, slotNumber, kind, type, speed, role, label, notes }`.
- `kind`: `switch-port` on switches, `server-port` on servers/NAS, `network` on
  motherboards and NICs, `video` for HDMI/DP, `keystone` on patch panels.
- `type`: `rj45`, `sfp`, `sfp-plus`, `hdmi`, `displayport`, …; `speed`: `1G`, `2.5G`, `5G`, `10G` (or omit).
- `role`: `access` | `uplink` | `trunk` | `management` | `disabled`. The audit
  wants one `uplink` on every switch that has cables.
- `id` is stable and is what cables reference; `slotNumber` is the position
  shown as "port N". Keep existing ids when editing ports. New ports get
  `max(id)+1`, unique `slotNumber`.
- `label` convention here: the OS interface name (`enp1s0`); `notes`: `MAC …`.

**Canvas** (all inside the workspace document):
- `placements`: `{ serverId: key, x, y }` for equipment on the canvas.
- `assignments`: `{ id, serverId: hostKey, itemId: componentKey, type, assignedAt }`.
- `connections`: `{ id, from, to, type: network|power|display|other, negotiatedSpeedBps, label, createdAt }`.
  Each endpoint is `{ itemId, portId }`, or for a port on a PC build's motherboard
  or on an assigned NIC/GPU `{ itemId: hostKey, portId, hostedItemId: componentKey }`.
  A port takes **one** cable; a second one fails with a UNIQUE constraint error.

**Custom fields** (catalog, apply to `server`, `pcBuild`, `switch`): `Hostname`,
`IP Address`, `OS`, `SSH User`, `Services`. **Tags**: `Network Infrastructure`,
`Core Server`, `Workstation`, `Client`. The project `description` holds the IP schema.

## 4. Editing

Write a small script and run it with `SKILL/run.sh script.mjs`. `run.sh`
prepends `SKILL/lib.mjs`, so these helpers are available directly:

| helper | does |
| --- | --- |
| `findItem(name, type?)` | current item by exact name; throws if missing/ambiguous |
| `updateItem(key, input => {...})` | copies the **current** item, lets you mutate it, PUTs it |
| `createItem(input)` | creates a project item, returns its new key |
| `getMetadata(key)` / `setMetadata(key, {values, tags})` | read / **merge** custom fields (`null` clears one); `tags` replaces the tag list |
| `catalog()` | `{fields, tags}` by name |
| `updateCanvas(state => {...})` | mutate placements/assignments/connections; sends the read `revision` |
| `assign(hostKey, [componentKeys])` | attach components to a host |
| `connect(fromEndpoint, toEndpoint, {speedBps, label})` | add a cable |
| `snapshot()` / `api(method, path, body)` / `workspace()` | raw access |

Example: fill in a host and give it a CPU:
```js
const host = await findItem('home-media', 'server')
const before = JSON.parse(await snapshot())
await updateItem(host.key, (item) => {
  item.model = 'ProDesk 400 G3 DM'
  item.ports.find((p) => p.label === 'enp1s0').notes = 'MAC aa:bb:cc:dd:ee:ff'
})
await setMetadata(host.key, { values: { OS: 'Debian 13 (trixie)' } })
const cpu = await createItem({ type: 'cpu', name: 'Intel Core i7-6700T', manufacturer: 'Intel',
  family: 'Core i7', number: '6700T', specs: { cores: 4, threads: 8, baseClockGhz: 2.8, boostClockGhz: 3.6 } })
await assign(host.key, [cpu])
const after = JSON.parse(await snapshot())
// prove nothing else moved (see step 5)
console.log(Object.keys(before.items).filter((k) => k !== host.key)
  .every((k) => JSON.stringify(before.items[k]) === JSON.stringify(after.items[k])))
```

Other operations:
- **Rename**: `updateItem(key, (i) => { i.name = 'new' })`. It changes only the
  app, not `inventory/hosts.yml`, DNS or Caddy, unless the user asks for those too.
- **Move on canvas**: `updateCanvas((s) => { s.placements.find((p) => p.serverId === key).x = 800 })`.
  Cards are ~280 wide; a server card with components is ~500 tall.
- **New custom field / tag**: `api('POST', '/api/inventory-metadata/definitions', { name, fieldType: 'shortText', applicableItemTypes: ['server','pcBuild','switch'] })`;
  `api('POST', '/api/inventory-metadata/tags', { name, colorToken: 'blue' })`. Field types:
  `shortText longText number boolean date dateTime singleSelect multiSelect url`.
- **Project description**: `api('PATCH', '/api/projects/1', { description })`.
- **Archive / delete an item**: `POST /api/inventory/items/<type>/<id>/archive` or
  `DELETE /api/inventory/items/<type>/<id>`. **Ask the user first.**

Naming conventions already in the data: hosts use their real hostname
(`home-edge`, `macmom`); identifiable parts use the product name
(`Samsung MZVLQ512HALU 512GB`); generic parts are `<host> <size> <kind>`
(`home-edge 8GB DDR3L`).

## 5. Safety rules

1. **Targeted writes only.** Never re-run a bulk import or rewrite items you
   weren't asked to change. On 2026-09-13 a bulk re-run silently reverted the
   user's gateway edits and had to be recovered from the WAL.
2. **Read → mutate → write** every time, via the helpers. `PUT item` and
   `PUT metadata` **replace** the whole thing; the helpers merge on top of a fresh read.
3. **Revision conflicts are good.** `updateCanvas` sends the revision it read. A
   `409 … revision N is stale` means the user changed the canvas meanwhile. Re-read
   and redo; never force.
4. **Before writing more than one item**, take a backup:
   `ssh home-edge 'tar czf ~/homelab-inventory-$(date +%Y%m%d-%H%M%S).tgz -C ~/*/homelab-inventory .'`
   and tell the user its path.
5. **Confirm first** before deleting/archiving, renaming something the user named,
   changing tags they set, or anything outside the app.
6. Record measured facts, and say where each came from. Mark guesses as guesses in
   `notes` (e.g. "Port count assumed (5)"), and leave fields blank rather than invent.
7. Keep serial numbers and hardware UUIDs out. MACs and IPs are fine (the user wants them).

## 6. Quirks (app 0.16.14)

- **Port `ipAddress` is only saved when an item is created**, and any later
  `PUT` of the item drops it. Put IPs in the `IP Address` custom field.
- **Custom field values collapse all whitespace**, longText included. Separate
  list entries with ` · `. Item `notes` keep newlines.
- The Systems table's OS / LAN IP columns only fill from the app's monitoring
  agent (not installed), which is why the custom fields exist.
- PC-build motherboard cables (`hostedItemId`) show a false "Saved connection points
  to a port that no longer exists" audit warning; the UI itself creates them the same way.
- Other expected audit warnings: "needs an assigned power adapter/supply" (power
  isn't modelled) and "Switch has active connections but no uplink" for the gateway.
- Port speeds accept only `1G 2.5G 5G 10G`; a real 100 Mb/s link goes on the
  cable's `negotiatedSpeedBps` (`1e8`), not the port.
- **On create the app renumbers port ids**, and for `monitor`, `nas`, `powerAdapter`,
  `powerSupply`, `ups`, `powerStrip` it adds its own power ports (monitor: `AC input`
  in slot 1). Give your ports free slots (monitor: start at 2), then look them up
  **by label** after `createItem` before cabling.
- **Monitor `sizeInches` must convert to whole millimetres** (34″ = 863.6 mm fails
  with a 500 "Canonical conversion from in would lose precision"). Leave it empty
  and put the size in `model`.
- Monitors: display inputs are `kind: 'video'` ports (`hdmi`, `displayport`); the
  cable is `type: 'display'` from the GPU's hosted port. Custom fields don't apply to monitors.
- Opening a *copy* of the DB with `sqlite3` checkpoints and deletes the copy's WAL.
  Copy the three files into a separate folder first.

## 7. Check the result

1. Re-read what you changed (`workspace()`, `getMetadata`) and show the user the new values.
2. Diff `snapshot()` before vs after: every item, placement, assignment and
   connection you did not mean to touch must be byte-identical.
3. `SKILL/api.sh GET /api/health | jq .persistence.database.integrity` → `"ok"`.
4. `just inventory-dump` and read the affected section of `tmp/inventory.md`.
5. For layout changes, check visually in a sandbox (step 8) or ask the user to look.

## 8. Gathering facts, sandbox, recovery

**Hardware facts.** home-edge, home-media and home-desktop are reachable over SSH:
`ssh <host> bash -s < SKILL/facts.sh` (read-only, no sudo). It covers DMI model,
CPU, RAM, disks, NICs with MAC / link speed / `carrier_changes` (link drops), IPs and GPU VRAM.
The laptops (matebook, macmom) are usually not reachable. Give the user a
command to run and paste back; the commands used on 2026-09-13 were
`system_profiler SPHardwareDataType SPMemoryDataType SPDisplaysDataType SPAirPortDataType` (filter
`Serial|UUID|UDID`, cut `Other Local Wi-Fi Networks`) + `diskutil info disk0` +
`networksetup -listallhardwareports` on macOS, and `hostnamectl`, `lscpu`, `free -h`,
`lsblk -d -e7 -o NAME,MODEL,SIZE,ROTA,TRAN`, `lspci -nn`, `ip -br link/addr`, `iw dev <if> link` on Arch.

**Monitors** identify themselves by EDID. On home-desktop (the local machine), use
`edid-decode /sys/class/drm/card*-<connector>/edid` for connected connectors (the
sysfs file reports size 0, so don't test it with `-s`) and `hyprctl monitors` for
the current mode. The manufacturer code + product id (e.g. `XMI 3446`) and the
"Made in" week/year settle which model it is; user-given model names can be wrong.
Look up web specs for anything the user names, cite them, and prefer the vendor
page. Values derived rather than published (e.g. switching capacity from port
count) go in `notes` as derived.

**Sandbox** (for risky or many-item changes): run the same image on a copy of the data, then point the helpers at it.
```sh
S=<scratch dir>; mkdir -p $S/sb
ssh home-edge 'cd ~/*/homelab-inventory && tar cf - .' | tar xf - -C $S/sb
IMG=$(ssh home-edge 'docker inspect $(docker ps -q --filter name=homelab-inventory) --format "{{.Config.Image}}"')
docker run -d --name hi-sb --user "$(id -u):$(id -g)" -e TRUST_PROXY=1 -e LABGD_ENABLED=false \
  -p 127.0.0.1:18798:8798 -v $S/sb:/data "$IMG"
cat SKILL/lib.mjs script.mjs > $S/full.mjs && INVENTORY_BASE=http://127.0.0.1:18798 node $S/full.mjs
docker rm -f hi-sb; rm -rf $S/sb   # the copy includes auth tables
```
For screenshots, use `playwright-core` with `executablePath: '/usr/bin/chromium'`;
the fit-to-view button is bottom-left of the canvas.

**Recovery.**
- *Whole app*: scale the service to 0, untar a backup into the data dir, then scale back to 1.
- *One overwritten item*: the WAL usually still holds its previous version. Copy
  the three DB files into a scratch folder. Walk the WAL frames (32-byte header,
  frames of 24 + page_size, a commit frame has a non-zero "db size"). Truncate a
  copy of the WAL just after each commit, and find the last commit before the bad
  write (`inventory_items.updated_at_ms`). Boot the sandbox on that snapshot, `GET`
  the item as JSON, and `PUT` it back to production with `updateItem`.

## 9. When something doesn't match

The source is `github.com/mriverodorta/homelab-inventory`. Check out the deployed
revision (`APP_REVISION` in the container env). Useful places: `server/*-routes.mjs`
(endpoints), `server/persistence/sqlite-store.ts` (`setProject`, item create/update),
`src/types/inventory.ts` (shapes), `src/components/inventory-form/model.ts`
(`KNOWN_SPEC_KEYS`, ports), `src/components/inventory-form/options.ts` (allowed values),
`src/lib/audit.ts` (warnings). If you learn something new, update this skill.

## 10. Report

Say what changed, item by item, with the new values. Say where each fact came
from (the user, SSH facts, a pasted dump) and what you guessed. Mention any new
audit warnings, any backup you took, and anything you left undone.
