#!/usr/bin/env bash
# Stands in for the real `octave` binary in season-simulation tests: reads
# the input JSON path (2nd arg) and writes a canned result to the output
# JSON path (3rd arg), instead of running the real Octave computation.
set -euo pipefail

output_path="$3"

cat > "$output_path" <<'JSON'
{"points": [{"day": 1, "biomass": 1.5, "rendement": 0.75},
            {"day": 2, "biomass": 3.0, "rendement": 1.5}],
 "final_rendement": 1.5, "appreciation": "Faible"}
JSON
exit 0
