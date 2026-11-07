#!/usr/bin/env bash
set -euo pipefail
: "${DARLING_HOST_UID:?missing Darling user namespace}"
: "${DARLING_WORKSPACE:?missing Darling workspace}"
if [ "${DARLING_SETUP:-0}" != 1 ] && [ "${1:-}" != shutdown ]; then
  python3 "$DARLING_WORKSPACE/scripts/nix-state.py" check || {
    echo 'Rootless runtime readiness missing; run darling-lol --installer in a terminal.' >&2
    exit 1
  }
fi
# This is namespace root (a subordinate host UID), not host root. Keep real
# UID/GID intact so Darling initializes the correct guest account and ownership.
# The workspace variables are this wrapper's; guest processes inherit the
# loader's environment, so they do not get host build paths.
workspace=$DARLING_WORKSPACE
exec env -u DARLING_WORKSPACE -u DARLING_PACKAGE_ID -u DARLING_RUNNER_DIR -u DARLING_SETUP \
  setpriv --euid 0 --egid 0 --keep-groups "$workspace/usr-local/bin/darling" "$@"
