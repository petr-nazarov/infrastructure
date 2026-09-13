# Controll node
## Install dependencies
```bash
mise install
just init
```



## Run like this:
```bash
just run HOST
```

# Managed node arch
```bash
sudo pacman -Sy --needed openssh python python-pip sops age 
sudo systemctl enable --now sshd
```
# Managed node macOS
Macs are in the `mac-workstations` group, named after their hostname (e.g. `macmom`).
Each mac is its own controller (`ansible_connection: local`), so everything runs on the mac itself.
```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install gh just stow mise sops age
```
Clone `~/.secrets` (it holds the age key, and its `secrets.zsh` exports `SOPS_AGE_KEY_FILE`),
then sync the dotfiles (`cd ~/dotfiles && just sync`) and open a new shell.

Add the mac to `mac-workstations` in `inventory/hosts.yml` and put its sudo password in sops. Casks with pkg installers call sudo themselves and need it:
```bash
EDITOR=vim sops inventory/host_vars/HOST.sops.yml # ansible_become_password: ...
```
Then follow the controller node steps above, with `just run HOST`. Ansible renames the mac to HOST.

Manual steps macOS won't let ansible do:
- Grant yabai and skhd Accessibility access (System Settings > Privacy & Security > Accessibility)
- For the yabai scripting addition (space focus / move bindings), partially disable SIP:
  https://github.com/asmvik/yabai/wiki/Disabling-System-Integrity-Protection

# Managed node debian
```bash
su -
apt update && apt install sudo
adduser USER sudo
exit

sudo apt install openssh-server python3-pip python3
sudo service ssh start
```
## Sync ssh key
```
ssh-copy-id -i .ssh/personal-server home-edge
```
