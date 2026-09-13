#!/usr/bin/env bash
# Runs a Node edit script against the live homelab-inventory API.
# lib.mjs is prepended, so the script can call its helpers directly.
# The script travels over stdin and runs in a throwaway node container
# on the swarm network on home-edge, so nothing is needed locally.
# Usage: run.sh SCRIPT.mjs
set -euo pipefail

dir=$(dirname "$0")
cat "$dir/lib.mjs" "$1" |
	ssh -o BatchMode=yes home-edge \
		'docker run --rm -i --quiet --network home_local_net node:24-alpine node --input-type=module -'
