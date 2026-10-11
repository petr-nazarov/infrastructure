# Handover: voxtype-remote-mac

2026-10-11 13:14 · infrastructure · branch `main` · HEAD `395c259`

## Goal

Let the Mac (`macmom`) send voxtype dictation, both speech-to-text and the LLM cleanup, to
the desktop's GPU instead of its own slow `small` model. A menu bar item switches between
local and remote on demand. Same setup for the matebook later.

## Current state

Done and verified on `home-desktop` (Arch):
- `arch/voxtype_server` runs `voxtype-whisper` (whisper-server, Vulkan on the RX 7800 XT)
  and `voxtype-gateway` (Caddy on `:8765`, bearer token + NetBird IPs only). Measured
  0.2-0.3 s per 4-5 s clip. Without the token, with a wrong token or from the LAN IP: 401.
  `/api/pull`: 404.
- `voxtype-target` toggle local -> remote -> local works on the desktop, including the
  language swap to `"auto"` and back. A playbook run while remote changed nothing.
- `voxtype-postprocess` sent the cleanup through the gateway while remote.

Not yet done or tested on the Mac:
- `darwin/gui_apps` has the same "Point voxtype at the voxtype server" task, but has never
  run.
- Hammerspoon's new `voxtypeTarget` menu bar item and `voxtype-target` under the macs'
  `/usr/bin/python3` (3.9) have only passed `luac -p` / `py_compile` on Linux.

## Changed files

Committed this session:
- `395c259` feat(voxtype): serve dictation from the desktop gpu to other machines
- dotfiles `799bf77` feat(voxtype): switch dictation between local and the desktop server

Uncommitted: none from this work. Unrelated edits by the user sit in dotfiles
(`.devcontainer/*`, `install.sh`, `_claude/.claude/skills/dumbdown/SKILL.md`). Leave them.

## Next step

On the Mac: `cd ~/dotfiles && git pull && just sync`, reload Hammerspoon, then
`cd ~/infrastructure && git pull && just run macmom`.

## Blockers & open decisions

- The Mac must be on NetBird and resolve `home-desktop.netbird.cloud`. If it doesn't, check
  NetBird DNS on the Mac before touching the config.
- The desktop must be awake. When it sleeps the item turns yellow and a remote dictation
  fails after 10 s. Switching back to local is manual, by choice.
- NetBird's access policy is still the default (all peers). Tightening it in the dashboard
  is optional.

## How to verify

On the Mac:
- `curl -s -o /dev/null -w '%{http_code}\n' http://home-desktop.netbird.cloud:8765/health`
  should give `401`, which proves the gateway is reachable.
- `~/.local/bin/voxtype-target status` should print JSON with class `local`.
- Click the chip icon in the menu bar. The alert says "Speech: voxtype server" and the icon
  becomes a server. `grep -E '^(mode|language) ' ~/Library/Application\ Support/voxtype/config.toml`
  should show `mode = "remote"` and `language = "auto"`.
- Hold cmd+m and dictate in English and Russian. On the desktop,
  `journalctl -u voxtype-whisper -f` shows each request with `lang = auto`.
- Click again: back to `mode = "local"` and `language = ["en", "ru"]`.
