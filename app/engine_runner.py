import asyncio
import json
import os
import tempfile
from pathlib import Path

# Two separate locks, not one: the daily recommendation script
# (run_recommendation.m) runs the Richards PDE solver and can take up to
# `timeout_s` (30 min) — sharing one lock with the season-simulation script
# (run_season_prediction.m, a lightweight day-by-day loop with no PDE solver)
# meant a slow/stuck recommendation job blocked every Predictions-tab request
# on the server for as long as it ran. They touch unrelated Octave scripts
# with no shared state, so there's nothing to protect between them.
ENGINE_LOCK = asyncio.Lock()
SEASON_LOCK = asyncio.Lock()


class EngineRunError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _clean_engine_error(stderr_text: str) -> str:
    """Octave's raw stderr is noisy for a farmer to read (an X11/GUI
    warning banner, then a full call stack under "error: called from") —
    extract just the actual error() message, which is the only part a
    human needs. Falls back to a truncated raw dump if no `error: ` line
    is found (an unexpected crash shape we haven't seen before)."""
    messages = [
        line[len("error: "):].strip()
        for line in stderr_text.splitlines()
        if line.startswith("error: ") and line.strip() != "error: called from"
    ]
    if messages:
        return messages[-1]
    return stderr_text.strip()[:300] or "Erreur inconnue du moteur."


async def run_engine(
    params: dict,
    octave_cmd: str,
    script_path: str,
    timeout_s: int = 1800,
    lock: asyncio.Lock | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict:
    lock = lock or ENGINE_LOCK
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = Path(tmp_dir) / "input.json"
        output_path = Path(tmp_dir) / "output.json"
        input_path.write_text(json.dumps(params))

        env = {**os.environ, **extra_env} if extra_env else None

        async with lock:
            process = await asyncio.create_subprocess_exec(
                octave_cmd,
                script_path,
                str(input_path),
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise EngineRunError(f"Le calcul a depasse {timeout_s}s, arrete.")

        if process.returncode != 0:
            raw_stderr = stderr.decode(errors="replace")
            # Full detail goes to the service log (journalctl) for
            # debugging; only the clean, farmer-facing message is stored
            # on the job and shown in the app.
            print(f"[engine_runner] {script_path} failed (code {process.returncode}):\n{raw_stderr}", flush=True)
            raise EngineRunError(f"Le moteur a echoue : {_clean_engine_error(raw_stderr)}")

        if not output_path.exists():
            raise EngineRunError("Le moteur n'a produit aucun resultat.")

        try:
            return json.loads(output_path.read_text())
        except json.JSONDecodeError as exc:
            raise EngineRunError(f"Resultat du moteur illisible: {exc}")
