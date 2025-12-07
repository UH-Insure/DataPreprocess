"""
slice_cryptol_preprocess.py

Pipeline for:
  * Reading Cryptol slices from REPO_ROOT/sliced_files
  * Checking them with the existing interpreter_process helpers
  * Greedily minimizing imports (when possible)
  * Returning a pandas DataFrame of passing, minimized snippets.

This module DOES NOT modify interpreter_process.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd

from .interpreter_process import (
    load_with_cryptol_server,
)


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def write_code_at_repo_relpath(
    code: str,
    rel_path: Path,
    host_mount_dir: Path,
) -> Tuple[Path, str]:
    """
    Write `code` to MOUNT_DIR / rel_path on the host, and return:

      (host_path, container_relpath)

    where container_relpath is the path we pass to the Cryptol server.
    By convention, host_mount_dir is mounted inside the container at
    /home/cryptol/files, so container_relpath must start with 'files/'.
    """
    host_mount_dir = host_mount_dir.resolve()
    rel_path = Path(rel_path)

    host_path = host_mount_dir / rel_path
    host_path.parent.mkdir(parents=True, exist_ok=True)
    host_path.write_text(code, encoding="utf-8")

    # This is what the container sees: /home/cryptol/files/<rel_path>
    container_relpath = f"files/{rel_path.as_posix()}"

    return host_path, container_relpath


def get_mount_dir(env_var: str = "MOUNT_DIR") -> Path:
    """
    Resolve MOUNT_DIR from the environment.
    """
    val = os.getenv(env_var)
    if not val:
        raise RuntimeError(f"{env_var} is not set in the environment")
    return Path(val).expanduser().resolve()


def split_import_blocks(code: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Split a Cryptol module into (header, imports_block, body) using a
    simple heuristic:

      * header  : everything before the first 'import ' line
      * imports : consecutive import / blank lines
      * body    : everything after the import block
    """
    lines = code.splitlines()
    header: List[str] = []
    imports: List[str] = []
    body: List[str] = []

    in_imports = False
    seen_import = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("import "):
            in_imports = True
            seen_import = True
            imports.append(line)
        elif in_imports and (stripped == "" or stripped.startswith("--")):
            # keep blank/comment lines inside the import block
            imports.append(line)
        elif in_imports and seen_import:
            # first non-import, non-blank after imports → body
            body.append(line)
        else:
            header.append(line)

    # If we never saw an import, all lines are in header
    if not seen_import:
        return lines, [], []

    return header, imports, body


def count_real_imports(import_lines: List[str]) -> int:
    """
    Count non-empty 'import' lines (ignores blank or comment-only lines).
    """
    return sum(
        1
        for l in import_lines
        if l.lstrip().startswith("import ")
    )


def check_code_with_interpreter(
    code: str,
    rel_path: Path,
    host_mount_dir: Path,
    server_url: str,
    reset_server: bool = False,
) -> Tuple[bool, Any]:
    """
    Write `code` into MOUNT_DIR / rel_path, ask the Cryptol remote server
    to load it, then delete the file.

    Returns (ok, load_info).
    """
    # Write code at the repo-relative path under the mount dir
    host_path, container_relpath = write_code_at_repo_relpath(
        code=code,
        rel_path=rel_path,
        host_mount_dir=host_mount_dir,
    )

    try:
        load_info = load_with_cryptol_server(
            container_relpath=container_relpath,
            server_url=server_url,
            reset_server=reset_server,
        )
        print("  [debug] load_info:", repr(load_info))

        ok = False
        if isinstance(load_info, dict):
            if "load_ok" in load_info:
                ok = bool(load_info["load_ok"])
            elif "success" in load_info:
                ok = bool(load_info["success"])
        # fallback: if no dict/flag, consider as failure unless you want otherwise

    except Exception as exc:  # network / server / parse, etc.
        ok = False
        load_info = exc

    finally:
        # Delete the slice file, keep the directory structure
        try:
            host_path.unlink()
        except FileNotFoundError:
            pass

    return ok, load_info


# ---------------------------------------------------------------------------
# Import minimization (all in THIS module)
# ---------------------------------------------------------------------------

def minimize_imports(
    code: str,
    file_relpath: Path,
    host_mount_dir: Path,
    server_url: str,
) -> Tuple[str, int, int]:
    """
    Greedy import minimization:

      1. Split into (header, imports, body).
      2. For each import line, try dropping it:
           * Build candidate code.
           * Check via Cryptol interpreter.
           * If it still loads, keep it removed.
           * Otherwise, leave it in.

    Returns:
      (final_code, n_imports_original, n_imports_final)
    """
    header, imports, body = split_import_blocks(code)
    n_orig = count_real_imports(imports)

    if not imports:
        # No imports to minimize
        return code, 0, 0

    print(f"  [imports] Starting minimization for {file_relpath!r}")
    print(f"  [imports] Original imports: {n_orig}")

    # Greedy removal loop
    for idx, imp_line in enumerate(imports):
        if not imp_line.lstrip().startswith("import "):
            continue  # skip blanks or comments

        trial_imports = imports.copy()
        trial_imports[idx] = ""  # remove this import line in candidate
        candidate_code = "\n".join(header + trial_imports + body) + "\n"

        print(f"    [try] Removing import at line {idx}: {imp_line!r}")
        ok, _info = check_code_with_interpreter(
            code=candidate_code,
            rel_path=file_relpath,
            host_mount_dir=host_mount_dir,
            server_url=server_url,
            reset_server=False,
        )
        if ok:
            print("    [keep removed] OK without this import")
            imports = trial_imports
            code = candidate_code
        else:
            print("    [revert] Need this import")

    n_final = count_real_imports(imports)
    print(f"  [imports] Done. Final imports: {n_final}")

    final_code = "\n".join(header + imports + body) + "\n"
    return final_code, n_orig, n_final


# ---------------------------------------------------------------------------
# High-level pipeline → DataFrame
# ---------------------------------------------------------------------------

def process_sliced_files_to_df(
    sliced_root: Optional[Path] = None,
    mount_dir: Optional[Path] = None,
    server_url: Optional[str] = None,
) -> pd.DataFrame:
    """
    Main entry point.

    For every *.cry in `sliced_root` (default: REPO_ROOT / "sliced_files"):

      1. Read the file into a string.
      2. Run a basic Cryptol load via interpreter_process.
         * If FAIL: log and skip.
      3. If PASS:
         * Run import minimization (in this module).
      4. Append a row to a DataFrame:

         {
           "original_filename": relative path from sliced_root, # original path inside sliced_files
           "filename": basename,
           "code_final": minimized (or original) code,
           "n_imports_original": int,
           "n_imports_final": int,
         }

    Only files that PASS the initial load check are included in the DataFrame.
    """
    if mount_dir is None:
        mount_dir = get_mount_dir()
    else:
        mount_dir = Path(mount_dir).resolve()

    if sliced_root is None:
        pass
    else:
        sliced_root = Path(sliced_root).resolve()

    if server_url is None:
        server_url = os.getenv("CRYPTOL_SERVER_URL", "http://localhost:8080")

    print("[pipeline] REPO_ROOT   :", mount_dir)
    print("[pipeline] SLICED_ROOT :", sliced_root)
    print("[pipeline] SERVER_URL  :", server_url)

    rows: List[Dict[str, Any]] = []

    # NEW: counters for sanity check
    total_files = 0
    n_pass = 0
    n_fail = 0

    # Reset server only for the FIRST file we check, then reuse session.
    first_reset = True

    for slice_path in sorted(sliced_root.rglob("*.cry")):
        total_files += 1

        print("\n=== Processing slice ===")
        print("Slice:", slice_path)

                # Relative path of the slice under sliced_root, e.g.
        #   cryptol-specs/Primitive/Symmetric/Cipher/Block/Threefish.cry/067_test512b.cry
        rel = slice_path.relative_to(sliced_root)
        filename = slice_path.name

        # Path to the *original* module file, e.g.
        #   cryptol-specs/Primitive/Symmetric/Cipher/Block/Threefish.cry
        original_module_rel = rel.parent

        # Where we want to place the test file inside the mounted repo:
        #   same directory as the original module:
        #   cryptol-specs/Primitive/Symmetric/Cipher/Block/067_test512b.cry
        file_relpath = original_module_rel.parent / filename

        # For the DataFrame, keep track of the original module path
        original_filename = original_module_rel

        try:
            code = slice_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  [error] Could not read file: {e}")
            n_fail += 1
            continue

        print("  [check] Initial Cryptol load")
        ok, info = check_code_with_interpreter(
            code=code,
            rel_path=file_relpath,
            host_mount_dir=mount_dir,
            server_url=server_url,
            reset_server=first_reset,
        )
        first_reset = False  # only reset the first time

        if not ok:
            n_fail += 1
            print("  [skip] Initial load failed; skipping this slice.")
            print("  [debug] load_info:", repr(info))
            continue
        else:
            n_pass += 1

        final_code, n_orig, n_final = minimize_imports(
            code=code,
            file_relpath=file_relpath,
            host_mount_dir=mount_dir,
            server_url=server_url,
        )


        rows.append(
            {
                "original_filename": str(original_filename),   # relative path under sliced_root
                "filename": filename,
                "code_final": final_code,
                "n_imports_original": n_orig,
                "n_imports_final": n_final,
            }
        )

    df = pd.DataFrame(rows)

    # NEW: sanity-check summary
    print("\n[pipeline] Completed.")
    print("  Total files seen   :", total_files)
    print("  Initial load PASS  :", n_pass)
    print("  Initial load FAIL  :", n_fail)
    print("  Rows in DataFrame  :", len(df))

    return df



# ---------------------------------------------------------------------------
# Optional CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = process_sliced_files_to_df(
        sliced_root="/Users/josh/SecurityAnalytics/toy-cryptol-ast/sliced_files_test",
        mount_dir=os.getenv("MOUNT_DIR", "/Users/josh/SecurityAnalytics"),
        server_url="http://localhost:8080",
    )
    with pd.option_context("display.max_colwidth", 80):
        print(df.head())

