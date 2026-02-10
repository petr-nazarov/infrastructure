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
sudo pacman -Sy --needed openssh python
sudo systemctl enable --now sshd
```
# Managed node debian
```bash
su -
apt update && apt install sudo
adduser USER sudo
exit

sudo apt install openssh-server python3
sudo service ssh start
```
## Sync ssh key
```
ssh-copy-id -i .ssh/personal-server home-edge
```
