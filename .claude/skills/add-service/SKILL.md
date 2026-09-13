---
name: add-service
description: Add a new self-hosted service to the home Docker Swarm stack (roles/docker/deploy-docker-swarm) - compose file, enabled_services, data dirs that the restic backup picks up, config, Caddy route, Authelia, Cloudflare DDNS records in SOPS, Gatus check and Glance link. Use when the user types /add-service or says "add service <name>" / "add <name> to the swarm", usually with a GitHub link.
argument-hint: "<name> [github-url]"
allowed-tools: [Bash, Read, Edit, Write, Glob, Grep, WebFetch, AskUserQuestion]
---

# /add-service - add a service to the home swarm

`$ARGUMENTS` is `<name>` and usually a GitHub URL. If there is no URL, find the
upstream repo from the name and confirm it with the user before going on.

All paths below are relative to the repo root. `ROLE` means
`roles/docker/deploy-docker-swarm`.

The most recent service added end to end is **homelab-inventory**, in commit
`ef27948`. Run `git show ef27948` whenever a step is unclear. It touches every
file this skill touches except OIDC. Existing services are the source of truth.
If a neighbour disagrees with this file, follow the neighbour and say so.

---

## 1. Research upstream first

Read the repo README, its example `docker-compose.yml` or `compose.yaml`, and its
docs. Use WebFetch against `github.com` and `raw.githubusercontent.com`. Collect:

- **Image**: the one upstream publishes (Docker Hub, `ghcr.io`, `lscr.io`), plus
  the tag it recommends (`latest`, `stable`, a major). This is what makes the
  compose "trusted": it's upstream's own image. If only a third party publishes
  one, say so and ask. If there is no image at all, stop and report. Don't add a
  build step.
- **Internal port** of the web UI.
- **Persistent paths** in the container (`/config`, `/data`, a DB dir).
- **Runtime user**: does it take `PUID`/`PGID`, `user:`, or insist on its own
  uid? Remember homelab-inventory needed `user: "{{ puid }}:{{ pgid }}"`.
- **Sidecars**: postgres, redis, workers.
- **Reverse-proxy settings**: external/base URL, trusted proxies, and anything
  that breaks behind TLS termination. homelab-inventory needed `TRUST_PROXY`.
- **Health endpoint**, such as `/health`, `/api/health`, `/ping` or
  `/healthcheck`, and what it returns.
- **Auth**: built-in login, OIDC/OAuth2 support (env var names, redirect URI
  path), or none.
- **First-run side effects** that can't be undone later, like LABGD_ENABLED in
  homelab-inventory.

## 2. Resolve the open decisions

Ask them in **one** AskUserQuestion call. Put your recommendation first, based
on what step 1 found.

1. **Node**
   - `home-edge`, the swarm manager: infra, dashboards, general apps.
     Placement `"node.role == manager"`.
   - `home-media`: anything that needs `/mnt/storage` or transcoding.
     Placement `"node.hostname == {{ hostname_media }}"`.
2. **Access / Authelia**
   - *Forward auth*: Authelia gates the whole host (one_factor). Use it for apps
     with weak or no auth of their own. The arr apps and inventory do this.
   - *OIDC*: the app logs in via Authelia SSO itself. Use it when upstream
     supports OIDC. Beszel and UpSnap do this.
   - *App's own auth*: no Authelia. Jellyfin and wg-easy do this.
   - *Public, no auth*: only for things meant to be public.
3. **Exposure**
   - Public: `<name>-home.{{ public_top_domain }}` plus a LAN route (default).
   - LAN only.
   - Public only.
   - Keep hosts to one label under `public_top_domain`. That's why it is
     `name-home`, not `name.home`: the certbot wildcard cert and Cloudflare's
     proxy cert only cover one level.
4. **Dashboard group**: pick the Gatus group and Glance group together.
   - Gatus: `50 - Public`, `51 - Infra Management`, `52 - Media`, `53 - Other`.
   - Glance, in `home-network.yml` bookmarks: `Public`, `Local tools`,
     `Infra Management`, `Other`.
   - The usual pairs are edge infra → 51 / Infra Management, media →
     52 / Local tools, and general apps → 53 / Local tools.

Don't ask things you can decide yourself, like the internal port, image, or
volume paths. Mention them in the final report instead.

## 3. Make the changes

Work through the list in order. Read each target file before editing and put the
new entry next to its closest neighbours, not at the end of the file.

### 3.1 Compose file: `ROLE/templates/compose/<name>.yml.j2`

The file is included inside the `services:` map of
`templates/docker-compose.yml.j2`. Follow these rules:

- Start with the line `# services:`. Indent the service key by 2 spaces.
- `networks: [local_net]`. Add `dns: ["{{ local_dns }}"]` if it resolves
  anything on the LAN.
- `deploy.replicas: 1` and the placement constraint from decision 1.
- `TZ: "{{ tz }}"`, with `PUID`/`PGID` or `user: "{{ puid }}:{{ pgid }}"` as
  the image supports.
- **No `ports:`**. Caddy reaches the service over `local_net` by service name.
  The exception is non-HTTP traffic that must hit the host (see
  transmission/wg-easy).
- Secrets come from SOPS vars (`{{ admin_pass }}`, `{{ db_postgres_user }}`,
  and so on), never literals.
- Sidecar DB: `<name>_db` on `postgres:17.5`, same as `rss.yml.j2` and
  `gatus.yml.j2`.
- Comment only the non-obvious env, and say *why*, like homelab-inventory does.

### 3.2 Enable it: `ROLE/defaults/main.yml`

Add `<name>` to `enabled_services` under the right comment block (`# Edge`
or `## Media`). The key must equal the compose filename without `.yml.j2`.

### 3.3 Storage, which is what backup depends on

`compose/backup.yml.j2` runs restic on each node over **`{{ remote_data }}`
and `{{ remote_config }}` only**. So:

- State → `{{ remote_data }}/<name>` (sub-dirs like `<name>/db` for sidecars).
- Config → `{{ remote_config }}/<name>` (see 3.4).
- No named volumes and no paths outside those two roots, or the data won't
  get backed up. Bulk media on `/mnt/storage/Media` is the one deliberate
  exception.
- Mount **directories, not single files**. Ansible replaces templated files by
  rename, and a file bind mount keeps the old inode. The comment in
  `caddy.yml.j2` explains this.

Swarm won't start a service whose bind-mount source is missing, so pre-create
the data dirs in `ROLE/tasks/main.yml`, right after the homelab-inventory task:

```yaml
- name: Ensure <Name> data directory exists
  # Swarm rejects a missing bind mount source.
  ansible.builtin.file:
    path: "{{ remote_data }}/<name>"
    state: directory
    mode: "0755"
  when: "'<name>' in enabled_services"
```

- **Media node**: this play only runs on the manager (`home-edge`), so add
  `delegate_to: home-media` to the task. No existing task does this yet, so
  point it out in the report.
- **Images that chown their volume** (postgres, redis): copy the Authelia
  pattern instead, which is `stat` first and create only when absent.

### 3.4 Config files, only if the app needs a config file

- Static file, where the app does its own `${ENV}` interpolation (gatus and
  glance do): put it in `ROLE/templates/config/<name>/`. It is rsynced to
  `{{ remote_config }}` with `delete: true`.
- File that needs Ansible vars or secrets: put it in
  `ROLE/templates/config.j2/<name>/<file>.j2`, and do both of the following:
  - Add `{folder: <name>, file: <file>}` to the "Template config files" loop
    in `tasks/main.yml`, or give it its own task with a restart handler if the
    app doesn't hot-reload. See `Restart Authelia` in `handlers/main.yml`.
  - Create `ROLE/templates/config/<name>/.keep`. The rsync `delete: true` would
    otherwise remove the directory the template renders into. caddy and
    authelia have `.keep` for this reason.
- Mount it as `{{ remote_config }}/<name>:<container dir>`, as a directory.

### 3.5 Caddy: `ROLE/templates/config.j2/caddy/Caddyfile.j2`

Add a `### <Name>` block in the right section (edge block or `## Media`):

```caddy
### <Name>
<name>-home.{{ public_top_domain }} {
    import my_tls
    import authelia_auth          # only for forward auth
    reverse_proxy <service>:<port>
}
<name>.{{ local_media_domain }}:80 {   # edge services use top_local_domain
    reverse_proxy <service>:<port>
}
```

LAN routes never import `authelia_auth`, which matches the existing ones.

### 3.6 Authelia

- **Forward auth**: add `<name>-home` to `authelia_protected_hosts` in
  `defaults/main.yml`. The Caddy `import authelia_auth` and this list must
  always agree. A host listed in one but not the other is either left open or
  gets a hard deny, because `default_policy: deny`.
- **OIDC**:
  1. Add an entry to `authelia_oidc_clients` in `defaults/main.yml`, with
     `key: <name>`, the display name, `redirect_uris` from upstream docs using
     the public host, and scopes.
  2. Generate the credentials without printing them. Use the Authelia CLI:
     `docker run --rm authelia/authelia:latest authelia crypto hash generate
     pbkdf2 --variant sha512 --random --random.length 72 --random.charset
     rfc3986`. It prints the random password and its digest.
  3. Store the credentials under key `<name>` in three SOPS dicts:
     `authelia_oidc_client_ids`, `authelia_oidc_client_secrets` (plaintext,
     for the app) and `authelia_oidc_client_secret_hashes` (digest, for
     Authelia). Pipe the values into
     `sops set --value-stdin vars/docker_swarm.sops.yml
     '["authelia_oidc_client_secrets"]["<name>"]'` so no secret lands on
     argv or in this transcript.
  4. Wire the app env with `{{ authelia_oidc_client_ids['<name>'] }}` and
     `{{ authelia_oidc_client_secrets['<name>'] }}`. Issuer:
     `https://auth.{{ public_top_domain }}`.
  5. Before writing, confirm the dict shapes by listing keys only:
     `sops -d --extract '["authelia_oidc_client_ids"]' vars/docker_swarm.sops.yml | cut -d: -f1`.
     Never print SOPS values.
  - Don't stack forward auth on top of OIDC.

### 3.7 DNS / DDNS: `vars/docker_swarm.sops.yml`

`compose/ddns.yml.j2` creates Cloudflare records from two comma-separated
lists of subdomain labels. Public exposure needs the host in one of them:

- `cloudflare_proxied_domains` (orange cloud) is the default for anything
  served by Caddy over HTTPS.
- `cloudflare_managed_domains` (DNS only) is for non-HTTP or non-443
  traffic, or when the Cloudflare proxy must be bypassed (like `wg-home`,
  `proxy`, `dns`).

These are hostnames, not secrets, so read, check for duplicates, and append:

```bash
f=vars/docker_swarm.sops.yml; k=cloudflare_proxied_domains
cur=$(sops -d --extract "[\"$k\"]" "$f")
case ",$cur," in *",<name>-home,"*) echo "already present";; *)
  sops set "$f" "[\"$k\"]" "\"$cur,<name>-home\"";; esac
sops -d --extract "[\"$k\"]" "$f"   # verify
```

LAN-only services need no DNS change.

### 3.8 Gatus: `ROLE/templates/config/gatus/config.yaml`

Add an endpoint in the chosen group, next to its group-mates:

```yaml
  - name: <Name>
    url: http://<service>:<port><health>          # edge: service name
    # url: http://<name>.${LOCAL_MEDIA_DOMAIN}<health>   # media: LAN route, like the arrs
    interval: 1m
    group: <group>
    conditions:
      - "[STATUS] == 200"
      # plus a body check if the endpoint returns one, e.g. "[BODY].status == OK"
    alerts:
      - type: pushover
```

Gatus can only use env vars that are passed in `compose/gatus.yml.j2`. Add a
new one there if you need it.

### 3.9 Glance: `ROLE/templates/config/glance/config/home-network.yml`

Add a link to the chosen bookmarks group:

```yaml
                - title: <Name>
                  description: <few words>
                  url: https://<name>-home.${PUBLIC_TOP_DOMAIN}
                  icon: sh:<slug>
```

Check that the selfh.st icon exists before using it:
`curl -sfI https://cdn.jsdelivr.net/gh/selfhst/icons/png/<slug>.png`. If it
doesn't, fall back to a fitting `mdi:` icon.

## 4. Verify

- Plain YAML parses:
  `python3 -c 'import sys,yaml; [yaml.safe_load(open(p)) for p in sys.argv[1:]]' ROLE/templates/config/gatus/config.yaml ROLE/templates/config/glance/config/home-network.yml`
- Check consistency with greps. The service name must appear in
  `enabled_services`, in the compose filename and in the Caddy upstream. The
  forward-auth host must be in both the Caddyfile and
  `authelia_protected_hosts`. The public host must be in a DDNS list.
- `just lint` if `.venv` exists.
- Review `git diff` end to end.

**Don't deploy.** It changes live DNS and restarts the stack. Offer
`just run-tags home-server` and let the user run it.

## 5. Report

Keep it short. Cover:

- Decisions taken, and anything you chose yourself (image and tag, port,
  volumes, health endpoint).
- Upstream gotchas you worked around, and why.
- Manual steps left, such as first-run setup in the UI, the app-side OIDC
  settings if they aren't configurable through env, and deploying.

Leave committing to `/cm`.
