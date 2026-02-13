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

run host: source
  ansible-playbook -i inventory/hosts.yml -l {{ host }} main.yml 
