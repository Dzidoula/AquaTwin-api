#!/usr/bin/env bash
# Stands in for the real `octave` binary in data-driven season-simulation
# tests: reads the input JSON path (2nd arg) and writes a canned result to
# the output JSON path (3rd arg), instead of running the real Python-backed
# Random Forest computation (NASA POWER API + sklearn).
set -euo pipefail

output_path="$3"

cat > "$output_path" <<'JSON'
{"rendement": 6611.44, "biomasse": 13222.88, "appreciation": "Bon"}
JSON
exit 0
