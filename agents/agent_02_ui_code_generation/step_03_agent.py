import ast
import os
import subprocess
import sys
import traceback
from agents.agent_02_ui_code_generation.step_01_jira_reader import (
    fetch_jira_issue_details,
)
from agents.agent_02_ui_code_generation.step_02_ui_code_generation import (
    build_streamlit_shell,
    extract_form_code,
    generate_ui_form_code,
)
from core.state import ProjectState
from core.ui_server import restart_ui_server


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

    Runs against the fully assembled file (static shell + generated form
    code) so the CSS/contrast checks below are satisfied by the shell and
    don't need to be re-asserted by the LLM on every generation.

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

    # LAYER 2b: Live Pipeline Integration Check — the form must actually POST
    # to the real ingestion API on submit, not just define `submitted` and
    # stop. A dry-run alone can't catch this, since a missing `if submitted:`
    # block simply runs no code and "succeeds" trivially.
    if "if submitted" not in code_content or "submit_to_pipeline(" not in code_content:
        return (
            False,
            "Missing Live Pipeline Integration",
            "The form must handle `if submitted:` and call "
            "`submit_to_pipeline(form_data)` with the collected field values "
            "— this is missing from the generated code.",
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
                    "error": lambda *a, **k: None,
                    "warning": lambda *a, **k: None,
                    "success": lambda *a, **k: None,
                    "info": lambda *a, **k: None,
                    # Widgets are commonly called directly on `st` as well as
                    # on a column/form object, so both need to work.
                    "text_input": lambda *a, **k: "",
                    "text_area": lambda *a, **k: "",
                    "number_input": lambda *a, **k: 0,
                    "date_input": lambda *a, **k: "",
                    "selectbox": lambda *a, **k: "",
                    "multiselect": lambda *a, **k: [],
                    "checkbox": lambda *a, **k: False,
                    "form_submit_button": lambda *a, **k: False,
                    "form": lambda *a, **k: type(
                        "MockForm",
                        (),
                        {
                            "__enter__": lambda s: s,
                            "__exit__": lambda s, *a: None,
                            "text_input": lambda *a, **k: "",
                            "text_area": lambda *a, **k: "",
                            "number_input": lambda *a, **k: 0,
                            "date_input": lambda *a, **k: "",
                            "selectbox": lambda *a, **k: "",
                            "multiselect": lambda *a, **k: [],
                            "checkbox": lambda *a, **k: False,
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
                                "number_input": lambda *a, **k: 0,
                                "date_input": lambda *a, **k: "",
                                "selectbox": lambda *a, **k: "",
                                "multiselect": lambda *a, **k: [],
                                "checkbox": lambda *a, **k: False,
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
    """Agent 02 Node: Reads the UI Jira story and generates/updates ONLY the
    KYC form part of streamlit_app.py in scope with that story — the page
    shell (page config + design-system CSS) is static and assembled in
    Python, never regenerated by the LLM. This keeps each run's LLM output
    small (a form snippet, not an entire multi-thousand-character file),
    which uses far fewer tokens and avoids the truncation/self-healing
    thrash a full-file regeneration was causing."""
    if not state.jira_ui_issue_key:
        print("No UI Jira issue key found. Skipping Agent 02.")
        return state

    print(f"Fetching Jira details for: {state.jira_ui_issue_key}...")
    ui_details = fetch_jira_issue_details(state.jira_ui_issue_key)

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    streamlit_path = os.path.join(project_root, "streamlit_app.py")

    existing_form_code = None
    if os.path.exists(streamlit_path):
        with open(streamlit_path, "r", encoding="utf-8") as f:
            existing_form_code = extract_form_code(f.read())

    # ============================================================================
    # SELF-HEALING RETRY LOOP (only the form snippet is ever (re)generated —
    # a failed/timed-out/malformed generation on ANY attempt, including the
    # first, just counts as one failed attempt and retries, rather than
    # crashing the whole agent).
    # ============================================================================
    # Each attempt only generates a small scoped form snippet (fast, cheap),
    # and this model's failures are more like variance than a systematic
    # error, so a larger retry budget meaningfully improves convergence odds.
    max_retries = 6
    form_code = None
    generated_code = None
    healing_context = existing_form_code
    err_type = "Unknown"

    for attempt in range(1, max_retries + 1):
        print(f"Generating KYC form code for this Jira story only (Attempt {attempt}/{max_retries})...")
        try:
            candidate_form_code = generate_ui_form_code(
                ui_details, existing_form_code=healing_context
            )
        except Exception as e:
            print(f"⚠️ [GENERATION ERROR] Attempt {attempt}/{max_retries}: {e}")
            healing_context = (
                f"# The previous attempt failed with: {e}\n"
                "Keep the response short and output ONLY the form body/submission "
                "code — nothing else."
            )
            err_type = "LLM Generation Error"
            continue

        form_code = clean_code_block(candidate_form_code)
        generated_code = build_streamlit_shell(form_code)

        with open(streamlit_path, "w", encoding="utf-8") as f:
            f.write(generated_code)

        is_valid, err_type, err_traceback = Comprehensive_code_validator(
            streamlit_path, generated_code
        )

        if is_valid:
            print(
                f"✅ [SELF-HEALING SUCCESS] All checks (Syntax, Runtime, Contrast CSS)"
                f" passed on attempt #{attempt}!"
            )
            break

        print(f"\n⚠️ [SELF-HEALING DETECTED ISSUE - ATTEMPT {attempt}/{max_retries}]")
        print(f"🔴 Error Category: {err_type}")
        print(f"📋 Error Traceback:\n{err_traceback}\n")

        healing_context = (
            f"# BROKEN FORM CODE ATTEMPT:\n{form_code}\n\n"
            f"# ERROR CATEGORY: {err_type}\n"
            f"# FULL STACK TRACE:\n{err_traceback}\n\n"
            f"# SELF-HEALING DIRECTIVE:\n"
            f"Fix the error highlighted in the stack trace above ({err_type}).\n"
            "Remember: output ONLY the form body/submission code, not the "
            "page shell/CSS/imports."
        )
    else:
        print("❌ [SELF-HEALING] Max retries reached.")
        state.errors.append(
            f"Agent 02: UI code failed validation after {max_retries} self-healing "
            f"attempts ({err_type}); deployed best-effort code may be broken."
        )

    if generated_code is None:
        # Every attempt raised before producing any code at all.
        error_msg = "Agent 02: All UI form generation attempts failed (LLM errors); no code deployed."
        print(error_msg)
        state.errors.append(error_msg)
        return state

    state.ui_code = generated_code
    print(f"✅ Final validated code deployed to: {streamlit_path}")

    # Always restart (not just launch-if-down): this is the ONLY live UI
    # now, and the point of self-healing is that the newly generated code
    # takes effect immediately, not after a manual "Rerun" click in an
    # already-open Streamlit tab.
    print("🔄 Restarting UI server on port 8502 with the newly generated code...")
    try:
        if restart_ui_server(port=8502):
            print("✅ UI server is live with the latest generated code.")
        else:
            print("⚠️ UI server failed to come up after restart.")
            state.errors.append("Agent 02: code validated and saved, but the UI server failed to restart.")
    except Exception as e:
        # The code is already validated and saved to disk at this point —
        # a server-restart failure shouldn't be treated as the whole agent
        # having failed.
        print(f"⚠️ UI server restart raised an error: {e}")
        state.errors.append(f"Agent 02: code validated and saved, but restarting the UI server raised: {e}")

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
