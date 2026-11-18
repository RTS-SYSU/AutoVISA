#!/usr/bin/env bash
# Download the PDF runtime from the configured Ubuntu 22.04 package indices.
# @output Project-local archives and extracted binaries under artifacts/w03-runtime.
# @exit Zero when all packages have been unpacked.
set -euo pipefail
# directory contains the project download cache and extracted runtime.
directory="$(cd "$(dirname "$0")/.." && pwd)/artifacts/w03-runtime"
mkdir -p "$directory/debs" "$directory/prefix"
cd "$directory/debs"
apt-get download poppler-utils libpoppler118 libopenjp2-7
for package in poppler-utils libpoppler118 libopenjp2-7; do
    # version selects one archive even when earlier downloads remain in the cache.
    version="$(apt-cache policy "$package" | awk '/Candidate:/ {print $2}')"
    archive="$(find . -maxdepth 1 -name "${package}_*.deb" -print | while read -r candidate; do
        if [ "$(dpkg-deb -f "$candidate" Version)" = "$version" ]; then echo "$candidate"; fi
    done)"
    [ -f "$archive" ]
    dpkg-deb -x "$archive" "$directory/prefix"
    sha256sum "$archive"
done
