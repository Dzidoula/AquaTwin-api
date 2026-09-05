#!/usr/bin/env bash
# Same as fake_octave.sh, but the canned result includes animation frames —
# used to test the GET /recommendation/animation endpoint without depending
# on the real Octave engine.
set -euo pipefail

output_path="$3"

sleep 0.2
cat > "$output_path" <<'JSON'
{"should_irrigate": true, "duration_s": 131.79, "volume": 0.0,
 "soil_moisture": 0.31, "severe_stress": false,
 "psi_old": [1.0, 2.0, 3.0], "theta_infiltre": 0.02, "jour_julien": 221,
 "animation": {"r_max": 0.5, "z_max": 0.8, "r_emitter": 0.005,
   "theta_r": 0.0114, "theta_s": 0.4717, "grid_res": 2,
   "frames": [[[0.28, 0.29], [0.27, 0.30]], [[0.31, 0.32], [0.29, 0.33]]],
   "trace_debut": {"r_max": 0.5, "z_max": 0.8, "r_emitter": 0.005,
     "theta_r": 0.0114, "theta_s": 0.4717, "grid_res": 2,
     "frame_times_s": [0, 0.5],
     "frames": [[[0.28, 0.29], [0.27, 0.30]], [[0.28, 0.29], [0.27, 0.30]]]},
   "trace_fin": {"r_max": 0.5, "z_max": 0.8, "r_emitter": 0.005,
     "theta_r": 0.0114, "theta_s": 0.4717, "grid_res": 2,
     "frame_times_s": [130.5, 131.0],
     "frames": [[[0.31, 0.32], [0.29, 0.33]], [[0.31, 0.32], [0.29, 0.33]]]}}}
JSON
exit 0
