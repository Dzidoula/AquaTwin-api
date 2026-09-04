#!/usr/bin/env bash
# Emits a realistic noisy Octave failure (X11 warning banner + a real
# error() message + a full "called from" stack) — used to verify the
# backend extracts just the actual message for the app instead of
# forwarding this whole dump.
set -euo pipefail

cat >&2 <<'EOF'
octave: X11 DISPLAY environment variable not set
octave: disabling GUI features
error: Aucune donnee de sol disponible pour ces coordonnees (20.0000, 7.4000) - ni iSDA Africa, ni ISRIC SoilGrids. Verifiez la position choisie.
error: called from
    SoilGrids_Rosetta at line 63 column 5
    vanMualemParametersValor at line 4 column 6
    dailyIrrigationRecommendation at line 40 column 2
EOF
exit 1
