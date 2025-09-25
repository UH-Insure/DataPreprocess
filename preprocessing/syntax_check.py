import json, subprocess, tempfile, uuid
from pathlib import Path
import pandas as pd
import os

CRYPTOl_CMD = "cryptol"  # or full path, e.g., "/usr/local/bin/cryptol"

CRYPTOL_CMD = "cryptol"
CRYPTOLPATHS = [
    "/Users/josh/SecurityAnalytics/development/cryptol-specs",
    "/Users/josh/SecurityAnalytics",
    "/Users/josh/.cryptol",
    "/opt/homebrew/Cellar/cryptol/3.3.0/share/cryptol",
]

def run_cryptol_load(cry_path: Path) -> tuple[int, str]:
    env = os.environ.copy()
    env["CRYPTOLPATH"] = os.pathsep.join(CRYPTOLPATHS)
    proc = subprocess.run(
        [CRYPTOL_CMD, "-c", f":load {cry_path}", "-c", ":quit"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

def check_jsonl_with_cryptol(jsonl_path: str) -> pd.DataFrame:
    """
    For each row in the JSONL (expects 'filename' and 'content'), writes content
    to a temp .cry file and checks Cryptol can load it. Returns a DataFrame with:
      - filename
      - cryptol_output  (combined stdout+stderr; starts with [OK]/[FAIL])
    """
    results = []
    tmp_dir_obj = tempfile.TemporaryDirectory(prefix="cryptol_check_")
    tmp_dir = Path(tmp_dir_obj.name)

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                results.append({
                    "filename": f"[jsonl line {line_num}]",
                    "cryptol_output": f"[FAIL parse] JSON decode error: {e}"
                })
                continue

            filename = row.get("filename", f"[unknown at line {line_num}]")
            content = row.get("content", "")

            # Write to a unique temp .cry file (ensure trailing newline)
            tmp_path = tmp_dir / f"{uuid.uuid4().hex}.cry"
            if not content.endswith("\n"):
                content = content + "\n"
            tmp_path.write_text(content, encoding="utf-8")

            # Run Cryptol load check
            return_code, output = run_cryptol_load(tmp_path, CRYPTOl_CMD)

            results.append({
                "filename": filename,
                "return_code": return_code,
                "cryptol_output": output,
                #"exec_path": exec_path,
                #"exec_string": exec_string
            })

    # Build the exact two-column DataFrame you requested
    df = pd.DataFrame(results, columns=["filename", "return_code"])
    return df