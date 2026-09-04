#!/usr/bin/env bash
# Echoes the TEST_ECHO_VAR environment variable into the output JSON —
# used to verify run_engine's extra_env actually reaches the subprocess's
# environment (e.g. Q_IRR_OVERRIDE_M3S for the emitter flow rate override).
set -euo pipefail

output_path="$3"
value="${TEST_ECHO_VAR:-null}"

cat > "$output_path" <<JSON
{"echoed": "$value"}
JSON
exit 0
