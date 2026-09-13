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

[linux]
notify message:
  paplay /usr/share/sounds/freedesktop/stereo/window-attention.oga
  notify-send "Done" "{{ message }}"
[macos]
notify message:
  afplay /System/Library/Sounds/Glass.aiff
  osascript -e 'display notification "{{ message }}" with title "Done"'
