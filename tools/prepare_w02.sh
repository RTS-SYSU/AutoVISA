#!/usr/bin/env bash
# Bootstrap the project-local integration runtime without modifying the host packages.
# @output Verified Debian archives in debs/ and runtime files in prefix/ under artifacts/w02-runtime/.
# @exit Zero once all selected packages are unpacked and their archive digests printed.
set -euo pipefail
# root is the source checkout; dir holds the download cache and extracted runtime tree.
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/artifacts/w02-runtime"
mkdir -p "$dir/debs" "$dir/prefix"
cd "$dir/debs"
# apt verifies downloads against the hashes in the distribution's signed package indices.
apt-get download postgresql-14 postgresql-client-14 libpq5 python3-psycopg2
for pkg in postgresql-14 postgresql-client-14 libpq5 python3-psycopg2; do
    # pkg is the requested package; version pins the candidate selected by the local apt indices.
    version="$(apt-cache policy "$pkg" | awk '/Candidate:/ {print $2}')"
    # file must resolve to one archive whose embedded version matches, even if older downloads remain.
    file="$(find . -maxdepth 1 -name "${pkg}_*.deb" -print | sort | while read -r f; do
        if [ "$(dpkg-deb -f "$f" Version)" = "$version" ]; then echo "$f"; fi
    done)"
    [ -f "$file" ]
    dpkg-deb -x "$file" "$dir/prefix"
    sha256sum "$file"
done

