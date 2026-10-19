# Desk KVM

An HDMI + USB KVM switch with 4 computer ports. The monitor and the desk peripherals
plug into it, and it hands all of them to one computer at a time.

| KVM port | Computer |
|---|---|
| 4 | home-desktop (Arch) |
| 2 | macmom, sometimes: lid closed (clamshell), through a USB-C dongle |

Each computer port takes an HDMI cable and a USB cable. For PC2 both come from a USB-C
dongle (VIA Labs hub with HDMI, gigabit LAN and USB), and the dongle's single USB-C cable
goes to the Mac:

```text
macmom ── USB-C ── dongle ─┬─ HDMI ─┐
                           └─ USB ──┴─ KVM port 2 ── KVM ─┬─ HDMI out ── monitor ("Mi Monitor")
                                                          └─ USB out ─── mic, webcam, keyboards,
                                                                          mouse, Bluetooth dongle
```

Switching the KVM switches the monitor along with the USB devices.

## What is on it

What macmom saw behind the KVM on 2026-10-19 (`ioreg -p IOUSB -w0 -l`):

| Device | USB id | Notes |
|---|---|---|
| USB/XLR Dynamic Microphone | `0d8c:016c` | the desk mic; also an output (its headphone jack) |
| Logitech Brio 500 | `046d:0943` | webcam, has its own mic |
| Glove80 Left | `16c0:27db` | keyboard; the right half talks to the left half |
| Logitech G502 HERO | `046d:c08b` | mouse |
| Realtek Bluetooth Radio | `0bda:8771` | RTL8761BU dongle, the desktop's Bluetooth |

Switching the KVM is a USB unplug on one computer and a plug on the other. Nothing
is shared; a computer the KVM isn't on simply has none of these devices.

## macmom

`roles/darwin/kvm` installs the LaunchAgent `local.kvm-watch`. Every 2 s it checks
whether the KVM mic is in CoreAudio:

- **Mic appears** (KVM switched to the mac): it becomes the default input, and
  `caffeinate -u` turns the display on, so there's no need to press a key first.
- **Mic disappears** (KVM switched away): the input goes back to "MacBook Air Microphone".
- It also connects and disconnects the Bluetooth earphones, see below.

It only reacts to those changes, so if you pick another input by hand while on the KVM,
it stays. The device names are in `roles/darwin/kvm/defaults/main.yml`.

### Waking up

A sleeping Mac doesn't wake when USB devices are plugged in, and the KVM keyboard isn't
plugged in until you switch to it. So "switch the KVM and it wakes up" only works because
the mac never sleeps on AC: `roles/darwin/power` sets `sleep 0` and turns on
`pmset disablesleep` while charging, which keeps it awake even with the lid closed. With
the display off, the agent turns it back on.

What this means in practice:

- Lid closed on the USB-C dongle (charging): switching to KVM port 2 turns the screen on
  within ~2 s. You still get the lock screen; type the password (Touch ID is under the lid).
- Lid closed on battery: the mac really sleeps, and switching the KVM won't wake it.
  Plugging in the dongle (power + monitor) wakes a closed Mac.

Check it:

```bash
launchctl print gui/$(id -u)/local.kvm-watch | grep state   # running
SwitchAudioSource -c -t input                               # the current input
pmset -g | grep -E 'SleepDisabled|sleep '                   # SleepDisabled 1 on AC
```

## Bluetooth earphones

The earphones are paired with the desktop through the Realtek dongle on the KVM. That
can't follow the KVM to the mac:

- **macOS has no driver for third-party Bluetooth dongles.** On macmom the dongle shows up
  in USB and does nothing; macOS only uses its built-in Apple controller.
- **The pairing isn't stored on the dongle.** BlueZ keeps the link keys on the desktop
  (`/var/lib/bluetooth/<dongle address>/`), so even a computer that could drive the dongle
  wouldn't know the earphones.
- When the KVM is on the mac, the desktop has no Bluetooth at all
  (`bluetoothctl`: "No default controller available").

So the earphones (Sony WH-1000XM6) are paired twice: with the desktop through the dongle,
and with macmom's built-in Bluetooth. `local.kvm-watch` swaps them over:

- **KVM arrives:** `blueutil --connect`, then the earphones become the output and the desk
  mic is set as the input again (a headset connecting can take the input over). If the
  earphones are off, the connect fails after a few seconds and nothing else changes.
- **KVM leaves:** `blueutil --disconnect`, so they are free for the desktop.

The address and name are `darwin_kvm_earphones` in `roles/darwin/kvm/defaults/main.yml`.
Re-pairing with the mac keeps the address, so nothing changes there.

Not done yet: the desktop doesn't reconnect them on its own when the dongle comes back.
Press the earphones' power button briefly, or `bluetoothctl connect <address>` there.

The seamless alternative is a USB Bluetooth audio transmitter on the KVM (Creative
BT-W5/BT-W6, Avantree DG80, ...). Every OS sees it as an ordinary USB sound card and the
pairing lives on the transmitter, so the earphones would follow the KVM like the mic does,
with no software on either computer.

The input side is covered either way: the desk mic is on the KVM, so it switches with it.
