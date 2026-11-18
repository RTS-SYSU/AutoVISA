#!/usr/bin/env bash
# Run the import CLI with project-local PDF tools and PostgreSQL bindings.
# @param "$@" Arguments forwarded individually to paper_import.py.
# @exit The Python CLI status, or failure if a required runtime is missing.
set -eu
# root is the checkout; database and pdf contain the unpacked runtime trees.
root="$(cd "$(dirname "$0")/.." && pwd)"
database="$root/artifacts/w02-runtime/prefix/usr"
pdf="$root/artifacts/w03-runtime/prefix/usr"
if [ -x "$database/lib/postgresql/14/bin/initdb" ]; then
    export AUTORTA_PGBIN="$database/lib/postgresql/14/bin"
    export AUTORTA_PGSHARE="$database/share/postgresql/14"
    export PYTHONPATH="$database/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
    export LD_LIBRARY_PATH="$database/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
elif command -v pg_config >/dev/null; then
    export AUTORTA_PGBIN="$(pg_config --bindir)" AUTORTA_PGSHARE="$(pg_config --sharedir)"
fi
if [ -x "$pdf/bin/pdftotext" ]; then
    export PATH="$pdf/bin:$PATH"
    export LD_LIBRARY_PATH="$pdf/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
# --workbench selects the Web entry using the same PDF/database runtime.
if [ "${1:-}" = "--workbench" ]; then
    shift
    exec python3 "$root/tools/workbench.py" "$@"
fi
if [ "${1:-}" = "--map-frozen" ]; then
    shift
    exec python3 "$root/tools/map_frozen.py" "$@"
fi
# --derive shares the installed source, database and Rocq environment.
if [ "${1:-}" = "--derive" ]; then
    shift
    exec python3 "$root/tools/derive.py" "$@"
fi
exec python3 "$root/tools/paper_import.py" "$@"
