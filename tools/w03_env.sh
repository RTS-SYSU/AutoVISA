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
# --feedback-check exercises the shared proposal Interface with restored real evidence.
if [ "${1:-}" = "--feedback-check" ]; then
    shift
    exec python3 "$root/tools/check_w05a.py" "$@"
fi
# --continuation-check validates real proof checks, decisions and linked-run restoration.
if [ "${1:-}" = "--continuation-check" ]; then
    shift
    exec python3 "$root/tools/check_w05b.py" "$@"
fi
# --comparison-check observes archived parent/child evidence without creating new proofs.
if [ "${1:-}" = "--comparison-check" ]; then
    shift
    exec python3 "$root/tools/check_w05c.py" "$@"
fi
# --service-proof-check preserves real W06 service proofs and the exact remaining gaps.
if [ "${1:-}" = "--service-proof-check" ]; then
    shift
    exec python3 "$root/tools/check_w06.py" "$@"
fi
# --msa-check validates source-independent MSA workflows through their public Interface.
if [ "${1:-}" = "--msa-check" ]; then
    shift
    exec python3 "$root/tools/check_msa.py" "$@"
fi
if [ "${1:-}" = "--msa-adapter-check" ]; then
    shift
    exec python3 "$root/tools/check_msa_adapters.py" "$@"
fi
if [ "${1:-}" = "--msa-legacy-check" ]; then
    shift
    exec python3 "$root/tools/check_msa_legacy.py" "$@"
fi
exec python3 "$root/tools/paper_import.py" "$@"
