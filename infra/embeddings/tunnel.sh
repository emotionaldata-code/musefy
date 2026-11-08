#!/bin/sh
# Keep PostgreSQL private; recreate the tunnel after a failed indexing process.
set -eu

: "${MUSEFY_SSH_HOST:?Set the SSH host}"
: "${MUSEFY_DATABASE_CONTAINER:?Set the PostgreSQL container name}"
port="${MUSEFY_TUNNEL_PORT:-55433}"
runtime="$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/musefy-embedding.XXXXXX")"
socket="$runtime/ssh"
cleanup() {
    ssh -S "$socket" -O exit "$MUSEFY_SSH_HOST" >/dev/null 2>&1 || true
    rm -rf "$runtime"
}
trap cleanup EXIT
trap 'exit 0' TERM INT

ssh -M -S "$socket" -fNT -o ControlPersist=no -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ConnectTimeout=20 \
    "$MUSEFY_SSH_HOST"
# The container name is a trusted local setting, restricted before remote interpolation.
case "$MUSEFY_DATABASE_CONTAINER" in *[!a-zA-Z0-9_.-]*) exit 2 ;; esac
address="$(ssh -S "$socket" "$MUSEFY_SSH_HOST" \
    "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' '$MUSEFY_DATABASE_CONTAINER'")"
case "$address" in ''|*[!0-9.]*) echo 'Invalid PostgreSQL address' >&2; exit 1 ;; esac
ssh -S "$socket" -O forward -o ExitOnForwardFailure=yes \
    -L "127.0.0.1:$port:$address:5432" "$MUSEFY_SSH_HOST"
"$@"
