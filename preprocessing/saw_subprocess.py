import os
import sys
import shutil
import subprocess
import pandas as pd
from pathlib import Path
from typing import Optional, Mapping, Union, Sequence, Dict, Any

def run_saw_script(
    filename: str,
    cryptol_path: Union[str, Sequence[str], None] = None,
    cwd: Optional[Union[str, Path]] = None,
    extra_env: Optional[Mapping[str, str]] = None,
    saw_exe: str = "saw",
    stream: bool = False,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run a SAW (.saw) script with the 'saw' CLI and never raise on process errors.

    Returns a dict:
      {
        "ok": bool,                # True iff returncode == 0
        "returncode": int,         # SAW process return code
        "stdout": str,             # captured stdout
        "stderr": str,             # captured stderr ('' if streamed/merged)
        "cmd": list[str],          # command invoked
        "cwd": str,                # working directory used
        "error": Optional[str],    # high-level error category or None
      }

    Notes:
      - If 'stream=True', output is echoed live to stdout; 'stderr' is merged into 'stdout'.
      - No exceptions are raised for process failures; only "file_not_found" or "saw_not_found"
        are reported via the 'error' field with ok=False and returncode=-1.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "returncode": -1,
        "stdout": "",
        "stderr": "",
        "cmd": [saw_exe, filename],
        "cwd": "",
        "error": None,
    }

    saw_path = Path(filename).resolve()
    if not saw_path.exists():
        result["error"] = "file_not_found"
        result["stdout"] = ""
        result["stderr"] = f"SAW script not found: {saw_path}"
        return result

    if shutil.which(saw_exe) is None:
        result["error"] = "saw_not_found"
        result["stderr"] = f"'{saw_exe}' not found on PATH"
        return result

    run_cwd = Path(cwd) if cwd else saw_path.parent
    result["cwd"] = str(run_cwd)

    env = os.environ.copy()
    CRYPTOL_PATH = "/Users/josh/SecurityAnalytics/development/cryptol-specs:/Users/josh/SecurityAnalytics/development/cryptol"
    env["CRYPTOLPATH"] = CRYPTOL_PATH + f":{cryptol_path}" if cryptol_path else CRYPTOL_PATH
    if extra_env:
        env.update(extra_env)

    try:
        if stream:
            # Stream output live; merge stderr into stdout
            proc = subprocess.Popen(
                [saw_exe, str(saw_path)],
                cwd=str(run_cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            buffer = []
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                buffer.append(line)
            proc.wait(timeout=timeout)
            result["returncode"] = proc.returncode
            result["stdout"] = "".join(buffer)
            result["stderr"] = ""  # merged
        else:
            cp = subprocess.run(
                [saw_exe, str(saw_path)],
                cwd=str(run_cwd),
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,  # <-- never raises
            )
            result["returncode"] = cp.returncode
            result["stdout"] = cp.stdout or ""
            result["stderr"] = cp.stderr or ""
        result["ok"] = (result["returncode"] == 0)
        return result
    except subprocess.TimeoutExpired as te:
        result["error"] = "timeout"
        result["stdout"] = te.stdout or ""
        result["stderr"] = (te.stderr or "") + f"\nTimed out after {timeout} seconds."
        result["returncode"] = -1
        return result

def load_saw_results(filepath: str) -> pd.DataFrame:
    p = Path(filepath).expanduser()
    if not p.exists():
        return pd.DataFrame([])
    return pd.read_json(p, lines=True, orient="records")

if __name__ == "__main__":
    # Example usage
    saw_file = [
        "/Users/josh/SecurityAnalytics/development/saw-script/examples/aes/aes.saw",
        "/Users/josh/SecurityAnalytics/development/cryptol-specs/Primitive/Symmetric/Cipher/Block/AES/Verifications/Common.saw"
        ]
    for f in saw_file:
        res = run_saw_script(f, stream=True)
        print("\nResult:", res)