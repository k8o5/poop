import google.generativeai as genai
import google.api_core.exceptions
import os
import traceback
import subprocess
import sys
import shutil
import time
import platform
import random
from PIL import Image
import re
try:
    import readline # For command history
except ImportError:
    # readline might not be available on all systems (e.g., some Windows setups without pyreadline)
    # Input history might be limited or platform-dependent.
    if platform.system() != "Windows": # pyreadline is not automatically a readline replacement on Windows via this import
        print("readline module not available, command history might be limited.")

GAK = os.environ.get("GOOGLE_API_KEY")
M_CURRENT_TEXT_MODEL = None
M_MULTI_CAPABLE_MODEL = None
M_LIGHT_MODEL = None
GCFG = genai.types.GenerationConfig(temperature=0.4, candidate_count=1)

CURRENT_TARGET_FILE = None
LAST_USER_INSTRUCTION = "print('Hello from POOP!')"
LAST_SUCCESSFUL_TASK_DESCRIPTION = ""

POOP_NAME = "Programmatic Operations Optimization Protocol"
FAREWELL = "Valete!"

LINK_START = "\x1b]8;;"
LINK_END = "\x1b\\"
LINK_RESET = "\x1b]8;;\x1b\\"
API_KEY_LINK = f"{LINK_START}https://makersuite.google.com/app/apikey{LINK_END}makersuite.google.com/app/apikey{LINK_RESET}"

ACTIVE_SUBPROCESS = None
ACTIVE_SUBPROCESS_FILE = None

CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False
LAST_CODE_FOR_CONFIRMATION = ""

CURRENT_PLAN_TEXT = ""
CURRENT_PLAN_STEPS = []
PLAN_CONFIRMED = False
PLAN_STEP_INDEX = 0
PLAN_STEP_FAILED_INFO = None

PAST_POOP_FILES_CONTEXT = []
MAX_PAST_FILES_CONTEXT = 5

# Color Definitions
_BASE_COLORS = [ # For random prompt color
    "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[34m", "\x1b[35m", "\x1b[36m",
    "\x1b[91m", "\x1b[92m", "\x1b[93m", "\x1b[94m", "\x1b[95m", "\x1b[96m",
]
RESET_COLOR = "\x1b[0m"
BRIGHT_WHITE_COLOR = "\x1b[97m"

POOP_PROMPT_COLOR = random.choice(_BASE_COLORS)
POOP_MSG_COLOR = "\x1b[36m"  # Cyan
POOP_PLAN_COLOR = "\x1b[35m" # Magenta
AI_RESPONSE_COLOR = "\x1b[92m" # Bright Green (for LLM generated code/plan text)
ERROR_COLOR = "\x1b[91m"    # Bright Red
SUCCESS_COLOR = "\x1b[92m"  # Bright Green
WARNING_COLOR = "\x1b[93m"  # Bright Yellow
CODE_OUTPUT_HEADER_COLOR = "\x1b[34m" # Blue
CHAT_LLM_RESPONSE_COLOR = "\x1b[32m" # Darker Green for chat

IMAGE_ANALYSIS_SIGNAL = "#POOP_ANALYZE_IMAGE_PATH:"
MODULE_INSTALL_SIGNAL = "#POOP_INSTALLED_MODULE:"

LAST_SCRIPT_STDOUT_LINES = []
LAST_SCRIPT_STDERR_MESSAGE = None


_CMDS_TEMPLATE = f"""CMDS for POOP ({POOP_NAME}):
h(elp): Show this help.
q(uit)/exit: Exit the agent.
run: If new/modified Python code exists, show for confirmation, then execute it
     (blocking, live output) and attempt to debug errors (incl. pip install for ModuleNotFound).
     If script signals for image analysis, POOP will attempt it.
start [path]: Start Python code in the target file in the background (live output).
              No confirmation before start; assumes code is tested.
              If no path given, uses the current target file. If none, a new unique file is created.
stop: Stop the last background process started with 'start'.
status_process: Check the status of the background process.
show: Display the current Python code buffer, target file, and active plan (if any).
clear: Clear Python code buffer, task history, and active plan. Resets confirmation status and target file.
m(odel) [name/alias]: Change LLM. Aliases: 'primary', 'light'. Full names or short names also work.
                      Available: '{{multi_model_name_short}}' (primary), '{{light_model_name_short}}' (light).
img_desc [path]: Describe an image using POOP's multimodal AI.
f(ile) [path]: Set Python target file. 'f none' for in-memory/auto-file per plan.
               Loads code if file exists, resets confirmation and task history.
sysinfo: Display detected system information.
chat [query]: Chat with the LLM about the current context (last instruction, code, output/errors).
              If no query, LLM gives general thoughts.
[any other text]: Generate a plan. If confirmed, POOP executes step-by-step.
                  Failed plan steps offer retry/skip/abort options.
                  POOP will attempt to `pip install` missing modules if ModuleNotFoundError occurs.
                  Planner favors additive code for iterative tasks like game dev.
                  Scripts signaling '{IMAGE_ANALYSIS_SIGNAL} <filepath>' trigger AI image analysis.
                  Code from approved plan steps runs without individual confirmation.
"""
CMDS = ""

def print_centered(text, color=BRIGHT_WHITE_COLOR):
    term_width = shutil.get_terminal_size(fallback=(80,24)).columns
    padding = (term_width - len(text.splitlines()[0])) // 2 # Use first line for width calculation
    padding = max(0, padding)
    for line in text.splitlines():
        print(f"{' ' * padding}{color}{line}{RESET_COLOR}")

def print_poop_ascii_art():
    art = [
        r"  #####   #####   #####  #####  ",
        r"  #    # #     # #     # #    # ",
        r"  #    # #     # #     # #    # ",
        r"  #####  #     # #     # #####  ",
        r"  #      #     # #     # #      ",
        r"  #      #     # #     # #      ",
        r"  #       #####   #####  #      "
    ]
    art_color = BRIGHT_WHITE_COLOR # Keep this bright
    term_width = shutil.get_terminal_size(fallback=(80,24)).columns
    for line in art:
        line_stripped = line.rstrip() # remove trailing spaces for centering
        padding = (term_width - len(line_stripped)) // 2
        padding = max(0, padding)
        print(f"{' ' * padding}{art_color}{line_stripped}{RESET_COLOR}")
    print()

def get_system_info():
    info = {
        "sys_platform": sys.platform,
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "os_name": os.name,
        "architecture": platform.machine(),
        "python_version": sys.version.split()[0]
    }
    if info["platform_system"] == "Linux":
        info["linux_distro_name"] = "N/A"
        info["linux_distro_id"] = "N/A"
        info["linux_distro_version_id"] = "N/A"
        try:
            with open("/etc/os-release") as f_os_release:
                for line_content in f_os_release:
                    if '=' in line_content:
                        key, value = line_content.strip().split('=', 1)
                        value = value.strip('"').strip("'")
                        if key == "NAME": info["linux_distro_name"] = value
                        elif key == "VERSION_ID": info["linux_distro_version_id"] = value
                        elif key == "ID": info["linux_distro_id"] = value
        except FileNotFoundError: pass
        except Exception: pass
    return info

def generate_unique_poop_filename():
    timestamp = int(time.time() * 1000)
    filename = f"poop{timestamp}.py"
    return os.path.abspath(filename)

def add_comment_to_code(code_content, task_description, is_plan_step=False, plan_step_info=None, overall_goal_for_comment=None):
    comment_lines = []
    if is_plan_step and plan_step_info:
        step_num_comment = plan_step_info.get('num', '?')
        total_steps_comment = plan_step_info.get('total', '?')
        comment_lines.append(f"# POOP: Plan Step {step_num_comment}/{total_steps_comment}: {task_description}\n")
        if overall_goal_for_comment:
            comment_lines.append(f"# POOP: Overall Goal: {overall_goal_for_comment}\n")
    elif task_description:
        comment_lines.append(f"# POOP: Task: {task_description}\n")

    existing_lines = code_content.splitlines()
    first_code_line_index = 0
    for i, line in enumerate(existing_lines):
        if line.strip():
            first_code_line_index = i
            break
    if existing_lines and existing_lines[first_code_line_index].startswith("# POOP:"):
        return code_content
    return "".join(comment_lines) + code_content


def update_cmds_display():
    global CMDS
    default_file_display = CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else "new unique file on generation/run/plan"
    multi_name_full = M_MULTI_CAPABLE_MODEL.model_name if M_MULTI_CAPABLE_MODEL else 'N/A'
    light_name_full = M_LIGHT_MODEL.model_name if M_LIGHT_MODEL else 'N/A'
    multi_name_short = multi_name_full.split('/')[-1]
    light_name_short = light_name_full.split('/')[-1]

    CMDS = _CMDS_TEMPLATE.format(
        current_default_file=default_file_display,
        multi_model_name_short=multi_name_short,
        light_model_name_short=light_name_short,
        IMAGE_ANALYSIS_SIGNAL=IMAGE_ANALYSIS_SIGNAL
    )

def load_past_poop_files_context():
    global PAST_POOP_FILES_CONTEXT
    PAST_POOP_FILES_CONTEXT = []
    try:
        files = [f for f in os.listdir(".") if f.startswith("poop") and f.endswith(".py")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(".", f)), reverse=True)

        for f_name in files[:MAX_PAST_FILES_CONTEXT]:
            try:
                with open(os.path.join(".", f_name), 'r', encoding='utf-8') as pf:
                    first_line = pf.readline().strip()
                    summary = ""
                    if first_line.startswith("# POOP:"):
                        summary = first_line.replace("# POOP:", "", 1).strip()
                        second_line_peek = pf.readline().strip()
                        if second_line_peek.startswith("# POOP: Overall Goal:"):
                            goal = second_line_peek.replace("# POOP: Overall Goal:", "",1).strip()
                            summary = f"{summary} (Part of Goal: {goal})"
                        PAST_POOP_FILES_CONTEXT.append(f"- {f_name}: {summary}")
            except Exception:
                pass # Ignore errors for individual files
        if PAST_POOP_FILES_CONTEXT:
            print(f"{POOP_MSG_COLOR}Context from {len(PAST_POOP_FILES_CONTEXT)} recent POOP files loaded.{RESET_COLOR}")
    except Exception as e:
        print(f"{WARNING_COLOR}!Warning: Error scanning for past POOP files: {e}{RESET_COLOR}")

def init_llm(model_name_primary='gemini-2.5-flash-preview-05-20', model_name_secondary='gemini-2.0-flash'):
    global GAK, M_CURRENT_TEXT_MODEL, M_MULTI_CAPABLE_MODEL, M_LIGHT_MODEL
    if not GAK: return False

    model_name_primary = model_name_primary.strip().rstrip(',')
    model_name_secondary = model_name_secondary.strip().rstrip(',')

    try:
        genai.configure(api_key=GAK)
        try:
            M_MULTI_CAPABLE_MODEL = genai.GenerativeModel(model_name_primary)
            print(f"{SUCCESS_COLOR}Primary LLM ({model_name_primary}): Initialized.{RESET_COLOR}")
        except Exception as e:
            print(f"{ERROR_COLOR}!Init {model_name_primary} (Primary) FAILED: {e}{RESET_COLOR}")
            M_MULTI_CAPABLE_MODEL = None

        if model_name_primary != model_name_secondary:
            try:
                M_LIGHT_MODEL = genai.GenerativeModel(model_name_secondary)
                print(f"{SUCCESS_COLOR}Secondary LLM ({model_name_secondary}): Initialized.{RESET_COLOR}")
            except Exception as e:
                print(f"{ERROR_COLOR}!Init {model_name_secondary} (Secondary) FAILED: {e}{RESET_COLOR}")
                M_LIGHT_MODEL = None
        elif M_MULTI_CAPABLE_MODEL:
            M_LIGHT_MODEL = M_MULTI_CAPABLE_MODEL
            print(f"{POOP_MSG_COLOR}Secondary LLM is same as Primary ({model_name_secondary}).{RESET_COLOR}")

        if M_MULTI_CAPABLE_MODEL:
            M_CURRENT_TEXT_MODEL = M_MULTI_CAPABLE_MODEL
        elif M_LIGHT_MODEL:
            M_CURRENT_TEXT_MODEL = M_LIGHT_MODEL
            print(f"{WARNING_COLOR}!Warning: Primary model failed or unavailable, using secondary model.{RESET_COLOR}")

        if M_CURRENT_TEXT_MODEL:
            print(f"{POOP_MSG_COLOR}Current text model set to: {M_CURRENT_TEXT_MODEL.model_name}{RESET_COLOR}")
        else:
            print(f"{ERROR_COLOR}!No LLM could be initialized as current text model.{RESET_COLOR}")
            update_cmds_display()
            return False

        load_past_poop_files_context()
        update_cmds_display()
        return True
    except Exception as e:
        print(f"{ERROR_COLOR}!General LLM Init FAILED: {e}{RESET_COLOR}")
        M_CURRENT_TEXT_MODEL = M_MULTI_CAPABLE_MODEL = M_LIGHT_MODEL = None
        update_cmds_display()
        return False

def get_llm_response_text(response, model_name_for_error_msg):
    try:
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            details = response.prompt_feedback.safety_ratings
            return f"#LLM_ERR: Prompt blocked by API for model {model_name_for_error_msg}. Reason: {reason}. Details: {details}"

        if not response.candidates:
            return f"#LLM_ERR: No candidates returned from model {model_name_for_error_msg}."

        candidate = response.candidates[0]
        finish_reason_val = None
        if hasattr(candidate, 'finish_reason'):
            if hasattr(candidate.finish_reason, 'name'):
                finish_reason_val = candidate.finish_reason.name
            else: # is an enum value
                finish_reason_val = candidate.finish_reason
        else:
            finish_reason_val = "UNKNOWN"


        if not candidate.content or not candidate.content.parts:
            safety_ratings_str = str(candidate.safety_ratings) if hasattr(candidate, 'safety_ratings') else "N/A"
            # FinishReason.STOP == 1
            if finish_reason_val == "STOP" or finish_reason_val == 1: # Check for enum value too
                 return f"#LLM_ERR: Model {model_name_for_error_msg} finished with {finish_reason_val} but no content (filtered/recitation). Safety: {safety_ratings_str}"
            return f"#LLM_ERR: No content parts from model {model_name_for_error_msg}. Finish: {finish_reason_val}. Safety: {safety_ratings_str}"

        text_parts = []
        for part in candidate.content.parts:
            if hasattr(part, 'text'):
                text_parts.append(part.text)

        if not text_parts:
            safety_ratings_str = str(candidate.safety_ratings) if hasattr(candidate, 'safety_ratings') else "N/A"
            return f"#LLM_ERR: Model {model_name_for_error_msg} returned no text parts. Finish: {finish_reason_val}. Safety: {safety_ratings_str}"

        return "".join(text_parts)

    except ValueError as ve: # E.g. if response.candidates is empty
        return f"#LLM_ERR: Error accessing response text from {model_name_for_error_msg} (ValueError): {ve}. Candidate finish_reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}"
    except AttributeError as ae: # If response structure is unexpected
        return f"#LLM_ERR: Attribute error processing LLM response from {model_name_for_error_msg}: {ae}. Candidate: {str(candidate)[:200]}"
    except Exception as e:
        return f"#LLM_ERR: Unexpected error processing LLM response from {model_name_for_error_msg}: {e}\n{traceback.format_exc()}"

def gmp(user_instruction_for_plan, system_info_for_plan, past_files_context_for_plan): # Generate Model Plan
    planning_model = M_MULTI_CAPABLE_MODEL if M_MULTI_CAPABLE_MODEL else M_CURRENT_TEXT_MODEL
    if not planning_model: return "#LLM_ERR: No suitable model for planning."

    system_info_str = "\n".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in system_info_for_plan.items()])
    past_context_str = "\n".join(past_files_context_for_plan) if past_files_context_for_plan else "No recent POOP activity."

    prompt = f"""You are POOP, an AI assistant that creates and executes Python code.
First, create a detailed, step-by-step plan for: "{user_instruction_for_plan}"

System Info:
---
{system_info_str}
---
Recent POOP Activity (other files/tasks):
---
{past_context_str}
---
Plan Instructions:
1. Numbered steps (1., 2., 3.).
2. For each step, define:
    - `Task:` Concise action for this step.
    - `Details:` (Optional) Specifics for implementing the task.
    - `Dependencies:` (Optional) Relies on previous output, libraries (e.g., 'pygame'), tools, user info, file paths. If a library is needed, explicitly state it (e.g., "Python library 'pygame'").
    - `Outcome:` What is achieved or produced by this step.
    - `Requires_Code_Gen:` (Yes/No) Does POOP need to generate Python code for this step?
    - `Additive_Code:` (Yes/No, only if Requires_Code_Gen: Yes) Should the code for this step be added to the script from previous steps, or is it a standalone script/replacement? Default No.
        **IMPORTANT**: If the overall user request implies building a single, evolving application (e.g., "make a pygame game", "develop a desktop app", "create a data analysis script with multiple plots"),
        **MOST code-generating steps AFTER the initial setup step SHOULD BE `Additive_Code: Yes`**. This means code from the current step will be appended to the code from previous steps in the SAME FILE.
        The first code-generating step in such a sequence can be `Additive_Code: No` (or Yes if adding to an existing buffer).
    - `Requires_User_Input_During_Step:` (Optional) If `Requires_Code_Gen: Yes`, what specific input will the Python script prompt the user for during its execution?
    - `Requires_User_Action:` (Optional) Is there a manual action the user needs to perform OR an internal POOP non-code action (e.g., "POOP will use its AI to describe image at <path_from_previous_step>.")?
    - `Screenshot_Analysis_Signal:` (Yes/No, only if Requires_Code_Gen: Yes AND the code *takes* a screenshot that POOP's AI should then analyze) If yes, the generated code must print the signal '{IMAGE_ANALYSIS_SIGNAL} <filepath_to_screenshot>'.

Example Plan for "make a simple pygame snake game":
1.  Task: Initial Pygame setup and game window.
    Details: Import pygame, initialize it, set up screen dimensions, title, and basic game loop structure.
    Dependencies: Python library 'pygame'.
    Outcome: An empty Pygame window opens and can be closed. This script will be the base for subsequent steps.
    Requires_Code_Gen: Yes
    Additive_Code: No

2.  Task: Implement Snake character and movement.
    Details: Define Snake class, draw it, handle keyboard input for movement (up, down, left, right).
    Dependencies: Code from Step 1.
    Outcome: Snake appears on screen and moves with arrow keys.
    Requires_Code_Gen: Yes
    Additive_Code: Yes

3.  Task: Implement Food and collision.
    Details: Create Food class, randomly place food, detect collision between Snake and Food.
    Dependencies: Code from Step 2.
    Outcome: Snake can "eat" food.
    Requires_Code_Gen: Yes
    Additive_Code: Yes

Return ONLY the numbered plan. Start with "1. Task: ...".
"""
    try:
        response = planning_model.generate_content(prompt, generation_config=GCFG)
        plan_output = get_llm_response_text(response, planning_model.model_name)
        return plan_output.strip()
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during plan generation with {planning_model.model_name}: {e}"
    except Exception as e:
        return f"#LLM_ERR: Error during plan generation with {planning_model.model_name}: {e}\n{traceback.format_exc()}"

def parse_plan_step_details(step_text_content):
    details = {}
    def extract_field(field_name, text, stop_keywords_list):
        # More robust pattern: field_name followed by colon, space, then content
        # Stops at the next field_name or end of text.
        pattern_str = rf"^\s*{re.escape(field_name)}:\s*(.*?)(?=(" + "|".join(map(lambda kw: r"\n\s*" + re.escape(kw) + ":", stop_keywords_list)) + r")|$)"
        match = re.search(pattern_str, text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match and match.group(1) else None

    all_fields_ordered = ["Task", "Details", "Dependencies", "Outcome", "Requires_Code_Gen", "Additive_Code", "Requires_User_Input_During_Step", "Requires_User_Action", "Screenshot_Analysis_Signal"]
    current_field_map = {
        "Task": "task", "Details": "details", "Dependencies": "dependencies", "Outcome": "outcome",
        "Requires_Code_Gen": "requires_code_gen", "Additive_Code": "additive_code",
        "Requires_User_Input_During_Step": "requires_user_input_during_step",
        "Requires_User_Action": "requires_user_action",
        "Screenshot_Analysis_Signal": "screenshot_analysis_signal"
    }
    remaining_text = step_text_content

    # Extract Task first, as it's less strictly formatted sometimes
    task_match = re.match(r"^\s*Task:\s*(.*?)(?=\n\s*(?:Details:|Dependencies:|Outcome:|Requires_Code_Gen:|Additive_Code:|Requires_User_Input_During_Step:|Requires_User_Action:|Screenshot_Analysis_Signal:|$))", remaining_text, re.DOTALL | re.IGNORECASE)
    if task_match:
        details["task"] = task_match.group(1).strip()
        remaining_text = remaining_text[task_match.end():] # Consume the matched part
    else: # Fallback if "Task:" label is missing or task is multi-line before other fields
        temp_remaining_text = remaining_text
        task_lines = []
        for line in temp_remaining_text.splitlines(keepends=True):
            line_stripped_check = line.strip()
            is_field_label = False
            for f_kw in all_fields_ordered[1:]: # Check if it's one of the other field labels
                if line_stripped_check.lower().startswith(f_kw.lower() + ":"):
                    is_field_label = True
                    break
            if not is_field_label and line_stripped_check:
                task_lines.append(line)
            elif task_lines: # Stop if we hit a field label after collecting some task lines
                break
            elif is_field_label: # If the first content line is already a field, task is likely missing or embedded
                break
        if task_lines:
            details["task"] = "".join(task_lines).strip()
            # Consume the extracted task lines from remaining_text
            len_consumed = sum(len(l) for l in task_lines)
            remaining_text = remaining_text[len_consumed:]

    for i, field_name_caps in enumerate(all_fields_ordered):
        if field_name_caps == "Task" and "task" in details: continue # Already extracted

        # Create stop keywords for the current field
        stop_kws_for_current_field = all_fields_ordered[i+1:]

        value = extract_field(field_name_caps, remaining_text, stop_kws_for_current_field)
        if value:
            field_key = current_field_map[field_name_caps]
            if field_key in ["requires_code_gen", "additive_code", "screenshot_analysis_signal"]:
                details[field_key] = (value.lower() == "yes")
            else:
                details[field_key] = value
            # Attempt to remove the extracted field and its value from remaining_text to avoid re-parsing
            # This is tricky due to regex overlaps. A simpler way is just to rely on the stop_keywords.
            # For now, we don't aggressively remove, extract_field should handle it.

    # Defaults if not found
    if "requires_code_gen" not in details: details["requires_code_gen"] = True # Default to True if unspecified
    if details["requires_code_gen"]:
        if "additive_code" not in details: details["additive_code"] = False
        if "screenshot_analysis_signal" not in details: details["screenshot_analysis_signal"] = False
    else: # If no code gen, these are false
        details["additive_code"] = False
        details["screenshot_analysis_signal"] = False
    return details


def parse_plan(plan_text_input):
    parsed_steps_list = []
    # Regex to find step numbers like "1.", "01.", "  2. "
    step_pattern = re.compile(r"^\s*(\d+)\.\s*(.*?)(?=(?:\n\s*\d+\.\s*)|$)", re.MULTILINE | re.DOTALL)
    matches = list(step_pattern.finditer(plan_text_input))

    if not matches and plan_text_input.strip(): # Treat as a single step if no numbered list
        step_data = parse_plan_step_details(plan_text_input.strip())
        if step_data.get("task"): # Ensure a task was parsed
            parsed_steps_list.append(step_data)
        elif plan_text_input.strip(): # Fallback if detailed parsing fails but text exists
             # Use the first line as task, default other fields
             parsed_steps_list.append({
                 "task": plan_text_input.strip().splitlines()[0],
                 "requires_code_gen": True,
                 "additive_code": False,
                 "screenshot_analysis_signal": False
             })
        return parsed_steps_list

    for match_obj in matches:
        # group(1) is the step number, group(2) is the content after "X. "
        step_content_after_num = match_obj.group(2).strip()
        if not step_content_after_num: continue # Skip empty steps

        step_data = parse_plan_step_details(step_content_after_num)

        if step_data.get("task"): # Ensure a task was parsed
            parsed_steps_list.append(step_data)
        else: # Fallback if detailed parsing fails for a numbered step
            if step_content_after_num: # If there was some content
                step_data["task"] = step_content_after_num.splitlines()[0].strip() # Use first line as task
                if "requires_code_gen" not in step_data: step_data["requires_code_gen"] = True
                if "additive_code" not in step_data and step_data["requires_code_gen"]: step_data["additive_code"] = False
                if "screenshot_analysis_signal" not in step_data and step_data["requires_code_gen"]: step_data["screenshot_analysis_signal"] = False
                parsed_steps_list.append(step_data)
    return parsed_steps_list

def gmc(current_code="", user_instruction_for_code_gen=LAST_USER_INSTRUCTION, error_feedback=None, previous_task_context_for_code_gen="", system_info_for_code_gen=None, plan_context_for_code_gen=None):
    global CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN
    if not M_CURRENT_TEXT_MODEL: return "#LLM_ERR: Current text model not initialized."

    is_additive_from_plan = plan_context_for_code_gen.get("is_additive", False) if plan_context_for_code_gen else False

    prompt_parts = [
        "You are a Python expert. Create, modify, or debug Python scripts. Use standard libraries. Add imports. Return ONLY raw Python code, no explanations or markdown backticks unless the code itself requires it (e.g. in a string).",
        f"If the task involves taking a screenshot AND the plan context (if provided) indicates 'Screenshot_Analysis_Signal: Yes' OR the task description strongly implies POOP should analyze the screenshot, the script MUST print the exact signal: '{IMAGE_ANALYSIS_SIGNAL} /path/to/screenshot.png' (using the actual, valid path to the saved image)."
    ]
    if is_additive_from_plan and current_code:
        prompt_parts.append("You are ADDING to existing code. Do NOT repeat imports or setup already present in the 'CURRENT SCRIPT' unless necessary for the new part. Focus on implementing the new functionality as an addition.")


    if system_info_for_code_gen:
        prompt_parts.append("\n--- TARGET SYSTEM INFO (for context) ---")
        for key, value in system_info_for_code_gen.items(): prompt_parts.append(f"{key.replace('_', ' ').title()}: {value}")
        prompt_parts.append("Adapt script for this system if OS-specific commands or paths are needed.")

    if previous_task_context_for_code_gen: # This is LAST_SUCCESSFUL_TASK_DESCRIPTION
        prompt_parts.append(f"\n--- CONTEXT FROM PREVIOUS SUCCESSFUL OPERATION ---")
        prompt_parts.append(f"{previous_task_context_for_code_gen[:1000]}{'...' if len(previous_task_context_for_code_gen)>1000 else ''}") # Truncate if too long
        prompt_parts.append("This might include previous user goals or script output summaries. Consider it for continuity if relevant.")


    if plan_context_for_code_gen:
        prompt_parts.append("\n--- EXECUTING PLAN STEP ---")
        prompt_parts.append(f"Overall Goal of the Plan: {plan_context_for_code_gen.get('overall_goal', LAST_USER_INSTRUCTION)}")
        if plan_context_for_code_gen.get("full_plan"):
            prompt_parts.append(f"Full Plan (for broader context, current step is key):\n{plan_context_for_code_gen['full_plan'][:500]}{'...' if len(plan_context_for_code_gen['full_plan']) > 500 else ''}")
        prompt_parts.append(f"Current Step Task: {plan_context_for_code_gen.get('current_step_description','N/A')}")
        if plan_context_for_code_gen.get("current_step_details"):
            prompt_parts.append(f"Details for Current Step: {plan_context_for_code_gen['current_step_details']}")
        prompt_parts.append(f"Your task is to generate the Python code specifically for this CURRENT STEP: {plan_context_for_code_gen.get('current_step_description','N/A')}.")
        if plan_context_for_code_gen.get("requires_user_input_during_step"):
            prompt_parts.append(f"The Python script for this step MUST prompt the user for the following information during its execution: {plan_context_for_code_gen['requires_user_input_during_step']}")
        if plan_context_for_code_gen.get("screenshot_analysis_signal"): # This is a boolean from parsed plan
            prompt_parts.append(f"This step has 'Screenshot_Analysis_Signal: Yes'. Ensure the script prints '{IMAGE_ANALYSIS_SIGNAL} <filepath_to_screenshot>' if it captures an image for POOP's AI to analyze.")
        if is_additive_from_plan:
            prompt_parts.append("This is an ADDITIVE step. The generated code will be appended to the existing script content. Do not redefine existing functions/classes from the 'CURRENT SCRIPT' unless the goal is to modify them. Add new logic or extend existing logic. Only provide the new/additional code.")


    if error_feedback:
        prompt_parts.append("\n--- DEBUGGING TASK ---")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
            prompt_parts.append(f"The script was intended for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"Original instruction for this code segment: {user_instruction_for_code_gen}")

        code_for_error_prompt = current_code # This is the full buffer that failed
        if len(code_for_error_prompt) > 1500 : # Truncate if extremely long
            code_for_error_prompt = f"... (previous code, possibly truncated) ...\n{current_code[-1500:]}"
        prompt_parts.append(f"FAULTY SCRIPT (or relevant part that caused the error):\n```python\n{code_for_error_prompt}\n```")
        prompt_parts.append(f"ERROR MESSAGE AND TRACEBACK:\n```\n{error_feedback}\n```")
        prompt_parts.append("Provide the FIXED Python script. If it was an additive step, ensure the fix integrates correctly, potentially modifying the whole script if necessary or just the additive part if the error was localized there. Output only the raw code for the complete fixed script (or fixed additive part if that's clearly identifiable and sufficient).")
    elif current_code : # Modifying existing script (could be additive base) or first part of additive
        task_type = "Add to the existing script" if is_additive_from_plan else "Modify the existing script"
        prompt_parts.append(f"\n--- CODE MODIFICATION TASK ---")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
             prompt_parts.append(f"This work is for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"CURRENT SCRIPT (the code you are adding to or modifying):\n```python\n{current_code}\n```")
        prompt_parts.append(f"NEW INSTRUCTION (what to add or change based on the current plan step or user request): {user_instruction_for_code_gen}")
        prompt_parts.append("Provide the PYTHON SCRIPT. If additive, provide only the new code to append. If not additive (i.e., modifying), provide the full modified script. Raw code only.")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True
    else: # No current_code, so generate new script from scratch
        prompt_parts.append("\n--- NEW SCRIPT TASK ---")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
            prompt_parts.append(f"This new script is for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"INSTRUCTION: {user_instruction_for_code_gen}")
        prompt_parts.append("Provide the PYTHON SCRIPT (raw code only):")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True

    full_prompt = "\n".join(prompt_parts)
    # print(f"\n{WARNING_COLOR}DEBUG: GMC Prompt:\n{full_prompt[:1000]}...{RESET_COLOR}\n") # For debugging
    try:
        response = M_CURRENT_TEXT_MODEL.generate_content(full_prompt, generation_config=GCFG)
        output = get_llm_response_text(response, M_CURRENT_TEXT_MODEL.model_name)
        if output.startswith("#LLM_ERR"): return output

        # Clean up common markdown formatting if LLM still adds it
        if output.startswith("```python"): output = output[9:]
        elif output.startswith("```"): output = output[3:]
        if output.endswith("```"): output = output[:-3]
        return output.strip()
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during code generation with {M_CURRENT_TEXT_MODEL.model_name}: {e}"
    except Exception as e:
        return f"#LLM_ERR: Error during Python code generation with {M_CURRENT_TEXT_MODEL.model_name}: {e}\n{traceback.format_exc()}"

def gmc_multimodal(image_data, text_prompt="Describe this image in detail."): # Generate Model Content (Multimodal)
    active_multimodal_model = M_MULTI_CAPABLE_MODEL if M_MULTI_CAPABLE_MODEL else M_CURRENT_TEXT_MODEL
    if not active_multimodal_model: return "#LLM_ERR: No suitable multimodal model initialized."
    if not hasattr(active_multimodal_model, "generate_content"): # Simple check
        return f"#LLM_ERR: Model {active_multimodal_model.model_name} may not support multimodal input or is not configured correctly."

    content = [text_prompt, image_data]
    try:
        response = active_multimodal_model.generate_content(content, generation_config=GCFG)
        description = get_llm_response_text(response, active_multimodal_model.model_name)
        return description
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during multimodal generation with {active_multimodal_model.model_name}: {e}"
    except Exception as e: # Catch more general errors like type errors if image_data is wrong
        return f"#LLM_ERR: Error during multimodal generation with {active_multimodal_model.model_name}: {e}\n{traceback.format_exc()}"

def gmtc(chat_context_prompt): # Generate Model Text for Chat
    if not M_CURRENT_TEXT_MODEL: return "#LLM_ERR: Current text model not initialized."
    try:
        response = M_CURRENT_TEXT_MODEL.generate_content(chat_context_prompt, generation_config=GCFG)
        return get_llm_response_text(response, M_CURRENT_TEXT_MODEL.model_name)
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during chat with {M_CURRENT_TEXT_MODEL.model_name}: {e}"
    except Exception as e:
        return f"#LLM_ERR: Error during chat with {M_CURRENT_TEXT_MODEL.model_name}: {e}\n{traceback.format_exc()}"


def create_execution_scope():
    # Basic scope for in-memory execution.
    # More restricted than file execution for safety, though still powerful.
    s = {"__builtins__": __builtins__}
    # Minimal safe libraries by default for in-memory, file exec has more freedom.
    libs_to_try_import = [
        ('os', 'os'), ('sys', 'sys'), ('time', 'time'), ('random', 'random'),
        ('math', 'math'), ('json', 'json'), ('re', 're')
    ]
    # For specific, advanced libraries, users should ideally use file-based execution
    # or ensure the libraries are explicitly handled if needed for in-memory.
    try: import mss; s['mss'] = mss # Example: if mss is commonly used by POOP
    except ImportError: pass

    for lib_name, alias in libs_to_try_import:
        try:
            exec(f"import {lib_name} as {alias}", s)
        except ImportError:
            pass # Silently ignore if a common lib isn't available in restricted env
    return s

def execute_code(code_buffer_to_exec, last_instruction_for_fix_context, previous_task_context_for_fix, file_path=None, auto_run_source=""):
    global LAST_SCRIPT_STDOUT_LINES, LAST_SCRIPT_STDERR_MESSAGE, LAST_SUCCESSFUL_TASK_DESCRIPTION
    LAST_SCRIPT_STDOUT_LINES = []
    LAST_SCRIPT_STDERR_MESSAGE = None

    if not code_buffer_to_exec or not code_buffer_to_exec.strip():
        return code_buffer_to_exec, False, False, [], None

    print(f"{POOP_MSG_COLOR}{auto_run_source}Executing Python code ({'File: ' + file_path if file_path else 'In-Memory'})...{RESET_COLOR}")
    fixed_this_run = False
    execution_successful = False
    error_output_for_llm = None
    current_system_info_for_fix = get_system_info()
    stdout_lines_capture = [] # Renamed to avoid conflict with global
    plan_context_for_fix_gmc = None # Initialize
    if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
        current_step_fix = CURRENT_PLAN_STEPS[PLAN_STEP_INDEX]
        plan_context_for_fix_gmc = {
            "full_plan": CURRENT_PLAN_TEXT, "current_step_description": current_step_fix.get('task', 'N/A'),
            "current_step_details": current_step_fix.get('details', 'N/A'),
            "requires_user_input_during_step": current_step_fix.get('requires_user_input_during_step'),
            "screenshot_analysis_signal": current_step_fix.get('screenshot_analysis_signal', False),
            "overall_goal": LAST_USER_INSTRUCTION, # The overall goal of the plan
            "is_additive": current_step_fix.get("additive_code", False)
        }


    if file_path:
        try:
            with open(file_path, "w", encoding='utf-8') as f: f.write(code_buffer_to_exec)
            child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [sys.executable, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8', errors='replace', env=child_env
            )
            stderr_capture_list = []
            print(f"{CODE_OUTPUT_HEADER_COLOR}--- Live Python Output Start (File: {os.path.basename(file_path)}) ---{RESET_COLOR}", flush=True)
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    sys.stdout.write(line); sys.stdout.flush(); stdout_lines_capture.append(line.strip())
                process.stdout.close()
            if process.stderr:
                for line in iter(process.stderr.readline, ""):
                    sys.stderr.write(line); sys.stderr.flush(); stderr_capture_list.append(line.strip())
                process.stderr.close()
            process.wait(); return_code = process.returncode
            print(f"\n{CODE_OUTPUT_HEADER_COLOR}--- Live Python Output End ---{RESET_COLOR}", flush=True)

            LAST_SCRIPT_STDOUT_LINES = stdout_lines_capture[:]

            if return_code != 0:
                raw_error_output = "\n".join(stderr_capture_list)
                error_output_for_llm = raw_error_output
                LAST_SCRIPT_STDERR_MESSAGE = error_output_for_llm
                print(f"{ERROR_COLOR}!Python process error (code {return_code}).{RESET_COLOR}")

                module_not_found_match = re.search(r"ModuleNotFoundError: No module named '([\w\.]+)'", raw_error_output)
                if module_not_found_match:
                    missing_module = module_not_found_match.group(1)
                    print(f"{POOP_MSG_COLOR}POOP: Detected missing module: '{missing_module}'{RESET_COLOR}")
                    install_confirm = input(f"{WARNING_COLOR}Attempt to install '{missing_module}' using pip? (y/N): {RESET_COLOR}").strip().lower()
                    if install_confirm == 'y':
                        print(f"{POOP_MSG_COLOR}POOP: Attempting 'pip install {missing_module}'...{RESET_COLOR}")
                        try:
                            pip_process = subprocess.run(
                                [sys.executable, "-m", "pip", "install", missing_module],
                                capture_output=True, text=True, check=False, timeout=120
                            )
                            if pip_process.returncode == 0:
                                print(f"{SUCCESS_COLOR}POOP: Successfully installed '{missing_module}'.{RESET_COLOR}")
                                # Signal that module was installed, script should be re-run
                                error_output_for_llm = f"{MODULE_INSTALL_SIGNAL}{missing_module}" # This special string is now the "error"
                                LAST_SCRIPT_STDERR_MESSAGE = f"Module '{missing_module}' was installed. Retry execution."
                                fixed_this_run = True # Indicates a change that requires re-evaluation
                            else:
                                pip_fail_msg = f"!POOP: Failed to install '{missing_module}'. Pip output:\n{pip_process.stdout}\n{pip_process.stderr}"
                                print(f"{ERROR_COLOR}{pip_fail_msg}{RESET_COLOR}")
                                LAST_SCRIPT_STDERR_MESSAGE = pip_fail_msg # Store pip's error
                        except subprocess.TimeoutExpired:
                            timeout_msg = f"!POOP: 'pip install {missing_module}' timed out."
                            print(f"{ERROR_COLOR}{timeout_msg}{RESET_COLOR}")
                            LAST_SCRIPT_STDERR_MESSAGE = timeout_msg
                        except Exception as e_pip:
                            pip_exc_msg = f"!POOP: Error during pip install attempt: {e_pip}"
                            print(f"{ERROR_COLOR}{pip_exc_msg}{RESET_COLOR}")
                            LAST_SCRIPT_STDERR_MESSAGE = pip_exc_msg
                    else:
                        print(f"{POOP_MSG_COLOR}POOP: Installation of '{missing_module}' skipped by user.{RESET_COLOR}")
                
                # If not fixed by pip install (or pip install wasn't attempted/failed, and error_output_for_llm is not the special signal)
                if not (error_output_for_llm and error_output_for_llm.startswith(MODULE_INSTALL_SIGNAL)):
                    print(f"{POOP_MSG_COLOR}Attempting to fix with LLM...{RESET_COLOR}")
                    fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
                    if fixed_code.startswith("#LLM_ERR"): print(f"{ERROR_COLOR}{fixed_code}{RESET_COLOR}")
                    elif fixed_code == code_buffer_to_exec: print(f"{WARNING_COLOR}LLM: No change proposed (error might persist).{RESET_COLOR}")
                    else:
                        print(f"{SUCCESS_COLOR}LLM: Proposed a fix.{RESET_COLOR}");
                        code_buffer_to_exec = fixed_code;
                        fixed_this_run = True
            else: # return_code == 0
                print(f"{SUCCESS_COLOR}Python execution successful.{RESET_COLOR}"); execution_successful = True
                LAST_SCRIPT_STDERR_MESSAGE = None # Clear any previous error
                output_summary = " ".join(stdout_lines_capture).strip()
                if output_summary:
                    summary_for_desc = output_summary[:150] + "..." if len(output_summary) > 150 else output_summary
                    LAST_SUCCESSFUL_TASK_DESCRIPTION += f"\nScript Output Summary: {summary_for_desc}"

        except FileNotFoundError: # E.g. sys.executable not found
            error_output_for_llm = f"Interpreter {sys.executable} not found."
            print(f"{ERROR_COLOR}!ERROR: {error_output_for_llm}{RESET_COLOR}")
            LAST_SCRIPT_STDERR_MESSAGE = error_output_for_llm
        except Exception as e: # Other exceptions during process setup or file writing
            error_output_for_llm = f"File execution setup error: {e}\n{traceback.format_exc()}"
            print(f"{ERROR_COLOR}!FILE EXECUTION ERROR: {e}. Attempting to fix...{RESET_COLOR}")
            LAST_SCRIPT_STDERR_MESSAGE = error_output_for_llm
            fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
            if fixed_code.startswith("#LLM_ERR"): print(f"{ERROR_COLOR}{fixed_code}{RESET_COLOR}")
            elif fixed_code == code_buffer_to_exec: print(f"{WARNING_COLOR}LLM: No change proposed.{RESET_COLOR}")
            else: print(f"{SUCCESS_COLOR}LLM: Proposed a fix.{RESET_COLOR}"); code_buffer_to_exec = fixed_code; fixed_this_run = True
    else: # In-Memory Execution
        original_stdout = sys.stdout
        from io import StringIO
        captured_output_io = StringIO()
        sys.stdout = captured_output_io # Redirect stdout
        
        execution_scope, compiled_object, compile_error_msg = create_execution_scope(), None, None
        try:
            compiled_object = compile(code_buffer_to_exec, '<in_memory_code>', 'exec')
        except SyntaxError as se:
            compile_error_msg = f"SYNTAX ERROR: Line {se.lineno}, Offset {se.offset}: {se.msg}\nRelevant Code: `{(se.text or '').strip()}`\n{traceback.format_exc(limit=0)}"
        
        if compile_error_msg:
            sys.stdout = original_stdout # Restore stdout
            error_output_for_llm = compile_error_msg
            LAST_SCRIPT_STDERR_MESSAGE = error_output_for_llm
            print(f"{ERROR_COLOR}IN-MEMORY COMPILE ERROR: {compile_error_msg.splitlines()[0]}. Attempting to fix...{RESET_COLOR}")
            fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
            if fixed_code.startswith("#LLM_ERR"): print(f"{ERROR_COLOR}{fixed_code}{RESET_COLOR}")
            elif fixed_code == code_buffer_to_exec: print(f"{WARNING_COLOR}LLM: No change proposed.{RESET_COLOR}")
            else: print(f"{SUCCESS_COLOR}LLM: Proposed a fix.{RESET_COLOR}"); code_buffer_to_exec = fixed_code; fixed_this_run = True
        elif compiled_object:
            execution_scope['__name__'] = '__main__' # Some scripts check this
            print_to_original_stdout = lambda *args, **kwargs: print(*args, file=original_stdout, **kwargs) # Helper
            
            print_to_original_stdout(f"{CODE_OUTPUT_HEADER_COLOR}--- Live Python Output Start (In-Memory) ---{RESET_COLOR}", flush=True)
            try:
                exec(compiled_object, execution_scope, execution_scope)
                print_to_original_stdout(f"\n{SUCCESS_COLOR}Python execution successful (In-Memory).{RESET_COLOR}"); execution_successful = True
                LAST_SCRIPT_STDERR_MESSAGE = None
            except SystemExit:
                print_to_original_stdout(f"\n{POOP_MSG_COLOR}Script called exit() (In-Memory).{RESET_COLOR}"); execution_successful = True # Considered success
                LAST_SCRIPT_STDERR_MESSAGE = None
            except KeyboardInterrupt:
                print_to_original_stdout(f"\n{WARNING_COLOR}Execution interrupted by user (In-Memory).{RESET_COLOR}")
                # Not necessarily an error for LLM to fix, but not a full success
            except Exception as e:
                sys.stdout = original_stdout # Restore stdout before printing error details
                tb_lines = traceback.format_exc().splitlines()
                specific_error_line_detail = f"RUNTIME ERROR: {type(e).__name__}: {e}"
                for tbl_line in reversed(tb_lines): # Find the line from our exec
                    if '<in_memory_code>' in tbl_line:
                        specific_error_line_detail = f"RUNTIME ERROR: {type(e).__name__}: {e} (Near: {tbl_line.strip()})"
                        break
                error_output_for_llm = f"{type(e).__name__}: {e}\nFull Traceback:\n" + "\n".join(tb_lines)
                LAST_SCRIPT_STDERR_MESSAGE = error_output_for_llm
                print(f"\n{ERROR_COLOR}{specific_error_line_detail}. Attempting to fix...{RESET_COLOR}")

                fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
                if fixed_code.startswith("#LLM_ERR"): print(f"{ERROR_COLOR}{fixed_code}{RESET_COLOR}")
                elif fixed_code == code_buffer_to_exec: print(f"{WARNING_COLOR}LLM: No change proposed.{RESET_COLOR}")
                else: print(f"{SUCCESS_COLOR}LLM: Proposed a fix.{RESET_COLOR}"); code_buffer_to_exec = fixed_code; fixed_this_run = True
            finally:
                if sys.stdout != original_stdout: # Ensure stdout is restored
                    sys.stdout = original_stdout
                
                output_str_from_exec = captured_output_io.getvalue()
                if output_str_from_exec: # Print captured output if any
                   original_stdout.write(output_str_from_exec)
                stdout_lines_capture.extend(output_str_from_exec.splitlines())
                LAST_SCRIPT_STDOUT_LINES = stdout_lines_capture[:]
                
                print_to_original_stdout(f"{CODE_OUTPUT_HEADER_COLOR}--- Live Python Output End (In-Memory) ---{RESET_COLOR}", flush=True)
                if execution_successful: # If exec was successful and we are in finally
                    output_summary = " ".join(stdout_lines_capture).strip()
                    if output_summary:
                        summary_for_desc = output_summary[:150] + "..." if len(output_summary) > 150 else output_summary
                        LAST_SUCCESSFUL_TASK_DESCRIPTION += f"\nScript Output Summary (In-Memory): {summary_for_desc}"

        captured_output_io.close()

    return code_buffer_to_exec, fixed_this_run, execution_successful, stdout_lines_capture, error_output_for_llm


def start_code_in_background(file_path_to_start):
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if not file_path_to_start : print(f"{WARNING_COLOR}!No Python file path provided.{RESET_COLOR}"); return
    if not os.path.exists(file_path_to_start): print(f"{ERROR_COLOR}!File to start not found: '{file_path_to_start}'{RESET_COLOR}"); return
    if ACTIVE_SUBPROCESS and ACTIVE_SUBPROCESS.poll() is None: print(f"{WARNING_COLOR}!Process ({ACTIVE_SUBPROCESS_FILE}) already running. Use 'stop'.{RESET_COLOR}"); return
    
    print(f"{POOP_MSG_COLOR}Starting '{file_path_to_start}' in background...{RESET_COLOR}")
    try:
        child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
        ACTIVE_SUBPROCESS = subprocess.Popen(
            [sys.executable, file_path_to_start], stdout=sys.stdout, stderr=sys.stderr, # Direct output to POOP's console
            text=True, encoding='utf-8', errors='replace', env=child_env
        )
        ACTIVE_SUBPROCESS_FILE = file_path_to_start
        print(f"{SUCCESS_COLOR}'{file_path_to_start}' now running in background (PID: {ACTIVE_SUBPROCESS.pid}). Use 'stop' to terminate.{RESET_COLOR}")
    except FileNotFoundError: print(f"{ERROR_COLOR}!ERROR: Python interpreter '{sys.executable}' not found.{RESET_COLOR}"); ACTIVE_SUBPROCESS=None
    except Exception as e: print(f"{ERROR_COLOR}!ERROR starting process: {e}{RESET_COLOR}"); ACTIVE_SUBPROCESS=None

def stop_active_subprocess():
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if ACTIVE_SUBPROCESS:
        if ACTIVE_SUBPROCESS.poll() is None: # Process is running
            print(f"{POOP_MSG_COLOR}Stopping background process '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid})...{RESET_COLOR}");
            ACTIVE_SUBPROCESS.terminate() # Send SIGTERM
            try:
                ACTIVE_SUBPROCESS.wait(timeout=5) # Wait for graceful termination
                print(f"{SUCCESS_COLOR}Process stopped.{RESET_COLOR}")
            except subprocess.TimeoutExpired:
                print(f"{WARNING_COLOR}!SIGTERM timeout, sending SIGKILL to '{ACTIVE_SUBPROCESS_FILE}'...{RESET_COLOR}");
                ACTIVE_SUBPROCESS.kill() # Force kill
                ACTIVE_SUBPROCESS.wait() # Wait for SIGKILL to be processed
                print(f"{SUCCESS_COLOR}Process killed.{RESET_COLOR}")
        else:
            print(f"{POOP_MSG_COLOR}Background process '{ACTIVE_SUBPROCESS_FILE}' was already stopped (Exit code: {ACTIVE_SUBPROCESS.poll()}).{RESET_COLOR}")
        ACTIVE_SUBPROCESS = None; ACTIVE_SUBPROCESS_FILE = None
    else:
        print(f"{POOP_MSG_COLOR}No active background process to stop.{RESET_COLOR}")

def get_process_status():
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if ACTIVE_SUBPROCESS:
        poll_result = ACTIVE_SUBPROCESS.poll()
        status = f"{SUCCESS_COLOR}running{RESET_COLOR}" if poll_result is None else f"{WARNING_COLOR}stopped (Exit Code: {poll_result}){RESET_COLOR}"
        print(f"{POOP_MSG_COLOR}Background process '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid}) is {status}.")
    else:
        print(f"{POOP_MSG_COLOR}No active background process information.{RESET_COLOR}")

def handle_image_analysis_signal(script_stdout_lines_list, image_path_from_plan_dependency=None):
    image_path_to_analyze = None
    signal_found_in_stdout = False

    for line in script_stdout_lines_list:
        if line.startswith(IMAGE_ANALYSIS_SIGNAL):
            image_path_to_analyze = line.replace(IMAGE_ANALYSIS_SIGNAL, "").strip()
            signal_found_in_stdout = True
            print(f"\n{POOP_MSG_COLOR}POOP: Script signaled image analysis for: '{image_path_to_analyze}'{RESET_COLOR}")
            break

    if not image_path_to_analyze and image_path_from_plan_dependency:
        image_path_to_analyze = image_path_from_plan_dependency
        print(f"\n{POOP_MSG_COLOR}POOP: Using image from plan dependency for analysis: '{image_path_to_analyze}'{RESET_COLOR}")

    if image_path_to_analyze:
        if not os.path.isabs(image_path_to_analyze) and CURRENT_TARGET_FILE:
            # If path is relative, assume it's relative to the script's directory
            script_dir = os.path.dirname(CURRENT_TARGET_FILE)
            image_path_to_analyze = os.path.join(script_dir, image_path_to_analyze)
            image_path_to_analyze = os.path.abspath(image_path_to_analyze)
            print(f"{POOP_MSG_COLOR}POOP: Resolved relative image path to: '{image_path_to_analyze}'{RESET_COLOR}")


        if os.path.exists(image_path_to_analyze):
            try:
                pil_img = Image.open(image_path_to_analyze)
                # Ensure image is in a compatible format (e.g., RGB) if needed by the model
                if pil_img.mode not in ['RGB', 'RGBA']: # Common modes; some models might prefer RGB
                    pil_img = pil_img.convert('RGB')
                print(f"{POOP_MSG_COLOR}POOP: Requesting AI description for '{os.path.basename(image_path_to_analyze)}'...{RESET_COLOR}")
                description = gmc_multimodal(pil_img) # pil_img is PIL.Image object
                pil_img.close()

                if description.startswith("#LLM_ERR"):
                    print(f"{ERROR_COLOR}POOP: AI Error during image description: {description}{RESET_COLOR}")
                    return False # Analysis attempted but failed
                else:
                    print(f"{POOP_MSG_COLOR}POOP AI Description of '{os.path.basename(image_path_to_analyze)}':{RESET_COLOR}\n---\n{AI_RESPONSE_COLOR}{description}{RESET_COLOR}\n---")
                    global LAST_SUCCESSFUL_TASK_DESCRIPTION
                    LAST_SUCCESSFUL_TASK_DESCRIPTION += f"\nAI image description of '{os.path.basename(image_path_to_analyze)}' (summary): {description[:100]}..."
                    return True # Analysis successful
            except Exception as e_img:
                print(f"{ERROR_COLOR}POOP: Error processing or analyzing image '{image_path_to_analyze}': {e_img}{RESET_COLOR}")
        else:
            print(f"{ERROR_COLOR}POOP: Error - Image path for analysis does not exist: '{image_path_to_analyze}'{RESET_COLOR}")
        return False # Path issue or processing error
    return signal_found_in_stdout # True if signal was just found but no path, False if no signal and no dep.


if __name__ == "__main__":
    try:
        from PIL import Image
    except ImportError:
        print(f"{ERROR_COLOR}!Pillow library (for image handling) is missing. Please install it: `pip install Pillow`{RESET_COLOR}")
        sys.exit(1)

    if not GAK:
        print_centered("🔑 GOOGLE_API_KEY environment variable is missing.", WARNING_COLOR)
        print_centered(f"   You can obtain an API key from: {API_KEY_LINK}", WARNING_COLOR)
        GAK_input = input(f"   {WARNING_COLOR}Please paste your GOOGLE_API_KEY here or set the environment variable and restart: {RESET_COLOR}").strip()
        if not GAK_input:
            print_centered("🔴 No API key provided. Exiting.", ERROR_COLOR)
            sys.exit(1)
        else:
            os.environ["GOOGLE_API_KEY"] = GAK_input # Set for current session
            GAK = GAK_input
            print_centered("✅ API key accepted for this session.", SUCCESS_COLOR)
    else:
        print_centered("✅ GOOGLE_API_KEY found.", SUCCESS_COLOR)

    if not init_llm():
        sys.exit(1)
    print("-" * shutil.get_terminal_size(fallback=(80,24)).columns)
    print_centered(f"Welcome to POOP ({POOP_NAME})", BRIGHT_WHITE_COLOR)
    print_poop_ascii_art()
    print_centered(f"Type 'h' or 'help' for commands. Your current model is {M_CURRENT_TEXT_MODEL.model_name}.", POOP_MSG_COLOR)
    print("-" * shutil.get_terminal_size(fallback=(80,24)).columns)
    current_code_buffer = ""

    while True:
        try:
            print() # Add a blank line for spacing before the prompt
            user_input_raw = ""
            POOP_PROMPT_COLOR = random.choice(_BASE_COLORS) # Vary prompt color

            if PLAN_STEP_FAILED_INFO:
                failed_step_task_display = PLAN_STEP_FAILED_INFO['step_task']
                if CURRENT_PLAN_STEPS and PLAN_STEP_FAILED_INFO['index'] < len(CURRENT_PLAN_STEPS): # Defensive check
                    failed_step_task_display = CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']].get('task', failed_step_task_display)

                print(f"\n{WARNING_COLOR}POOP: Plan step {PLAN_STEP_FAILED_INFO['index'] + 1} ('{failed_step_task_display}') failed.{RESET_COLOR}")
                print(f"{WARNING_COLOR}Reason: {PLAN_STEP_FAILED_INFO['reason'][:200]}{'...' if len(PLAN_STEP_FAILED_INFO['reason']) > 200 else ''}{RESET_COLOR}")
                retry_choice = input(f"{POOP_PROMPT_COLOR}Action: [R]etry, [M]odify & Retry, [S]kip, [A]bort plan, or new instruction: {RESET_COLOR}").strip().lower()
                
                if retry_choice == 'r':
                    print(f"{POOP_MSG_COLOR}POOP: Retrying failed step...{RESET_COLOR}")
                    if PLAN_STEP_FAILED_INFO.get('code_at_failure'):
                         current_code_buffer = PLAN_STEP_FAILED_INFO['code_at_failure'] # Restore code state at failure
                    PLAN_STEP_FAILED_INFO = None # Clear failure state for retry
                    user_input_raw = "#POOP_CONTINUE_PLAN" # Signal to continue plan logic
                elif retry_choice == 'm':
                    new_instr_for_step = input(f"{POOP_PROMPT_COLOR}New instruction/clarification for step '{failed_step_task_display}': {RESET_COLOR}").strip()
                    if new_instr_for_step:
                        # Update the task description of the failed step
                        CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']]['task'] = new_instr_for_step
                        # Optionally, store the original for reference, or just overwrite
                        CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']]['original_task_if_modified'] = failed_step_task_display
                        print(f"{POOP_MSG_COLOR}POOP: Modified instruction for step {PLAN_STEP_FAILED_INFO['index'] + 1}. Retrying with new instruction...{RESET_COLOR}")
                        
                        is_additive_at_failure = CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']].get("additive_code", False)
                        if not is_additive_at_failure:
                            # If the failed step was not additive, its code was standalone.
                            # Modification implies regenerating code for this step, so clear previous attempt.
                            current_code_buffer = "" # Or, could try to pass PLAN_STEP_FAILED_INFO['code_at_failure'] to gmc for modification
                        # If additive, gmc will receive the existing current_code_buffer (which includes prior steps' code)
                        # and will try to generate the modified part for the current step.
                        
                        PLAN_STEP_FAILED_INFO = None # Clear failure state
                        user_input_raw = "#POOP_CONTINUE_PLAN" # Signal to re-process this step
                    else:
                        print(f"{WARNING_COLOR}POOP: No modification provided. Plan remains paused at failed step.{RESET_COLOR}")
                elif retry_choice == 's':
                    print(f"{POOP_MSG_COLOR}POOP: Skipping failed step {PLAN_STEP_FAILED_INFO['index'] + 1}.{RESET_COLOR}")
                    PLAN_STEP_INDEX = PLAN_STEP_FAILED_INFO['index'] + 1 # Advance past the failed step
                    PLAN_STEP_FAILED_INFO = None
                    # Decide on code buffer: if next step is non-additive, it will clear. If additive, it will use current.
                    # For simplicity, let's clear it if a step is skipped, assuming next step starts fresh or is first additive.
                    # current_code_buffer = "" # This might be too aggressive if next step is additive.
                                            # Let next step's additive logic handle current_code_buffer.

                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS):
                        print(f"\n{POOP_MSG_COLOR}🤖 POOP: Plan ended (last step was skipped).{RESET_COLOR}")
                        CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0
                    else:
                        user_input_raw = "#POOP_CONTINUE_PLAN" # Continue with the new PLAN_STEP_INDEX
                elif retry_choice == 'a':
                    print(f"{POOP_MSG_COLOR}POOP: Plan aborted by user.{RESET_COLOR}")
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = "" # Clear code buffer after aborting plan
                else: # Assumed to be a new instruction
                    user_input_raw = retry_choice
                    # Reset all plan state as user is giving a new top-level instruction
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = "" # New instruction means new code context

            elif PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
                # Automatically continue plan if no failure and steps remain
                user_input_raw = "#POOP_CONTINUE_PLAN"
            else:
                # Standard input prompt
                user_input_raw = input(f"{POOP_PROMPT_COLOR}POOP> {RESET_COLOR}").strip()
                if not user_input_raw: continue


            parts = user_input_raw.lower().split(maxsplit=1)
            command, argument = parts[0], parts[1] if len(parts) > 1 else ""
            current_system_info = get_system_info()

            if command in ['exit', 'quit', 'q']:
                stop_active_subprocess()
                if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE) and CURRENT_TARGET_FILE.startswith("poop"):
                    del_q = input(f"{WARNING_COLOR}Delete temporary POOP file '{CURRENT_TARGET_FILE}'? (y/N): {RESET_COLOR}").lower()
                    if del_q == 'y':
                        try:
                            os.remove(CURRENT_TARGET_FILE)
                            print(f"{POOP_MSG_COLOR}'{CURRENT_TARGET_FILE}' deleted.{RESET_COLOR}")
                        except Exception as e:
                            print(f"{ERROR_COLOR}!Error deleting '{CURRENT_TARGET_FILE}': {e}{RESET_COLOR}")
                print(f"\n{BRIGHT_WHITE_COLOR}{FAREWELL}{RESET_COLOR}\n"); break
            elif command in ['help', 'h']:
                update_cmds_display() # Ensure it's fresh
                print(f"\n{BRIGHT_WHITE_COLOR}{CMDS}{RESET_COLOR}")
            elif command == "sysinfo":
                print(f"\n{POOP_MSG_COLOR}--- System Information ---{RESET_COLOR}")
                for k, v_sys in current_system_info.items():
                    print(f"{BRIGHT_WHITE_COLOR}{k.replace('_',' ').title()}:{RESET_COLOR} {v_sys}")
                print(f"{POOP_MSG_COLOR}--------------------------{RESET_COLOR}")
            elif command in ['model', 'm']:
                if argument:
                    target_model_obj = None
                    multi_short = M_MULTI_CAPABLE_MODEL.model_name.split('/')[-1] if M_MULTI_CAPABLE_MODEL else ""
                    light_short = M_LIGHT_MODEL.model_name.split('/')[-1] if M_LIGHT_MODEL else ""

                    if M_MULTI_CAPABLE_MODEL and (argument == multi_short or argument == "primary" or argument == M_MULTI_CAPABLE_MODEL.model_name) :
                        target_model_obj = M_MULTI_CAPABLE_MODEL
                    elif M_LIGHT_MODEL and (argument == light_short or argument == "light" or argument == M_LIGHT_MODEL.model_name):
                        target_model_obj = M_LIGHT_MODEL
                    
                    if target_model_obj:
                        M_CURRENT_TEXT_MODEL = target_model_obj
                        print(f"{SUCCESS_COLOR}Current text model set to: '{M_CURRENT_TEXT_MODEL.model_name}'.{RESET_COLOR}")
                    else:
                        print(f"{ERROR_COLOR}!Model '{argument}' unknown or unavailable.{RESET_COLOR}")
                        if M_MULTI_CAPABLE_MODEL: print(f"  {POOP_MSG_COLOR}Primary available: '{M_MULTI_CAPABLE_MODEL.model_name}' (aliases: primary, {multi_short}){RESET_COLOR}")
                        if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"  {POOP_MSG_COLOR}Light available: '{M_LIGHT_MODEL.model_name}' (aliases: light, {light_short}){RESET_COLOR}")
                else:
                    print(f"{POOP_MSG_COLOR}Current text model: {M_CURRENT_TEXT_MODEL.model_name if M_CURRENT_TEXT_MODEL else 'N/A'}{RESET_COLOR}")
                    if M_MULTI_CAPABLE_MODEL: print(f"  {POOP_MSG_COLOR}Primary: {M_MULTI_CAPABLE_MODEL.model_name}{RESET_COLOR}")
                    if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"  {POOP_MSG_COLOR}Light:   {M_LIGHT_MODEL.model_name}{RESET_COLOR}")

            elif command == "run":
                if not current_code_buffer.strip(): print(f"{WARNING_COLOR}!No code in buffer to run.{RESET_COLOR}"); continue
                
                confirmed_to_run = False
                if CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN or current_code_buffer != LAST_CODE_FOR_CONFIRMATION:
                    print(f"\n{AI_RESPONSE_COLOR}--- Code for Execution Review ---{RESET_COLOR}\n{current_code_buffer}\n{AI_RESPONSE_COLOR}-------------------------------{RESET_COLOR}")
                    confirm = input(f"{WARNING_COLOR}Execute this code? (y/N): {RESET_COLOR}").strip().lower()
                    if confirm == 'y':
                        confirmed_to_run = True
                        LAST_CODE_FOR_CONFIRMATION = current_code_buffer # Mark as confirmed
                    else:
                        print(f"{POOP_MSG_COLOR}Execution cancelled by user.{RESET_COLOR}")
                else: # Code hasn't changed since last confirmation (or was never LLM-modified and run before)
                    confirmed_to_run = True 
                
                if confirmed_to_run:
                    target_file_for_run_cmd = CURRENT_TARGET_FILE
                    code_to_run = current_code_buffer # Use the main buffer

                    if not target_file_for_run_cmd and current_code_buffer.strip(): # Ad-hoc run without 'f' command
                        target_file_for_run_cmd = generate_unique_poop_filename()
                        # Add a comment to this temp file for context if it's ever reviewed
                        code_to_run_with_comment = add_comment_to_code(current_code_buffer, f"Ad-hoc execution of user instruction: {LAST_USER_INSTRUCTION}")
                        print(f"{POOP_MSG_COLOR}Using temporary file for this run: {target_file_for_run_cmd}{RESET_COLOR}")
                    elif target_file_for_run_cmd: # If a target file is set, ensure it's up-to-date
                        code_to_run_with_comment = current_code_buffer # Assume it already has comments or doesn't need them here
                    else: # Should not happen if current_code_buffer has content
                        code_to_run_with_comment = current_code_buffer

                    # Execute the code (either from buffer directly if in-memory, or via file)
                    ran_code_buffer, fixed, successful, script_stdout_lines, exec_error_msg = execute_code(
                        code_to_run_with_comment, # Pass the potentially commented version
                        LAST_USER_INSTRUCTION,
                        LAST_SUCCESSFUL_TASK_DESCRIPTION,
                        file_path=target_file_for_run_cmd # Pass file path if one is determined
                    )

                    if fixed and ran_code_buffer != code_to_run_with_comment: # If LLM fixed it
                        current_code_buffer = ran_code_buffer # Update main buffer with the fix
                        # If a temp file was used, it was already written by execute_code with the original attempt.
                        # The fixed code is now in current_code_buffer. If user runs again, new temp file or existing.
                        if target_file_for_run_cmd: # If a file was used, re-write it with the fix.
                            try:
                                with open(target_file_for_run_cmd, "w", encoding='utf-8') as f_fix: f_fix.write(current_code_buffer)
                                print(f"{POOP_MSG_COLOR}Fixed code saved to '{target_file_for_run_cmd}'.{RESET_COLOR}")
                            except Exception as e_fix_save:
                                print(f"{ERROR_COLOR}!Error saving fixed code to '{target_file_for_run_cmd}': {e_fix_save}{RESET_COLOR}")


                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = fixed # If fixed, it's "modified by LLM"
                    if fixed:
                        LAST_CODE_FOR_CONFIRMATION = "" # Requires re-confirmation if run again

                    if exec_error_msg and exec_error_msg.startswith(MODULE_INSTALL_SIGNAL):
                        # Module was installed, don't clear successful task desc.
                        print(f"{POOP_MSG_COLOR}POOP: A required module was installed. Please 'run' the command again to use the module.{RESET_COLOR}")
                    elif successful and not fixed:
                        LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION # Update on successful, un-fixed run
                    elif not successful :
                        LAST_SUCCESSFUL_TASK_DESCRIPTION = "" # Clear if execution failed

                    if successful: # Even if fixed, if it ultimately succeeded.
                        handle_image_analysis_signal(script_stdout_lines)
            
            elif command == "chat":
                if not M_CURRENT_TEXT_MODEL:
                    print(f"{ERROR_COLOR}!LLM not available for chat.{RESET_COLOR}")
                    continue

                chat_context_parts = [
                    "You are POOP, an AI assistant. The user wants to chat with you. Here's the recent context:",
                    f"Last high-level user instruction to POOP: \"{LAST_USER_INSTRUCTION}\"",
                ]
                if current_code_buffer.strip():
                    code_summary = current_code_buffer
                    if len(code_summary) > 700: # Summarize if too long for chat context
                        code_summary = current_code_buffer[:350] + "\n...\n(code truncated for chat context)\n...\n" + current_code_buffer[-350:]
                    chat_context_parts.append(f"Current code in buffer:\n```python\n{code_summary}\n```")
                else:
                    chat_context_parts.append("The code buffer is currently empty.")

                if LAST_SUCCESSFUL_TASK_DESCRIPTION:
                    chat_context_parts.append(f"Last successful task/event description: \"{LAST_SUCCESSFUL_TASK_DESCRIPTION}\"")
                
                if PLAN_CONFIRMED and CURRENT_PLAN_STEPS:
                    current_step_info = "Plan is active. "
                    if PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
                        current_step_info += f"Currently at step {PLAN_STEP_INDEX + 1}/{len(CURRENT_PLAN_STEPS)}: '{CURRENT_PLAN_STEPS[PLAN_STEP_INDEX].get('task', 'N/A')}'."
                    else:
                        current_step_info += "All plan steps seem to be completed."
                    chat_context_parts.append(current_step_info)
                elif PLAN_STEP_FAILED_INFO:
                     chat_context_parts.append(f"A plan step recently failed: Step {PLAN_STEP_FAILED_INFO['index'] + 1} ('{PLAN_STEP_FAILED_INFO['step_task']}'). Reason: {PLAN_STEP_FAILED_INFO['reason']}")


                if LAST_SCRIPT_STDOUT_LINES:
                    output_preview = "\n".join(LAST_SCRIPT_STDOUT_LINES[:10]) # Show first 10 lines
                    if len(LAST_SCRIPT_STDOUT_LINES) > 10: output_preview += "\n... (stdout truncated)"
                    chat_context_parts.append(f"Last script's standard output (stdout) preview:\n```\n{output_preview}\n```")
                
                if LAST_SCRIPT_STDERR_MESSAGE:
                     chat_context_parts.append(f"Last script's error message (stderr):\n```\n{LAST_SCRIPT_STDERR_MESSAGE[:500]}{'...' if len(LAST_SCRIPT_STDERR_MESSAGE)>500 else ''}\n```")


                user_chat_query = argument if argument else "What are your thoughts on the current situation or the last operation? What should I consider doing next, or are there any potential issues you foresee based on this context?"
                chat_context_parts.append(f"\nUser's specific chat query: \"{user_chat_query}\"")
                chat_context_parts.append("\nPlease provide a concise, helpful, and conversational response. If you suggest code changes, provide them in brief or conceptually unless asked for full code.")

                full_chat_prompt = "\n\n".join(chat_context_parts)
                # print(f"DEBUG CHAT PROMPT: {full_chat_prompt}") # For debugging
                print(f"{POOP_MSG_COLOR}POOP: Asking LLM to chat (model: {M_CURRENT_TEXT_MODEL.model_name})...{RESET_COLOR}")
                
                response_text = gmtc(full_chat_prompt)
                
                if response_text.startswith("#LLM_ERR"):
                    print(f"{ERROR_COLOR}{response_text}{RESET_COLOR}")
                else:
                    print(f"\n{CHAT_LLM_RESPONSE_COLOR}POOP Chat:{RESET_COLOR}\n{response_text}")


            elif command == "start":
                target_f_start = argument if argument else CURRENT_TARGET_FILE
                
                if not current_code_buffer.strip() and not (target_f_start and os.path.exists(target_f_start)):
                    print(f"{WARNING_COLOR}!No code in buffer and no existing file specified to start.{RESET_COLOR}"); continue

                code_to_start_from_buffer = current_code_buffer # Code from buffer is primary if exists
                
                if not target_f_start and code_to_start_from_buffer.strip(): # No file given, but buffer has code
                    target_f_start = generate_unique_poop_filename()
                    final_code_to_write = add_comment_to_code(code_to_start_from_buffer, f"Background execution started for: {LAST_USER_INSTRUCTION}")
                    print(f"{POOP_MSG_COLOR}Using new temporary file for background process: {target_f_start}{RESET_COLOR}")
                    # Do not set CURRENT_TARGET_FILE here, 'start' is ephemeral for the process
                elif target_f_start and code_to_start_from_buffer.strip(): # File given, buffer has code -> overwrite file
                     final_code_to_write = code_to_start_from_buffer # Assume buffer is what user wants to run
                     print(f"{POOP_MSG_COLOR}Will write current buffer to '{target_f_start}' before starting.{RESET_COLOR}")
                elif target_f_start and not code_to_start_from_buffer.strip() and os.path.exists(target_f_start): # File given, buffer empty, file exists
                    final_code_to_write = None # Signal to just run existing file
                    print(f"{POOP_MSG_COLOR}Starting existing file '{target_f_start}' in background.{RESET_COLOR}")
                elif target_f_start and not code_to_start_from_buffer.strip() and not os.path.exists(target_f_start): # File given, buffer empty, file NOT exists
                    print(f"{ERROR_COLOR}!Specified file '{target_f_start}' does not exist and code buffer is empty.{RESET_COLOR}")
                    continue
                else: # Should be covered
                    print(f"{ERROR_COLOR}!Internal error in 'start' command logic.{RESET_COLOR}")
                    continue


                if final_code_to_write: # If there's code to write (from buffer)
                    try:
                        with open(target_f_start, "w", encoding='utf-8') as f_write: f_write.write(final_code_to_write)
                        print(f"{POOP_MSG_COLOR}Code successfully written to '{target_f_start}'.{RESET_COLOR}")
                        start_code_in_background(target_f_start)
                    except Exception as e:
                        print(f"{ERROR_COLOR}!Error writing code to '{target_f_start}': {e}{RESET_COLOR}")
                elif target_f_start and os.path.exists(target_f_start): # No code to write, just run existing file
                    start_code_in_background(target_f_start)
                # else case handled above

                # Mark buffer as "used" for confirmation purposes if it was written
                if code_to_start_from_buffer.strip() and final_code_to_write:
                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False # Assumes 'start' means it's tested/finalized by user
                    LAST_CODE_FOR_CONFIRMATION = code_to_start_from_buffer
                    # LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION # Starting a process is a kind of success

            elif command == "stop": stop_active_subprocess()
            elif command == "status_process": get_process_status()
            elif command == "img_desc":
                if not argument: print(f"{WARNING_COLOR}!Path to image file is required for 'img_desc'.{RESET_COLOR}"); continue
                if not M_MULTI_CAPABLE_MODEL: print(f"{ERROR_COLOR}!Multimodal model is not available for image description.{RESET_COLOR}"); continue
                
                try:
                    image_path_arg = os.path.abspath(argument)
                    if not os.path.exists(image_path_arg):
                        print(f"{ERROR_COLOR}!Image file not found at: '{image_path_arg}'{RESET_COLOR}"); continue
                    
                    pil_image = Image.open(image_path_arg)
                    if pil_image.mode not in ['RGB', 'RGBA']: pil_image = pil_image.convert('RGB')
                    
                    print(f"{POOP_MSG_COLOR}Generating description for image '{os.path.basename(image_path_arg)}'...{RESET_COLOR}");
                    description = gmc_multimodal(pil_image) # Pass PIL.Image object
                    pil_image.close()
                    
                    if description.startswith("#LLM_ERR"):
                        print(f"{ERROR_COLOR}Error during image description: {description}{RESET_COLOR}")
                    else:
                        print(f"\n{AI_RESPONSE_COLOR}--- Image Description ---\n{description}\n------------------------{RESET_COLOR}")
                except Exception as e:
                    print(f"{ERROR_COLOR}!Error processing image for 'img_desc': {e}{RESET_COLOR}")

            elif command == "show":
                print(f"\n{POOP_MSG_COLOR}--- Current POOP Status ---{RESET_COLOR}")
                print(f"{BRIGHT_WHITE_COLOR}Target File:{RESET_COLOR} {CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else 'In-Memory / Auto-generated per plan'}")
                if current_code_buffer.strip():
                    print(f"{BRIGHT_WHITE_COLOR}Code Buffer ({len(current_code_buffer)} bytes):{RESET_COLOR}\n{'-'*30}\n{current_code_buffer}\n{'-'*30}")
                else:
                    print(f"{BRIGHT_WHITE_COLOR}Code Buffer:{RESET_COLOR} {WARNING_COLOR}(empty){RESET_COLOR}")
                
                if LAST_USER_INSTRUCTION: print(f"{BRIGHT_WHITE_COLOR}Last User Instruction:{RESET_COLOR} {LAST_USER_INSTRUCTION}")
                if LAST_SUCCESSFUL_TASK_DESCRIPTION: print(f"{BRIGHT_WHITE_COLOR}Last Successful Task/Event:{RESET_COLOR} {LAST_SUCCESSFUL_TASK_DESCRIPTION}")
                
                if LAST_SCRIPT_STDOUT_LINES:
                    stdout_preview = "\n".join(LAST_SCRIPT_STDOUT_LINES[:5])
                    if len(LAST_SCRIPT_STDOUT_LINES) > 5: stdout_preview += "\n... (more)"
                    print(f"{BRIGHT_WHITE_COLOR}Last Script STDOUT (preview):{RESET_COLOR}\n{stdout_preview}")
                if LAST_SCRIPT_STDERR_MESSAGE:
                    print(f"{BRIGHT_WHITE_COLOR}Last Script STDERR:{RESET_COLOR} {ERROR_COLOR}{LAST_SCRIPT_STDERR_MESSAGE[:200]}{'...' if len(LAST_SCRIPT_STDERR_MESSAGE)>200 else ''}{RESET_COLOR}")


                if CURRENT_PLAN_TEXT:
                    print(f"\n{POOP_PLAN_COLOR}--- Active Plan ---{RESET_COLOR}")
                    for i, step_show in enumerate(CURRENT_PLAN_STEPS):
                        status_char = "❌" if PLAN_STEP_FAILED_INFO and PLAN_STEP_FAILED_INFO['index'] == i else \
                                      ("✅" if i < PLAN_STEP_INDEX else \
                                      ("⏳" if i == PLAN_STEP_INDEX and PLAN_CONFIRMED else "📋"))
                        modified_marker = f"{WARNING_COLOR} (modified from original task){RESET_COLOR}" if 'original_task_if_modified' in step_show else ""
                        print(f"{status_char} {i+1}. {step_show.get('task','N/A')}{modified_marker}")
                        if i == PLAN_STEP_INDEX and PLAN_CONFIRMED and not PLAN_STEP_FAILED_INFO:
                            print(f"    {POOP_MSG_COLOR}(This is the next step to be executed){RESET_COLOR}")
                        elif PLAN_STEP_FAILED_INFO and PLAN_STEP_FAILED_INFO['index'] == i:
                            print(f"    {ERROR_COLOR}(This step failed - awaiting user action: Retry, Modify, Skip, Abort){RESET_COLOR}")
                    
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and PLAN_CONFIRMED and not PLAN_STEP_FAILED_INFO:
                        print(f"{SUCCESS_COLOR}🎉 Plan Fully Completed!{RESET_COLOR}")
                    elif not PLAN_CONFIRMED and CURRENT_PLAN_STEPS and not PLAN_STEP_FAILED_INFO:
                        print(f"{WARNING_COLOR}🕒 Plan is generated and awaiting user confirmation to proceed.{RESET_COLOR}")
                print(f"{POOP_MSG_COLOR}---------------------------{RESET_COLOR}")


            elif command == "clear":
                current_code_buffer = "";
                LAST_USER_INSTRUCTION = "print('Hello from POOP!')"; # Reset to default
                LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                LAST_SCRIPT_STDOUT_LINES = []
                LAST_SCRIPT_STDERR_MESSAGE = None
                
                # Don't delete CURRENT_TARGET_FILE automatically, user might want to keep it.
                # If it was a temp file, 'exit' handles it. If user-set, it persists.
                # CURRENT_TARGET_FILE = None # Resetting this means next op might create new temp. User can use 'f none'.

                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False;
                LAST_CODE_FOR_CONFIRMATION = ""
                
                CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                
                print(f"{POOP_MSG_COLOR}Code buffer, task history, and active plan cleared. Target file association remains unless changed with 'f'.{RESET_COLOR}");
                update_cmds_display()


            elif command in ["file", "f"]:
                if argument.lower() == "none" or argument.lower() == "--clear":
                    if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE) and CURRENT_TARGET_FILE.startswith("poop"): # Temp file
                        del_q = input(f"{WARNING_COLOR}Current target '{CURRENT_TARGET_FILE}' seems like a POOP temp file. Delete it? (y/N): {RESET_COLOR}").lower()
                        if del_q == 'y':
                            try: os.remove(CURRENT_TARGET_FILE); print(f"{POOP_MSG_COLOR}'{CURRENT_TARGET_FILE}' deleted.{RESET_COLOR}")
                            except Exception as e: print(f"{ERROR_COLOR}!Error deleting '{CURRENT_TARGET_FILE}': {e}{RESET_COLOR}")
                    
                    CURRENT_TARGET_FILE = None;
                    print(f"{POOP_MSG_COLOR}Target file association cleared. Operations will use in-memory or auto-generate temporary files as needed.{RESET_COLOR}");
                    LAST_SUCCESSFUL_TASK_DESCRIPTION = "" # Context changes
                elif argument:
                    new_target_file = os.path.abspath(argument);
                    CURRENT_TARGET_FILE = new_target_file
                    print(f"{POOP_MSG_COLOR}Target file set to: '{CURRENT_TARGET_FILE}'.{RESET_COLOR}")
                    if os.path.exists(CURRENT_TARGET_FILE):
                        try:
                            with open(CURRENT_TARGET_FILE, 'r', encoding='utf-8') as f_read: current_code_buffer = f_read.read()
                            print(f"{POOP_MSG_COLOR}Loaded code from '{CURRENT_TARGET_FILE}' ({len(current_code_buffer)} bytes) into buffer.{RESET_COLOR}")
                            LAST_USER_INSTRUCTION = f"# Code loaded from file: {os.path.basename(CURRENT_TARGET_FILE)}"
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Loaded code from file '{CURRENT_TARGET_FILE}'"
                        except Exception as e:
                            print(f"{ERROR_COLOR}!Error loading code from '{CURRENT_TARGET_FILE}': {e}{RESET_COLOR}");
                            current_code_buffer = "" # Clear buffer on load error
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                    else:
                        print(f"{POOP_MSG_COLOR}File '{CURRENT_TARGET_FILE}' does not exist yet. It will be created if code is generated and saved/run.{RESET_COLOR}");
                        current_code_buffer = "" # New file means empty buffer
                        LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                else: # No argument, just show current
                    print(f"{POOP_MSG_COLOR}Current Target File: {CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else 'In-Memory / Auto-generated per plan'}{RESET_COLOR}")

                # Changing file association or loading code means confirmation status resets
                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False
                LAST_CODE_FOR_CONFIRMATION = current_code_buffer # What's in buffer is now "confirmed" by this action
                update_cmds_display()


            elif command == "#poop_continue_plan" or (not (CURRENT_PLAN_TEXT or PLAN_STEP_FAILED_INFO)):
                # This block handles both explicit plan continuation and new user instructions that trigger planning.
                if command != "#poop_continue_plan": # New user instruction, not internal continuation
                    LAST_USER_INSTRUCTION = user_input_raw
                    # Reset plan state for a new top-level instruction
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = "" # New user instruction implies starting fresh with code, unless 'f' was used.
                    LAST_SUCCESSFUL_TASK_DESCRIPTION = "" # Reset this as well for a new goal
                    # CURRENT_TARGET_FILE might persist if set by 'f', otherwise new plan might make new files.

                # --- Plan Execution Logic ---
                if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO:
                    current_step_details_exec = CURRENT_PLAN_STEPS[PLAN_STEP_INDEX]
                    step_task_exec = current_step_details_exec.get('task', f"Unnamed Plan Step {PLAN_STEP_INDEX + 1}")
                    is_additive_step_exec = current_step_details_exec.get("additive_code", False)
                    
                    print(f"\n{POOP_MSG_COLOR}🤖 POOP Plan Step {PLAN_STEP_INDEX + 1}/{len(CURRENT_PLAN_STEPS)}: {RESET_COLOR}{BRIGHT_WHITE_COLOR}{step_task_exec}{RESET_COLOR} {'(Additive Code)' if is_additive_step_exec else '(New/Replace Code)'}")

                    if current_step_details_exec.get("requires_code_gen", True):
                        instruction_for_gmc_step = f"Implement the following plan step: {step_task_exec}."
                        if current_step_details_exec.get('details'):
                            instruction_for_gmc_step += f" Specific details for this step: {current_step_details_exec['details']}."
                        
                        # Determine code base for gmc: if additive, use current_code_buffer; if not, gmc gets empty.
                        code_base_for_gmc_step = current_code_buffer if is_additive_step_exec else ""
                        
                        if not is_additive_step_exec:
                            # For non-additive, if a target file is set by user, we might overwrite it.
                            # If no target file, or if it's not the first step, generate a new one.
                            if not CURRENT_TARGET_FILE or (CURRENT_TARGET_FILE and PLAN_STEP_INDEX > 0):
                                CURRENT_TARGET_FILE = generate_unique_poop_filename()
                                print(f"{POOP_MSG_COLOR}POOP: Non-additive step. Using new/dedicated target file: '{CURRENT_TARGET_FILE}'{RESET_COLOR}")
                            current_code_buffer = "" # Clear main buffer for non-additive step's new code
                        elif is_additive_step_exec and not current_code_buffer.strip() and not CURRENT_TARGET_FILE:
                            # First additive step in a sequence, and no prior code/file. Create a new target file.
                            CURRENT_TARGET_FILE = generate_unique_poop_filename()
                            print(f"{POOP_MSG_COLOR}POOP: First additive step in sequence. Using new target file: '{CURRENT_TARGET_FILE}'{RESET_COLOR}")
                        elif is_additive_step_exec and current_code_buffer.strip() and not CURRENT_TARGET_FILE:
                            # Additive, buffer has code (e.g. from 'f'), but no file yet. Create one.
                            CURRENT_TARGET_FILE = generate_unique_poop_filename()
                            print(f"{POOP_MSG_COLOR}POOP: Additive step with existing buffer content. Using new target file for combined code: '{CURRENT_TARGET_FILE}'{RESET_COLOR}")
                        
                        update_cmds_display() # If CURRENT_TARGET_FILE changed

                        print(f"{POOP_MSG_COLOR}POOP: Generating code for this step...{RESET_COLOR}")
                        gmc_plan_context_step = {
                            "full_plan": CURRENT_PLAN_TEXT,
                            "current_step_description": step_task_exec,
                            "current_step_details": current_step_details_exec.get('details', 'N/A'),
                            "requires_user_input_during_step": current_step_details_exec.get('requires_user_input_during_step'),
                            "screenshot_analysis_signal": current_step_details_exec.get('screenshot_analysis_signal', False),
                            "overall_goal": LAST_USER_INSTRUCTION, # The plan's overall goal
                            "is_additive": is_additive_step_exec
                        }
                        generated_code_for_step_exec = gmc(
                            code_base_for_gmc_step,
                            instruction_for_gmc_step,
                            previous_task_context_for_code_gen=LAST_SUCCESSFUL_TASK_DESCRIPTION, # Context from *previous* step's success
                            system_info_for_code_gen=current_system_info,
                            plan_context_for_code_gen=gmc_plan_context_step
                        )

                        if generated_code_for_step_exec.startswith("#LLM_ERR"):
                            PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"LLM code generation failed for step: {generated_code_for_step_exec}", 'step_task': step_task_exec, 'code_at_failure': current_code_buffer} # Save buffer before modification attempt
                        elif not generated_code_for_step_exec.strip() and current_step_details_exec.get("requires_code_gen", True):
                             # LLM returned no code for a step that requires code gen
                            print(f"{WARNING_COLOR}LLM returned no code for step '{step_task_exec}', but code was expected.{RESET_COLOR}")
                            PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': "LLM generated no code where code was expected.", 'step_task': step_task_exec, 'code_at_failure': current_code_buffer}
                        elif generated_code_for_step_exec.strip(): # Code was generated
                            step_comment_info_exec = {'num': PLAN_STEP_INDEX + 1, 'total': len(CURRENT_PLAN_STEPS)}
                            overall_goal_comment = LAST_USER_INSTRUCTION if PLAN_CONFIRMED else None # Add overall goal only if part of a plan

                            if is_additive_step_exec:
                                separator = "\n\n" if current_code_buffer.strip() else ""
                                new_code_part_with_comment = add_comment_to_code(generated_code_for_step_exec, f"Additive part for: {step_task_exec}", True, step_comment_info_exec, overall_goal_comment)
                                current_code_buffer += separator + new_code_part_with_comment
                            else: # New or replacement code
                                current_code_buffer = add_comment_to_code(generated_code_for_step_exec, step_task_exec, True, step_comment_info_exec, overall_goal_comment)
                            
                            CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True; LAST_CODE_FOR_CONFIRMATION = "" # Needs review if 'run' cmd used later

                            if not CURRENT_TARGET_FILE: # Should ideally be set by now if code is generated
                                CURRENT_TARGET_FILE = generate_unique_poop_filename()
                                print(f"{WARNING_COLOR}!POOP: Target file was not set before code execution, using new temporary file: {CURRENT_TARGET_FILE}{RESET_COLOR}")
                                update_cmds_display()

                            # Save the (potentially combined) code to the target file before execution
                            if CURRENT_TARGET_FILE:
                                try:
                                    with open(CURRENT_TARGET_FILE, "w", encoding='utf-8') as f_w_step: f_w_step.write(current_code_buffer)
                                    # print(f"{POOP_MSG_COLOR}Code for step {PLAN_STEP_INDEX + 1} {'appended to' if is_additive_step_exec and code_base_for_gmc_step else 'saved to'} '{CURRENT_TARGET_FILE}'.{RESET_COLOR}")
                                except Exception as e_save_step:
                                    print(f"{ERROR_COLOR}!Error saving code to '{CURRENT_TARGET_FILE}' for step execution: {e_save_step}{RESET_COLOR}")
                                    PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"Failed to save code to file: {e_save_step}", 'step_task': step_task_exec, 'code_at_failure': current_code_buffer}
                                    # Don't proceed to execute if save failed

                            if not PLAN_STEP_FAILED_INFO: # Only execute if save (if attempted) was okay
                                executed_code_buffer_step, fixed_by_llm_after_exec_step, successful_exec_step, script_stdout_lines_step, exec_error_msg_step = execute_code(
                                    current_code_buffer, # Execute the full current buffer
                                    instruction_for_gmc_step, # Context for potential fix
                                    LAST_SUCCESSFUL_TASK_DESCRIPTION, # Prev step's success context
                                    file_path=CURRENT_TARGET_FILE, # Execute from this file
                                    auto_run_source=f"POOP (Plan Step {PLAN_STEP_INDEX + 1}) "
                                )

                                if fixed_by_llm_after_exec_step and executed_code_buffer_step != current_code_buffer:
                                    current_code_buffer = executed_code_buffer_step # Update main buffer with fix
                                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True; LAST_CODE_FOR_CONFIRMATION = ""
                                    # Re-save the fixed code to the file
                                    if CURRENT_TARGET_FILE:
                                        try:
                                            with open(CURRENT_TARGET_FILE, "w", encoding='utf-8') as f_fix_step: f_fix_step.write(current_code_buffer)
                                        except Exception as e_fix_save_step:
                                            print(f"{ERROR_COLOR}!Error saving fixed code to '{CURRENT_TARGET_FILE}': {e_fix_save_step}{RESET_COLOR}")


                                if exec_error_msg_step and exec_error_msg_step.startswith(MODULE_INSTALL_SIGNAL):
                                    # Module was installed. The current step needs to be retried.
                                    # Do not advance PLAN_STEP_INDEX. PLAN_STEP_FAILED_INFO is not set.
                                    # The next loop iteration will re-trigger '#POOP_CONTINUE_PLAN' for the same step.
                                    print(f"{POOP_MSG_COLOR}POOP: A module was installed. Retrying step {PLAN_STEP_INDEX + 1} automatically.{RESET_COLOR}")
                                elif successful_exec_step:
                                    LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Successfully completed plan step {PLAN_STEP_INDEX + 1}: {step_task_exec} (Part of overall goal: {LAST_USER_INSTRUCTION})"
                                    PLAN_STEP_INDEX += 1
                                    handle_image_analysis_signal(script_stdout_lines_step) # Handle signal from successful script
                                else: # Execution failed and wasn't a module install fix
                                    PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"Execution of step failed. Error: {exec_error_msg_step or 'Unknown execution error'}", 'step_task': step_task_exec, 'code_at_failure': current_code_buffer}
                        else: # No code generated, but step did not require code gen (e.g. requires_code_gen: No)
                             LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Acknowledged plan step {PLAN_STEP_INDEX + 1} (no code generation required): {step_task_exec}"; PLAN_STEP_INDEX += 1


                    else: # Step does not require code generation (e.g., manual action or POOP internal AI action)
                        action_completed_non_code = False;
                        action_desc_non_code = current_step_details_exec.get('requires_user_action', '')
                        
                        if action_desc_non_code:
                            print(f"{WARNING_COLOR}ACTION REQUIRED FOR STEP {PLAN_STEP_INDEX + 1}:{RESET_COLOR} {BRIGHT_WHITE_COLOR}{action_desc_non_code}{RESET_COLOR}")
                            
                            # Check for POOP internal AI image analysis based on action description
                            if "POOP will use its AI to describe the image at" in action_desc_non_code or \
                               "POOP to analyze image" in action_desc_non_code: # More flexible check
                                
                                img_path_from_action_desc = None
                                # Try to extract path from action description itself
                                img_path_match_action = re.search(r"(?:image at|path to|file)\s*['\"]?([/\w\.\-:\\]+\.(?:png|jpg|jpeg|bmp|gif))['\"]?", action_desc_non_code, re.IGNORECASE)
                                if img_path_match_action:
                                    img_path_from_action_desc = img_path_match_action.group(1).strip()
                                
                                # Also check dependencies field for a path
                                dependencies_text_non_code = current_step_details_exec.get('dependencies', '')
                                img_path_match_deps = re.search(r"(?:path to|image at|file)\s*['\"]?([/\w\.\-:\\]+\.(?:png|jpg|jpeg|bmp|gif))['\"]?", dependencies_text_non_code, re.IGNORECASE)
                                if img_path_match_deps and not img_path_from_action_desc: # Prefer path from action if both found
                                     img_path_from_action_desc = img_path_match_deps.group(1).strip()

                                if img_path_from_action_desc:
                                    if handle_image_analysis_signal([], img_path_from_action_desc): # Pass empty stdout, provide path from plan
                                        action_completed_non_code = True
                                    else: # Image analysis failed
                                        PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"AI image analysis (non-code step) failed for path: {img_path_from_action_desc}", 'step_task': step_task_exec}
                                else: # Could not determine image path for analysis
                                    print(f"{WARNING_COLOR}POOP: Could not automatically determine image path for AI analysis from plan description. Please ensure the image is available and, if needed, use 'img_desc' command manually or clarify path.{RESET_COLOR}")
                                    # Fall through to manual confirmation
                                    user_confirms_action_done = input(f"{POOP_PROMPT_COLOR}POOP: Has this non-code action been completed, or necessary information provided? (y/N): {RESET_COLOR}").strip().lower()
                                    if user_confirms_action_done == 'y': action_completed_non_code = True
                            else: # General non-code user action
                                user_confirms_action_done = input(f"{POOP_PROMPT_COLOR}POOP: Has this manual step been completed? (y/N): {RESET_COLOR}").strip().lower()
                                if user_confirms_action_done == 'y': action_completed_non_code = True
                        else: # No specific action described, assume step is informational or self-completing
                            action_completed_non_code = True 
                        
                        if action_completed_non_code:
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Completed non-code plan step {PLAN_STEP_INDEX + 1}: {step_task_exec}"
                            PLAN_STEP_INDEX += 1
                        elif not PLAN_STEP_FAILED_INFO: # Action not completed, and not already marked as failed
                            print(f"{WARNING_COLOR}Plan paused. Please complete the required non-code action for step {PLAN_STEP_INDEX + 1}.{RESET_COLOR}")
                            # Plan will not advance, user will be prompted again or can issue new command

                    # Check if plan is fully completed
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO:
                        print(f"\n{SUCCESS_COLOR}🎉 POOP: Plan Succeeded! All {len(CURRENT_PLAN_STEPS)} steps completed for goal: '{LAST_USER_INSTRUCTION}'.{RESET_COLOR}")
                        CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0
                        # current_code_buffer might contain the final script of the plan. User can 'show', 'run', or 'clear' it.

                # --- Plan Generation Logic ---
                elif not CURRENT_PLAN_TEXT and command != "#poop_continue_plan" and not PLAN_STEP_FAILED_INFO:
                    # User provided a new instruction, and no plan is active or failed. Time to generate a plan.
                    print(f"{POOP_MSG_COLOR}🤖 POOP: Received new instruction: '{LAST_USER_INSTRUCTION}'. Generating a plan...{RESET_COLOR}")
                    load_past_poop_files_context() # Refresh past files context for new plan
                    plan_text_output_gen = gmp(LAST_USER_INSTRUCTION, current_system_info, PAST_POOP_FILES_CONTEXT)

                    if plan_text_output_gen.startswith("#LLM_ERR"):
                        print(f"{ERROR_COLOR}{plan_text_output_gen}{RESET_COLOR}")
                    elif not plan_text_output_gen.strip():
                        print(f"{ERROR_COLOR}LLM returned an empty plan. Please try rephrasing your instruction or check model status.{RESET_COLOR}")
                    else:
                        CURRENT_PLAN_TEXT = plan_text_output_gen;
                        CURRENT_PLAN_STEPS = parse_plan(CURRENT_PLAN_TEXT)
                        if not CURRENT_PLAN_STEPS:
                            print(f"{ERROR_COLOR}Could not parse the plan generated by LLM. Raw plan text was:{RESET_COLOR}\n{CURRENT_PLAN_TEXT}");
                            CURRENT_PLAN_TEXT = "" # Clear invalid plan
                        else:
                            print(f"\n{POOP_PLAN_COLOR}--- POOP Proposed Plan ({len(CURRENT_PLAN_STEPS)} steps) ---{RESET_COLOR}")
                            for i, step_disp_gen in enumerate(CURRENT_PLAN_STEPS):
                                print(f"{i+1}. {BRIGHT_WHITE_COLOR}{step_disp_gen.get('task','N/A')}{RESET_COLOR}")
                            print(f"{POOP_PLAN_COLOR}-----------------------------------{RESET_COLOR}")
                            
                            confirm_plan_input = input(f"{WARNING_COLOR}Proceed with this plan? (y/N/edit): {RESET_COLOR}").strip().lower()
                            if confirm_plan_input == 'y':
                                PLAN_CONFIRMED = True; PLAN_STEP_INDEX = 0;
                                # Reset file/buffer for the new plan, unless user explicitly set a file they want to use as base
                                if not CURRENT_TARGET_FILE: # If user hasn't fixed a file with 'f', plan starts clean.
                                    current_code_buffer = ""
                                # If CURRENT_TARGET_FILE is set, the first step of the plan will decide to use/overwrite it.
                                LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Plan confirmed by user for: {LAST_USER_INSTRUCTION}"
                                print(f"{SUCCESS_COLOR}Plan confirmed. Starting execution...{RESET_COLOR}")
                                # The loop will now go to #POOP_CONTINUE_PLAN logic on next iteration.
                            elif confirm_plan_input == 'edit':
                                print(f"{WARNING_COLOR}Plan editing is not yet implemented. Please refine your initial instruction to generate a new plan, or reject this one.{RESET_COLOR}");
                                CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = [] # Discard plan
                            else: # 'n' or anything else
                                print(f"{POOP_MSG_COLOR}Plan rejected by user.{RESET_COLOR}");
                                CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = [] # Discard plan
                
                elif command == "#poop_continue_plan" and (not PLAN_CONFIRMED or PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS)) and not PLAN_STEP_FAILED_INFO:
                    # This case means #POOP_CONTINUE_PLAN was called, but there's no valid plan state to continue.
                    # E.g., plan finished, was aborted, or never confirmed.
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and CURRENT_PLAN_STEPS: # Plan actually finished
                         print(f"{POOP_MSG_COLOR}🤖 POOP: Plan previously finished. Please provide a new instruction.{RESET_COLOR}");
                         CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0
                    # else: No active plan to continue. Loop will reprompt.

        except KeyboardInterrupt:
            print(f"\n{WARNING_COLOR}POOP> Input/Operation cancelled by user (Ctrl+C).{RESET_COLOR}")
            if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO :
                # If a plan was running and not already failed, mark current step as failed due to interruption
                PLAN_STEP_FAILED_INFO = {
                    'index': PLAN_STEP_INDEX,
                    'reason': "User Interruption (Ctrl+C)",
                    'step_task': CURRENT_PLAN_STEPS[PLAN_STEP_INDEX].get('task', 'N/A'),
                    'code_at_failure': current_code_buffer # Save current code state
                }
                print(f"{WARNING_COLOR}Current plan step {PLAN_STEP_INDEX + 1} marked as interrupted. You can [R]etry, [M]odify, [S]kip, or [A]bort.{RESET_COLOR}")
            # If no plan was active, or it was already failed, just go back to prompt.
        except Exception as e:
            print(f"\n{ERROR_COLOR}!UNEXPECTED POOP LOOP ERROR: {e}{RESET_COLOR}");
            traceback.print_exc()
            if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO:
                 PLAN_STEP_FAILED_INFO = {
                    'index': PLAN_STEP_INDEX,
                    'reason': f"Unexpected POOP Loop Error: {e}",
                    'step_task': CURRENT_PLAN_STEPS[PLAN_STEP_INDEX].get('task', 'N/A'),
                    'code_at_failure': current_code_buffer
                }
                 print(f"{ERROR_COLOR}Due to the unexpected error, plan step {PLAN_STEP_INDEX + 1} is marked as failed. You can [R]etry, [M]odify, [S]kip, or [A]bort.{RESET_COLOR}")
