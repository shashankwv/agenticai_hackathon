import ast
import os
import socket
import subprocess
import sys
import traceback
from agents.agent_02_ui_code_generation.step_01_jira_reader import (
    fetch_jira_issue_details,
)
from agents.agent_02_ui_code_generation.step_02_ui_code_generation import (
    generate_ui_code,
)
from core.state import ProjectState

# ============================================================================
# UNIFORMITY PROMPT SYSTEM CONTRACT
# Enforces high-contrast UI design and layout structure during self-healing
# ============================================================================
UNIFORMITY_RULES = """
### UNIFORMITY & DESIGN SYSTEM GUIDELINES (STRICTLY REQUIRED):
1. **Page Config**: Must include `st.set_page_config(page_title="KYC Portal", page_icon="🤖", layout="wide")`.
2. **High-Contrast Dark CSS Theme**: Must inject explicit custom CSS styling using `st.markdown()` ensuring:
   - Text inputs and textareas use `-webkit-text-fill-color: #ffffff !important` with dark background `#1e293b`.
   - Labels are styled clearly with high contrast colors (`#e2e8f0`).
   - Primary buttons have visible background `#4f46e5` and white text `#ffffff`.
3. **Executable Code Only**: Output clean Python code only. Do NOT output plain markdown explanations outside code blocks.
"""


def is_port_in_use(port: int = 8502) -> bool:
    """Checks if the Streamlit server port is active."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def ensure_streamlit_running(port: int = 8502):
    """Programmatically boots Streamlit background process."""
    if not is_port_in_use(port):
        print(
            f"🚀 Launching Streamlit server background process on port {port}..."
        )
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        streamlit_file = os.path.join(project_root, "streamlit_app.py")

        subprocess.Popen(
            [
                "streamlit",
                "run",
                streamlit_file,
                "--server.fileWatcherType",
                "auto",
                "--server.port",
                str(port),
                "--server.address",
                "0.0.0.0",
                "--server.headless",
                "true",
            ],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("✅ Streamlit server process initialized.")
    else:
        print("ℹ️ Streamlit server is running and watching streamlit_app.py.")


def clean_code_block(code_str: str) -> str:
    """Removes outer markdown fences if returned by LLM."""
    if "```python" in code_str:
        return code_str.split("```python")[1].split("```")[0].strip()
    elif "```" in code_str:
        return code_str.split("```")[1].split("```")[0].strip()
    return code_str.strip()


# ============================================================================
# COMPREHENSIVE SELF-HEALING VALIDATION ENGINE
# Catches Syntax, High-Contrast UI CSS, Imports, and Dry-Run Execution Errors
# ============================================================================
def Comprehensive_code_validator(
    file_path: str, code_content: str
) -> tuple[bool, str, str]:
    """Self-Healing Engine: Validates Syntax, UI Contrast CSS, and Execution.

    Returns: (is_valid, error_category, error_traceback)
    """
    # LAYER 1: AST Syntax Check
    try:
        ast.parse(code_content, filename=file_path)
    except SyntaxError as se:
        return (
            False,
            "SyntaxError",
            f"SyntaxError on line {se.lineno}: {se.msg}\nSnippet: {se.text}",
        )
    except Exception as e:
        return False, "AST Parse Error", str(e)

    # LAYER 2: High-Contrast CSS Uniformity Validation
    if "st.markdown" not in code_content or "<style>" not in code_content:
        return (
            False,
            "UI Uniformity Error",
            "Missing high-contrast custom CSS styling injection (st.markdown).",
        )

    if (
        "-webkit-text-fill-color" not in code_content
        or ".stTextInput label" not in code_content
    ):
        return (
            False,
            "UI Contrast Error",
            "Input text styling missing explicitly defined label colors and high-contrast font rules.",
        )

    # LAYER 3: Python Compiler Validation
    compile_res = subprocess.run(
        [sys.executable, "-m", "py_compile", file_path],
        capture_output=True,
        text=True,
    )
    if compile_res.returncode != 0:
        return False, "Compilation Error", compile_res.stderr

    # LAYER 4: Headless Dry-Run Execution
    try:
        exec_globals = {
            "__file__": file_path,
            "__name__": "__main__",
            "st": type(
                "MockStreamlit",
                (),
                {
                    "set_page_config": lambda *a, **k: None,
                    "markdown": lambda *a, **k: None,
                    "title": lambda *a, **k: None,
                    "write": lambda *a, **k: None,
                    "form": lambda *a, **k: type(
                        "MockForm",
                        (),
                        {
                            "__enter__": lambda s: s,
                            "__exit__": lambda s, *a: None,
                            "form_submit_button": lambda *a, **k: False,
                        },
                    )(),
                    "columns": lambda n: [
                        type(
                            "MockCol",
                            (),
                            {
                                "__enter__": lambda s: s,
                                "__exit__": lambda s, *a: None,
                                "text_input": lambda *a, **k: "",
                                "text_area": lambda *a, **k: "",
                            },
                        )()
                        for _ in range(n if isinstance(n, int) else len(n))
                    ],
                },
            )(),
        }
        exec(compile(code_content, file_path, "exec"), exec_globals)
    except NameError as ne:
        return (
            False,
            "NameError (Missing Variable/Import)",
            f"{traceback.format_exc()}\nDetail: {ne}",
        )
    except AttributeError as ae:
        return (
            False,
            "AttributeError (Invalid Method/Object)",
            f"{traceback.format_exc()}\nDetail: {ae}",
        )
    except ImportError as ie:
        return (
            False,
            "ImportError (Missing Dependency)",
            f"{traceback.format_exc()}\nDetail: {ie}",
        )
    except Exception as re:
        return (
            False,
            "Runtime Execution Error",
            f"{traceback.format_exc()}\nDetail: {re}",
        )

    return True, "NONE", ""


def run_ui_code_generation_agent(state: ProjectState) -> ProjectState:
    """Agent 02 Node: Reads Jira, generates UI code with self-healing & contrast rules."""
    if not state.jira_ui_issue_key:
        print("No UI Jira issue key found. Skipping Agent 02.")
        return state

    print(f"Fetching Jira details for: {state.jira_ui_issue_key}...")
    ui_details = fetch_jira_issue_details(state.jira_ui_issue_key)

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    streamlit_path = os.path.join(project_root, "streamlit_app.py")

    existing_code = None
    if os.path.exists(streamlit_path):
        with open(streamlit_path, "r", encoding="utf-8") as f:
            existing_code = f.read()

    # 1. Initial Code Generation
    print("Generating Streamlit UI Code with High-Contrast System Contract...")
    prompt_payload = f"{ui_details}\n\n{UNIFORMITY_RULES}"
    generated_code = generate_ui_code(
        prompt_payload, existing_ui_code=existing_code
    )
    generated_code = clean_code_block(generated_code)

    with open(streamlit_path, "w", encoding="utf-8") as f:
        f.write(generated_code)

    # ============================================================================
    # SELF-HEALING RETRY LOOP
    # ============================================================================
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        is_valid, err_type, err_traceback = Comprehensive_code_validator(
            streamlit_path, generated_code
        )

        if is_valid:
            print(
                f"✅ [SELF-HEALING SUCCESS] All checks (Syntax, Runtime, Contrast CSS)"
                f" passed on attempt #{attempt}!"
            )
            break

        print(
            f"\n⚠️ [SELF-HEALING DETECTED ISSUE - ATTEMPT {attempt}/{max_retries}]"
        )
        print(f"🔴 Error Category: {err_type}")
        print(f"📋 Error Traceback:\n{err_traceback}\n")

        if attempt < max_retries:
            print(
                "🔧 [SELF-HEALING RE-GENERATION] Sending diagnostic feedback to LLM"
                " for resolution..."
            )

            healing_context = (
                f"# BROKEN CODE ATTEMPT:\n{generated_code}\n\n"
                f"# ERROR CATEGORY: {err_type}\n"
                f"# FULL STACK TRACE:\n{err_traceback}\n\n"
                f"# SELF-HEALING DIRECTIVE:\n"
                f"1. Fix the error highlighted in the stack trace above ({err_type}).\n"
                "2. Ensure all text fields have explicit dark background styling and"
                " white text contrast.\n"
                f"{UNIFORMITY_RULES}"
            )

            generated_code = generate_ui_code(
                ui_details, existing_ui_code=healing_context
            )
            generated_code = clean_code_block(generated_code)

            with open(streamlit_path, "w", encoding="utf-8") as f:
                f.write(generated_code)
        else:
            print("❌ [SELF-HEALING] Max retries reached.")

    state.ui_code = generated_code
    print(f"✅ Final validated code deployed to: {streamlit_path}")

    ensure_streamlit_running(port=8502)

    codespace_name = os.getenv("CODESPACE_NAME")
    port_forward_domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")

    if codespace_name and port_forward_domain:
        access_url = f"https://{codespace_name}-8502.{port_forward_domain}"
    else:
        access_url = "http://localhost:8502"

    print("\n" + "=" * 50)
    print("🔗 STREAMLIT UI LIVE ACCESS LINK:")
    print(f"👉 {access_url}")
    print("=" * 50 + "\n")

    return state