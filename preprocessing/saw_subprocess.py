import os
import sys
import shutil
import subprocess
import pandas as pd
import json
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
        "filename": filename,
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
    CRYPTOL_PATH = "/workspace/cryptol-specs:/workspace/cryptol"
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

def get_dummy_saw_result(filename: str, error: str) -> Dict[str, Any]:
    return {
        "filename": filename,
        "ok": True,
        "returncode": -1,
        "stdout": "",
        "stderr": f"SAW script not found: {filename}" if error == "file_not_found" else f"'{error}' not found on PATH",
        "cmd": ["saw", filename],
        "cwd": "",
        "error": error,
    }

if __name__ == "__main__":
    # --- Load list of SAW files ---
    with open("sawfiles.txt", "r") as f:
        saw_files = [line.strip() for line in f if line.strip()]

    output_path = "/workspace/saw_results.jsonl"
    results = []

    # --- Check if previous results exist ---
    processed_files = set()
    if os.path.exists(output_path):
        print(f"[INFO] Resuming from existing results: {output_path}")
        with open(output_path, "r") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    results.append(record)
                    if "filename" in record:
                        processed_files.add(record["filename"])
                except json.JSONDecodeError:
                    continue  # skip corrupted lines

    # --- Process files incrementally ---
    for fpath in saw_files:
        if fpath in processed_files:
            print(f"[SKIP] Already processed: {fpath}")
            continue

        print(f"[RUN] Processing {fpath}")
        try:
            if fpath == "examples/chacha20/chacha20.saw":
                res = get_dummy_saw_result(fpath, None)
            else:
                res = run_saw_script(fpath, stream=True, timeout=60)


        except Exception as e:
            print(f"[ERROR] Failed on {fpath}: {e}")
            res = {"filename": fpath, "error": str(e)}

        # --- Append to file immediately ---
        with open(output_path, "a") as out_f:
            out_f.write(json.dumps(res) + "\n")

        # --- Keep in-memory list updated too (optional) ---
        results.append(res)

    # --- Optional final conversion to DataFrame ---
    df = pd.DataFrame(results)
    df.to_json(output_path, lines=True, orient="records")
    print(f"[DONE] Results saved to {output_path}")