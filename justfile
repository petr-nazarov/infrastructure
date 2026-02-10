init:
  python -m venv .venv
  . .venv/bin/activate
  pip install ansible ansible-lint
  pip install 'resolvelib<1.1.1,>=0.5.3'
  ansible-galaxy install -r requirements.yml
source:
  . .venv/bin/activate
# Run all linters and formatters
lint:
    stylua --check .
    taplo fmt --check
    ansible-lint

format:
    stylua .
    taplo fmt
    shfmt -w .
    yamlfmt .
fix:
  just format
  git add .
  just lint
  git add .

ci:
  dagger call lint --source .

run host: source
  ansible-playbook -i inventory/hosts.yml -l {{ host }} main.yml 
