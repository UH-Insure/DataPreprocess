from __future__ import annotations
import os, io, json, tempfile, pathlib
from typing import Optional, Tuple
import pandas as pd

# pip install cryptol
import cryptol

def write_cryptol_tempfile(
    code: str,
    host_mount_dir: str,
    prefer_name: Optional[str] = None,
) -> Tuple[pathlib.Path, str]:
    """
    Write UTF-8 Cryptol code to a temp file in the *host* mount directory.

    Returns:
      (host_path, container_relpath)
        - host_path: absolute Path on the host filesystem
        - container_relpath: path the Cryptol server should load, relative to its CWD,
          assuming the host_mount_dir is mounted at /home/cryptol/files inside the container.
          (i.e., 'files/<basename>.cry')
    """
    host_mount = pathlib.Path(host_mount_dir).resolve()
    host_mount.mkdir(parents=True, exist_ok=True)

    # Pick a readable basename if you have one; otherwise tempfile will generate one
    suffix = ".cry"
    prefix = None
    if prefer_name:
        # sanitize to a simple stem
        stem = pathlib.Path(prefer_name).stem
        prefix = f"{stem}_"

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(host_mount),
        prefix=(prefix or ""),
        suffix=suffix,
        delete=False,
    ) as tf:
        tf.write(code)
        tf.flush()
        os.fsync(tf.fileno())
        host_path = pathlib.Path(tf.name)

    # Inside the container we assume mount -> /home/cryptol/files
    container_relpath = f"files/{host_path.name}"
    return host_path, container_relpath


def load_with_cryptol_server(
    container_relpath: str,
    server_url: Optional[str] = None,
    reset_server: bool = True,
) -> dict:
    """
    Connect to Cryptol Remote API and :load the given file path.
    Returns a dict with 'load_ok' plus optional details (file_deps, errors).
    """
    kwargs = {}
    if server_url:
        kwargs["url"] = server_url
    cry = cryptol.connect(reset_server=reset_server, **kwargs)

    result: dict = {"load_ok": False, "file": container_relpath, "error": "None"}

    try:
        # Mirrors REPL ':load <file>'
        load_file = cry.load_file(container_relpath).result()  # may raise if load fails

        result["load_ok"] = True

        try:
            deps = cry.file_deps(container_relpath, is_file=True).result()
            result["file_deps"] = deps["imports"]
        except Exception:
            result["file_deps"] = "error"

    except Exception as e:
        result["error"] = e

    return result


def verify_df_row_with_cryptol(
    df: pd.DataFrame,
    idx: int,
    host_mount_dir: str,
    server_url: Optional[str] = None,
) -> dict:
    """
    Take row `idx` from df, write to mounted temp file, and ask Cryptol server to load it.
    Deletes the temp file on the host after the load attempt.

    Returns a dict with paths (for logging) and server response.
    """
    row = df.iloc[idx]
    code = row["content"]
    prefer_name = row.get("filename") if "filename" in df.columns else None

    host_path, container_relpath = write_cryptol_tempfile(
        code=code,
        host_mount_dir=host_mount_dir,
        prefer_name=prefer_name,
    )

    try:
        load_info = load_with_cryptol_server(
            container_relpath=container_relpath,
            server_url=server_url,
            reset_server=True,  # good hygiene between calls
        )
    finally:
        # Always try to delete the temp file, even if load failed
        try:
            host_path.unlink()
            deleted = True
        except FileNotFoundError:
            deleted = False
        except OSError:
            # You might want to log this in a real system
            deleted = False

    return {
        "host_path": str(host_path),
        "container_relpath": container_relpath,
        "load_info": load_info,
        "deleted": deleted,
    }

# Example usage:
# df = pd.read_json("your.jsonl", lines=True)
# confirm = verify_df_row_with_cryptol(
#     df, idx=0,
#     host_mount_dir="/path/host/mount",
#     server_url=os.environ.get("CRYPTOL_SERVER_URL"),
# )
# print(json.dumps(confirm, indent=2))
