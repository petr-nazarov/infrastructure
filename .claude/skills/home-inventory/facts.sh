#!/usr/bin/env bash
# Read-only hardware facts for a Linux host: ssh <host> bash -s < facts.sh
# No sudo; skips serials. Output feeds item specs, components, ports and custom fields.
echo "== host: $(hostname)"
. /etc/os-release && echo "os: $PRETTY_NAME"
echo "kernel: $(uname -r)"
for f in sys_vendor product_name product_version board_vendor board_name; do
	printf '%s: %s\n' "$f" "$(cat /sys/class/dmi/id/$f 2>/dev/null)"
done
lscpu | grep -E '^(Model name|CPU\(s\)|Thread|Core|Socket|CPU max MHz)'
free -m | awk 'NR==2{print "mem_total_mb: "$2}'
lsblk -d -e7 -o NAME,MODEL,SIZE,ROTA,TRAN
command -v lspci >/dev/null && lspci -nn | grep -iE 'ethernet|network|vga|3d'
for n in /sys/class/net/*; do
	[ -e "$n/device" ] || continue
	printf '%s mac=%s state=%s speed=%s duplex=%s carrier_changes=%s driver=%s\n' "${n##*/}" \
		"$(cat $n/address)" "$(cat $n/operstate)" "$(cat $n/speed 2>/dev/null)" "$(cat $n/duplex 2>/dev/null)" \
		"$(cat $n/carrier_changes)" "$(basename "$(readlink $n/device/driver)")"
done
ip -4 -br addr | grep -vE '^(lo|veth|docker|br-|virbr)'
for card in /sys/class/drm/card?/device; do
	[ -r "$card/mem_info_vram_total" ] && echo "gpu $(cat $card/vendor):$(cat $card/device) vram_bytes=$(cat $card/mem_info_vram_total)"
done
