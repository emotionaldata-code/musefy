#!/bin/sh
# Reuse the watcher's private tunnel and protected systemd environment.
set -eu
if [ "$#" -eq 0 ]; then
    echo "Usage: $0 embedding-status|embedding-activate|embedding-benchmark ..." >&2
    exit 2
fi
exec systemd-run --user --wait --pipe --collect \
    --property="EnvironmentFile=${XDG_CONFIG_HOME:-$HOME/.config}/musefy/embeddings.env" \
    /bin/sh -c 'exec "$MUSEFY_RUNTIME/bin/musefy" "$@"' musefy "$@"
