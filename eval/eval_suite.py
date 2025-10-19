from dataclasses import dataclass
import os
import re
import sys
import pandas as pd
import cryptol
from cryptol import BV
from huggingface_hub import InferenceClient

@dataclass
class Config:
    SERVER_URL: str = "http://localhost:8080"          # Cryptol remote API
    MODEL_ID: str = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    TEMP_FILE: str = "cryptol-files/generated.cry"              # single temp file; overwritten each row
    CRYPTOL_PATH: str = "files/generated.cry"  # path inside Cryptol server container
    EVALS_PATH: str = "/Users/josh/SecurityAnalytics/DataPreprocess/eval/basic_evals.jsonl"

    FUNCTION_PROMPT_TEMPLATE: str = """### Instruction:
    Write a Cryptol function that implements the tasks described below. Include any type signature necessary for the function.
    Output exactly one code block in the format ```cryptol ...``` and nothing else — no explanation, no extra text. The file should be valid Cryptol source that can be loaded by the Cryptol tool and by SAW.

    ### Request:
    Task: {task}
    """

    PROPERTY_PROMPT_TEMPLATE: str = """### Instruction:
    Write a Cryptol property that tests the function described below.
    Output exactly one code block in the format ```cryptol ...``` and nothing else — no explanation, no extra text. The code block should contain valid Cryptol source that can be loaded by the Cryptol tool and by SAW.

    ### Request:
    Task: {task}
    """

# ------------------ Helpers -------------------------
def extract_code_block(text: str) -> str:
    """
    Get content inside ```cryptol ...``` or generic ```...```.
    If no fence is found, return the raw text.
    """
    m = re.search(r"```(?:cryptol)?\s*(.*?)```", text, flags=re.S | re.I)
    return (m.group(1) if m else text).strip()

def run_assert(test_src: str, ns: dict) -> tuple[bool, str]:
    """
    Execute a single assert string. Returns (ok, message).
    """
    try:
        exec(test_src, ns)
        return True, "OK"
    except AssertionError as e:
        return False, f"AssertionError: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def run_eval_suite(eval_df: pd.DataFrame, config: Config, provider: str = "nebius") -> None:
    """
    Run the eval suite given by eval_df.
    Each row should have 'task', optional 'test_setup_code', and 'test_list'.
    """
    # ----------------- Inference Client -----------------
    HF_TOKEN = os.getenv("HF_TOKEN")
    if not HF_TOKEN:
        print("ERROR: Set HF_TOKEN in your environment.", file=sys.stderr)
        sys.exit(1)

    client = InferenceClient(
        provider=provider,
        api_key=HF_TOKEN,
    )
    # -------------------- Main loop --------------------- #
    for idx, row in eval_df.iterrows():
        task           = row["task"]
        task_id        = row.get("task_id", f"row{idx}")
        tests          = row.get("test_list", []) or []
        setup_code     = row.get("test_setup_code", "") or ""
        type           = row.get("type", "function")

        # -------- Prepare prompt --------
        if type == "property":
            prompt = config.PROPERTY_PROMPT_TEMPLATE.format(task=task)
        else:
            prompt = config.FUNCTION_PROMPT_TEMPLATE.format(task=task)

        print(f"\n=== Task {task_id} ===")
        print(f"[PROMPT]\n{prompt}")

        # -------- Inference --------
        try:
            completion = client.chat.completions.create(
                model=config.MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )
            # HF chat client returns .message.content
            content = completion.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] Inference failed: {e}")
            continue

        # -------- Extract code & save to single temp file --------
        source_code = extract_code_block(content)
        if setup_code != "":
            source_code = "\n\n// --- Begin Test Setup Code ---\n" + setup_code \
                  + "\n// --- End Test Setup Code ---\n\n" + source_code
        print(f"[GENERATED CODE]\n{source_code}\n")
        try:
            with open(config.TEMP_FILE, "w") as f:
                f.write(source_code)
            print(f"[INFO] Wrote generated Cryptol to {config.TEMP_FILE} (overwritten).")
        except Exception as e:
            print(f"[ERROR] Writing temp file failed: {e}")
            continue

        # -------- Cryptol: load & test --------
        try:
            cry = cryptol.connect(url=config.SERVER_URL, reset_server=True)
            cry.load_file(config.CRYPTOL_PATH)
        except Exception as e:
            print(f"[ERROR] Cryptol load failed: {e}")
            # Try to close/reset and move on
            try:
                cry.reset_server()
            except Exception:
                pass
            continue

        # Namespace exposed to exec() tests (only what's needed)
        ns = {"cry": cry, "BV": BV}

        # Optional setup code per row
        if setup_code.strip():
            try:
                exec(setup_code, ns)
            except Exception as e:
                print(f"[ERROR] test_setup_code failed: {e}")
                try:
                    cry.reset_server()
                except Exception:
                    pass
                continue

        # Run tests
        all_ok = True
        for i, test_src in enumerate(tests, 1):
            ok, msg = run_assert(test_src, ns)
            all_ok &= ok
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] test {i}: {msg}")

        # Cleanup/reset between tasks
        try:
            cry.reset_server()
        except Exception:
            pass

        print(f"[RESULT] Task {task_id}: {'ALL PASS' if all_ok else 'HAS FAILURES'}")

    print("\nDone processing all evals.")

if __name__ == "__main__":
    config = Config()
    eval_df = pd.read_json(config.EVALS_PATH, lines=True)
    run_eval_suite(eval_df, config)