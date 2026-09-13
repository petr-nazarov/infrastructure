# Handover: macos-workstation-setup

2026-09-13 12:02 · infrastructure (+ dotfiles) · branch `feat/macos-workstation` in both repos · HEAD `da75396` (infrastructure), `f7f8277` (dotfiles)

## Goal

Set up the new MacBook Air (macOS 15.7, arm64) the same way the Arch workstations are: Ansible roles in this repo, driven by `just run <host>`, with dotfiles synced by stow. The mac is host `macbook` in a new `mac-workstations` group. It is its own controller (`ansible_connection: local`).

## Current state

Written and statically checked, but **never run for real**. Homebrew is not installed on the mac yet, so no role past the Homebrew check has run.

Verified in this session, using a throwaway ansible-core 2.15 and community.general 9.5 venv:
- `ansible-playbook -i inventory/hosts.yml main.yml --syntax-check` passes.
- `yamllint roles/darwin` is clean. `ansible-lint --offline -p` reports nothing under `roles/darwin/`. Its other findings were already there before this branch.
- `ansible -i inventory/hosts.yml macbook -m ping` works over the local connection. The inventory loads for `macbook` without the age key, because sops only decrypts the hosts in scope.
- `darwin/preferences` ran in `--check --diff`: 14 items would change.
- `darwin/base` stops with the "Homebrew is not installed" message, as intended.
- The `darwin/docker` merge into `~/.docker/config.json` ran against temp homes: it creates the file when missing, keeps existing keys, and a second run reports `changed=0`.
- All formula and cask names were checked against the formulae.brew.sh API. `zen` is the cask name and it installs `Zen.app`. `mpv` is a formula, not a cask.

Not tested at all: the brew installs, the `homebrew_cask` `sudo_password` path, the netbird cask postflight, the yabai sudoers entry, the Colima brew service, `mise install`, and the hostname task (`scutil`).

`inventory/host_vars/macbook.sops.yml` was created by the user. A structural check showed `ansible_become_password` is `ENC[...]`, there are no plain values, and the recipient is `age1dkl6...` (matches `.sops.yaml`). It was not decrypted, because `sops` was not on PATH in this session.

User decisions made this session:
- The age key stays at `~/.secrets/enc-keys/personal`. `~/.secrets/secrets.zsh` already exports `SOPS_AGE_KEY_FILE`, so there is no copy step.
- Docker comes from Colima, not OrbStack.
- Work stays on branches, uncommitted and unpushed. The user chose "handover only".

## Changed files

Uncommitted, infrastructure:
- `README.md` - new "Managed node macOS" section: prerequisites, `~/.secrets` for the age key, `EDITOR=vim sops ...`, and the manual yabai steps.
- `inventory/hosts.yml` - `mac-workstations` group with host `macbook`.
- `inventory/host_vars/macbook.yml` - `ansible_connection: local`, `ansible_python_interpreter: "{{ ansible_playbook_python }}"`.
- `inventory/host_vars/macbook.sops.yml` - encrypted `ansible_become_password`, created by the user. Casks with pkg installers need it for sudo.
- `justfile` - the `run` and `run-tags` recipes call a new `notify` recipe, with a `[linux]` variant (paplay/notify-send) and a `[macos]` variant (afplay/osascript).
- `main.yml` - new play "Setup mac workstations" running the darwin roles.
- `vars/terminal_packages.yml` - adds `darwin_specific_packages` and `darwin_skip_packages`. The skip list covers `common_packages` entries that Homebrew names differently or macOS already ships.
- `roles/darwin/base` - Homebrew check, check that the become password is set, `brew update`, base formulae, hostname set via `scutil`.
- `roles/darwin/term_packages` - Homebrew version of `arch/term_packages`, using the shared vars file.
- `roles/darwin/developer_env` - mise from brew, stops if the dotfiles aren't synced, `mise install`, tpm, claude.
- `roles/darwin/preferences` - `osx_defaults` list: key repeat, Finder, Dock, and the Spaces settings yabai needs. The role was first called `defaults`, which ansible-lint misreads as a vars path, so it was renamed.
- `roles/darwin/yabai` - yabai, skhd, choose-gui; a sudoers entry pinned to the yabai binary's sha256 for `--load-sa`; `--start-service` for both.
- `roles/darwin/gui_apps` - casks: ghostty, zen, opera, obsidian, qbittorrent, localsend, iina, anydesk, studio-3t, dbeaver-community, fonts. Plus the `mpv` formula.
- `roles/darwin/docker` - colima, docker, docker-compose, docker-buildx; `homebrew_services` starts colima; `cliPluginsExtraDirs` is merged into `~/.docker/config.json`.
- `roles/darwin/netbird` - cask `netbirdio/tap/netbird-ui`, which pulls in the formula and the launchd daemon.
- `docs/handover/2026-09-13-1202_macos-workstation-setup.md` - this file.

Uncommitted, dotfiles (`~/dotfiles`, same branch name):
- `justfile` - `rm -f $HOME/.zshrc`, because a plain `rm` failed on a fresh mac. `sync-common-gui` no longer skips macOS, which never sets DISPLAY/WAYLAND_DISPLAY.
- `_mac_gui/.skhdrc` - Zen path changed from `Zen Browser.app` to `Zen.app`, to match the cask.
- `README.md` - "Bootstrap (bare macOS)" section.

Committed this session: none.

## Next step

In a normal terminal on the mac, install Homebrew and the prerequisites:
`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" && eval "$(/opt/homebrew/bin/brew shellenv)" && brew install gh just stow mise sops age`

After that: move `~/.claude/settings.json` aside (it is only `{"theme": "dark"}` and would block stow), run `cd ~/dotfiles && just sync`, open a new shell, then set up the control node venv (below) and run `just run macbook`.

### Control node venv

Use these commands rather than `just init`. Each justfile line runs in its own shell, so the `. .venv/bin/activate` line in `init` has no effect: pip installs into mise's Python instead of `.venv`. The `source` recipe that `run` depends on is a no-op for the same reason.

```bash
cd ~/infrastructure
mise trust && mise install          # python, just, dagger... from mise.toml
python -m venv .venv
source .venv/bin/activate
pip install ansible ansible-lint docker 'resolvelib<1.1.1,>=0.5.3'
ansible-galaxy install -r requirements.yml
```

In every new shell, run `source .venv/bin/activate` before `just run macbook`. `macbook.yml` sets `ansible_python_interpreter` to `ansible_playbook_python`, so modules run with this venv's Python. `.venv` is already in `.gitignore`.

## Blockers & open decisions

- Homebrew's installer needs the user's sudo password interactively, so the user has to run it.
- Unanswered: OrbStack covered Linux VMs and Colima does not. Should UTM be added as the counterpart of `arch/virtualization`?
- The `darwin_preferences` list was chosen by Claude, not the user. It needs their review.
- The hostname will change from `MacBook-Air` to `macbook` (via `darwin_base_hostname`). The user was told but did not explicitly confirm.
- Manual steps macOS won't allow Ansible to do: Accessibility permission for yabai and skhd, and partially disabling SIP for the yabai scripting addition (space focus/move bindings).
- The justfile's `init` and `source` recipes don't activate the venv (see "Control node venv"). They could be fixed with `export PATH := justfile_directory() / ".venv/bin:" + env("PATH")` at the top of the justfile, but that also changes the Arch flow, so it hasn't been done.
- Colima runs with its default VM size (2 CPU / 2 GB). This may be too small, and was not discussed.
- Nothing is committed or pushed in either repo. This handover exists only on this mac.

## How to verify

In `~/infrastructure` with the venv or mise python active:
- `ansible-playbook -i inventory/hosts.yml main.yml --syntax-check` should print only `playbook: main.yml`.
- `ansible-lint --offline -p | grep '^roles/darwin'` should print nothing.
- `EDITOR=vim sops inventory/host_vars/macbook.sops.yml` should open and show `ansible_become_password`.
- `just run macbook` should end with `failed=0`. Then `docker compose version` should work, and `docker context ls` should show `colima` as the active context. Running `just run macbook` a second time should report no changes except the `mise install` and `brew update` tasks.
