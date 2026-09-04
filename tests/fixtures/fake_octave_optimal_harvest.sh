#!/usr/bin/env bash
# Stands in for the real `octave` binary in optimal-harvest tests: reads
# the input JSON path (2nd arg) and writes a canned result to the output
# JSON path (3rd arg), instead of running the real Python-backed search
# (NASA POWER API + repeated Random Forest predictions).
set -euo pipefail

output_path="$3"

cat > "$output_path" <<'JSON'
{"rendement": 8200.5, "optimal_eto": 4.5, "appreciation": "Exceptionnel", "n_iterations": 3}
JSON
exit 0
