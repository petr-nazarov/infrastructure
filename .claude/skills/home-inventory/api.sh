#!/usr/bin/env bash
# Calls the homelab-inventory API from inside the swarm network on home-edge,
# where the app needs no login (Authelia only guards the public route).
# Usage: api.sh METHOD PATH [JSON_FILE|-]
# Prints the response body; exits non-zero on HTTP >= 400.
set -euo pipefail

method=$1 path=$2 body=${3:-}
curl="docker run --rm -i --quiet --network home_local_net curlimages/curl:8.10.1 -sS -w '\n%{http_code}' -X $method"
url="'http://homelab-inventory:8798$path'"

if [ -n "$body" ]; then
	[ "$body" = - ] && body=/dev/stdin
	out=$(ssh -o BatchMode=yes home-edge "$curl -H 'Content-Type: application/json' --data-binary @- $url" <"$body")
else
	out=$(ssh -o BatchMode=yes home-edge "$curl $url" </dev/null)
fi

status=${out##*$'\n'}
printf '%s\n' "${out%$'\n'*}"
if [ "$status" -ge 400 ]; then
	echo "HTTP $status from $method $path" >&2
	exit 1
fi
