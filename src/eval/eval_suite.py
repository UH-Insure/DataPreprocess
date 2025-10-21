from dataclasses import dataclass
import os
import re
import sys
import datetime
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
    EVALS_PATH: str = "/Users/josh/SecurityAnalytics/DataPreprocess/src/eval/.data/evals.jsonl"

    FUNCTION_PROMPT_TEMPLATE: str = """### Instruction:
    Write a Cryptol function that implements the tasks described below
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
    start_time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    print(f"Starting eval suite at {start_time}, {len(eval_df)} tasks to process.")
    filename = f"src/eval/.data/test/eval_results_{start_time}.txt"
    # ----------------- Inference Client -----------------
    HF_TOKEN = os.getenv("HF_TOKEN")
    if not HF_TOKEN:
        print("ERROR: Set HF_TOKEN in your environment.", file=sys.stderr)
        sys.exit(1)

    client = InferenceClient(
        provider=provider,
        api_key=HF_TOKEN,
    )
    results = ""
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
        if setup_code != "":
            prompt += f"\n### Additional setup code:\n```cryptol\n{setup_code}\n```"

        result_ = f"\n=== Task {task_id} ===\n"
        result_ += f"\n[PROMPT BEGIN]\n{prompt}\n[PROMPT END]\n\n"

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
            result_ += f"[ERROR] Inference failed: {e}"
            print(result_)
            results += f"{result_}\n"
            continue

        # -------- Extract code & save to single temp file --------
        source_code = extract_code_block(content)
        if setup_code != "":
            source_code = f"{setup_code}\n\n{source_code}"
        result_ += f"\n[GENERATE BEGIN]\n```cryptol\n{source_code}\n```\n[GENERATE END]\n\n"
        try:
            with open(config.TEMP_FILE, "w") as f:
                f.write(source_code)
            print(f"[INFO] Wrote generated Cryptol to {config.TEMP_FILE} (overwritten).")
        except Exception as e:
            result_ += f"[ERROR] Writing temp file failed: {e}"
            print(result_)
            results += f"{result_}\n"
            continue

        # -------- Cryptol: load & test --------
        try:
            cry = cryptol.connect(url=config.SERVER_URL, reset_server=True)
            cry.load_file(config.CRYPTOL_PATH)
        except Exception as e:
            result_ += f"[ERROR] Cryptol load failed: {e}"
            print(result_)
            results += f"{result_}\n"
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
                result_ += f"[ERROR] test_setup_code failed: {e}"
                print(result_)
                results += f"{result_}\n"
                # Try to close/reset and move on
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
            result_ += f"  [{status}] test {i}: {msg}\n"
        
        # Cleanup/reset between tasks
        try:
            cry.reset_server()
        except Exception:
            pass

        result_ += f"[RESULT] Task {task_id}: {'ALL PASS' if all_ok else 'HAS FAILURES'}\n"
        print(result_)
        results += f"{result_}\n"

    print(f"\n{\
            datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")\
            }\nDone processing all evals.")
    with open(filename, "w") as f:
        f.write(results)
    print(f"Wrote eval results to {filename}.")

if __name__ == "__main__":
    config = Config()
    eval_df = pd.read_json(config.EVALS_PATH, lines=True)
    run_eval_suite(eval_df, config)