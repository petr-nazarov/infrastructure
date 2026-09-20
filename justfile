init:
  python -m venv .venv
  . .venv/bin/activate
  pip install ansible ansible-lint docker
  pip install 'resolvelib<1.1.1,>=0.5.3'
  ansible-galaxy install -r requirements.yml
source:
  . .venv/bin/activate
# Run all linters and formatters
lint:
    ansible-lint
    yamllint . 
lint-fix:
    ansible-lint --fix
    yamllint . 

format:
    taplo fmt
    shfmt -w .
    yamlfmt roles/docker/deploy-docker-swarm/templates/config
    yamlfmt roles/docker/deploy-docker-swarm/templates/config.j2

fix:
  just lint-fix
  just format
ci:
  dagger call lint --source .
run-tags tags:
  ansible-playbook -i inventory/hosts.yml --tags {{ tags }} main.yml
  just notify "Infrastructure applied for tags {{ tags }}"

run host: source
  ansible-playbook -i inventory/hosts.yml -l {{ host }} main.yml
  just notify "Infrastructure applied for {{ host }}"

# Sync the config dir and restart Glance + Gatus, skipping the full stack deploy
dashboards:
  .venv/bin/ansible-playbook -i inventory/hosts.yml -l docker-swarm-managers --tags dashboards main.yml
  just notify "Dashboards reloaded"

# Dump the homelab inventory (inventory-home) as Markdown for LLMs
inventory-dump:
  mkdir -p tmp
  ssh home-edge 'docker run --rm -i --quiet --network home_local_net node:24-alpine node --input-type=module -' < scripts/inventory-dump.mjs > tmp/inventory.md
  @echo "Wrote tmp/inventory.md"

[linux]
notify message:
  paplay /usr/share/sounds/freedesktop/stereo/window-attention.oga
  notify-send "Done" "{{ message }}"
[macos]
notify message:
  afplay /System/Library/Sounds/Glass.aiff
  osascript -e 'display notification "{{ message }}" with title "Done"'
