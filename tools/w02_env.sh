#!/usr/bin/env bash
# Run the W02 CLI with matching PostgreSQL binaries, data files and Python bindings.
# @param "$@" Arguments forwarded individually to check_w02.py, for example --show joint-demo.
# @exit 2 when a PostgreSQL installation cannot be located; otherwise the Python CLI exit status.
set -eu
# root resolves project resources even when the caller starts in another directory.
root="$(cd "$(dirname "$0")/.." && pwd)"
# prefix is the unpacked Ubuntu /usr tree prepared specifically for this project.
prefix="$root/artifacts/w02-runtime/prefix/usr"
if [ -x "$prefix/lib/postgresql/14/bin/initdb" ]; then
    # The project-local Ubuntu packages need no system service or global Python install.
    # AUTORTA_PGBIN selects server and client programs; AUTORTA_PGSHARE supplies initdb templates.
    export AUTORTA_PGBIN="$prefix/lib/postgresql/14/bin"
    export AUTORTA_PGSHARE="$prefix/share/postgresql/14"
    # LD_LIBRARY_PATH locates libpq; PYTHONPATH locates the psycopg2 bindings for system Python.
    export LD_LIBRARY_PATH="$prefix/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export PYTHONPATH="$prefix/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
elif command -v pg_config >/dev/null; then
    export AUTORTA_PGBIN="$(pg_config --bindir)" AUTORTA_PGSHARE="$(pg_config --sharedir)"
else
    echo 'PostgreSQL is missing: run bash tools/prepare_w02.sh in Ubuntu first.' >&2
    exit 2
fi
exec /usr/bin/python3 "$root/tools/check_w02.py" "$@"

