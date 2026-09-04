#!/usr/bin/env bash
# Stands in for the real `octave` binary in tests: reads the input JSON path
# (2nd arg) and writes a canned result to the output JSON path (3rd arg),
# instantly, instead of taking ~13 minutes. Used to test the job/subprocess
# plumbing without depending on Octave being installed or on the real
# solver's runtime.
set -euo pipefail

input_path="$2"
output_path="$3"
lock_marker="/tmp/fake_octave_running_marker"

if [ -f "$lock_marker" ]; then
    echo "fake_octave: another instance is already running" >&2
    exit 1
fi
touch "$lock_marker"
trap 'rm -f "$lock_marker"' EXIT

if grep -q '"force_fail": *true' "$input_path"; then
    echo "fake_octave: forced failure" >&2
    exit 1
fi

sleep 0.2
cat > "$output_path" <<'JSON'
{"should_irrigate": true, "duration_s": 131.79, "volume": 0.0,
 "soil_moisture": 0.31, "severe_stress": false,
 "psi_old": [1.0, 2.0, 3.0], "theta_infiltre": 0.02, "jour_julien": 221,
 "eto_mm_jour": 4.1, "pluie_48h_mm": 16.7}
JSON
exit 0
