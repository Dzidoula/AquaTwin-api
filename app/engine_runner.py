import asyncio
import json
import tempfile
from pathlib import Path

ENGINE_LOCK = asyncio.Lock()


class EngineRunError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


async def run_engine(
    params: dict,
    octave_cmd: str,
    script_path: str,
    timeout_s: int = 1800,
) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = Path(tmp_dir) / "input.json"
        output_path = Path(tmp_dir) / "output.json"
        input_path.write_text(json.dumps(params))

        async with ENGINE_LOCK:
            process = await asyncio.create_subprocess_exec(
                octave_cmd,
                script_path,
                str(input_path),
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise EngineRunError(f"Le calcul a depasse {timeout_s}s, arrete.")

        if process.returncode != 0:
            raise EngineRunError(
                f"Le moteur a echoue (code {process.returncode}): {stderr.decode(errors='replace')[:2000]}"
            )

        if not output_path.exists():
            raise EngineRunError("Le moteur n'a produit aucun resultat.")

        try:
            return json.loads(output_path.read_text())
        except json.JSONDecodeError as exc:
            raise EngineRunError(f"Resultat du moteur illisible: {exc}")
