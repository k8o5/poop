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

COLORS = [
    "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[34m", "\x1b[35m", "\x1b[36m",
    "\x1b[91m", "\x1b[92m", "\x1b[93m", "\x1b[94m", "\x1b[95m", "\x1b[96m",
]
RESET_COLOR = "\x1b[0m"
BRIGHT_WHITE_COLOR = "\x1b[97m"

IMAGE_ANALYSIS_SIGNAL = "#POOP_ANALYZE_IMAGE_PATH:"
MODULE_INSTALL_SIGNAL = "#POOP_INSTALLED_MODULE:"


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
show: Display the current Python code buffer and active plan (if any).
clear: Clear Python code buffer, task history, and active plan. Resets confirmation status and target file.
m(odel) [name/alias]: Change LLM. Aliases: 'primary', 'light'. Full names or short names also work.
                      Available: '{{multi_model_name_short}}' (primary), '{{light_model_name_short}}' (light).
img_desc [path]: Describe an image using POOP's multimodal AI.
f(ile) [path]: Set Python target file. 'f none' for in-memory/auto-file per plan.
               Loads code if file exists, resets confirmation and task history.
sysinfo: Display detected system information.
[any other text]: Generate a plan. If confirmed, POOP executes step-by-step.
                  Failed plan steps offer retry/skip/abort options.
                  POOP will attempt to `pip install` missing modules if ModuleNotFoundError occurs.
                  Planner favors additive code for iterative tasks like game dev.
                  Scripts signaling '{IMAGE_ANALYSIS_SIGNAL} <filepath>' trigger AI image analysis.
                  Code from approved plan steps runs without individual confirmation.
"""
CMDS = ""

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
    art_color = BRIGHT_WHITE_COLOR
    for line in art:
        print(f"{art_color}{line}{RESET_COLOR}")
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
    # Check if the very first non-empty line is already a POOP comment to avoid duplication if re-commenting a fragment
    first_code_line_index = 0
    for i, line in enumerate(existing_lines):
        if line.strip():
            first_code_line_index = i
            break
    if existing_lines and existing_lines[first_code_line_index].startswith("# POOP:"):
        return code_content # Already has a POOP comment at the start of actual code
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
                pass
        if PAST_POOP_FILES_CONTEXT:
            print(f"Context from {len(PAST_POOP_FILES_CONTEXT)} recent POOP files loaded.")
    except Exception as e:
        print(f"!Error scanning for past POOP files: {e}")

def init_llm(model_name_primary='gemini-2.5-flash-preview-05-20', model_name_secondary='gemini-2.0-flash'):
    global GAK, M_CURRENT_TEXT_MODEL, M_MULTI_CAPABLE_MODEL, M_LIGHT_MODEL
    if not GAK: return False

    model_name_primary = model_name_primary.strip().rstrip(',')
    model_name_secondary = model_name_secondary.strip().rstrip(',')

    try:
        genai.configure(api_key=GAK)
        try:
            M_MULTI_CAPABLE_MODEL = genai.GenerativeModel(model_name_primary)
            print(f"Primary LLM ({model_name_primary}): Initialized.")
        except Exception as e:
            print(f"!Init {model_name_primary} (Primary) FAILED: {e}")
            M_MULTI_CAPABLE_MODEL = None

        if model_name_primary != model_name_secondary:
            try:
                M_LIGHT_MODEL = genai.GenerativeModel(model_name_secondary)
                print(f"Secondary LLM ({model_name_secondary}): Initialized.")
            except Exception as e:
                print(f"!Init {model_name_secondary} (Secondary) FAILED: {e}")
                M_LIGHT_MODEL = None
        elif M_MULTI_CAPABLE_MODEL:
            M_LIGHT_MODEL = M_MULTI_CAPABLE_MODEL
            print(f"Secondary LLM is same as Primary ({model_name_secondary}).")

        if M_MULTI_CAPABLE_MODEL:
            M_CURRENT_TEXT_MODEL = M_MULTI_CAPABLE_MODEL
        elif M_LIGHT_MODEL:
            M_CURRENT_TEXT_MODEL = M_LIGHT_MODEL
            print("!Warning: Primary model failed or unavailable, using secondary model.")

        if M_CURRENT_TEXT_MODEL:
            print(f"Current text model set to: {M_CURRENT_TEXT_MODEL.model_name}")
        else:
            print("!No LLM could be initialized as current text model.")
            update_cmds_display()
            return False

        load_past_poop_files_context()
        update_cmds_display()
        return True
    except Exception as e:
        print(f"!General LLM Init FAILED: {e}")
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
            else:
                finish_reason_val = candidate.finish_reason
        else:
            finish_reason_val = "UNKNOWN"

        if not candidate.content or not candidate.content.parts:
            safety_ratings_str = str(candidate.safety_ratings) if hasattr(candidate, 'safety_ratings') else "N/A"
            if finish_reason_val == "STOP" or finish_reason_val == 1:
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

    except ValueError as ve:
        return f"#LLM_ERR: Error accessing response text from {model_name_for_error_msg} (ValueError): {ve}. Candidate finish_reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}"
    except AttributeError as ae:
        return f"#LLM_ERR: Attribute error processing LLM response from {model_name_for_error_msg}: {ae}. Candidate: {str(candidate)[:200]}"
    except Exception as e:
        return f"#LLM_ERR: Unexpected error processing LLM response from {model_name_for_error_msg}: {e}\n{traceback.format_exc()}"

def gmp(user_instruction_for_plan, system_info_for_plan, past_files_context_for_plan):
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
Recent POOP Activity:
---
{past_context_str}
---
Plan Instructions:
1. Numbered steps (1., 2., 3.).
2. For each step, define:
    - `Task:` Concise action.
    - `Details:` (Optional) Specifics.
    - `Dependencies:` (Optional) Relies on previous output, libraries (e.g., 'pygame'), tools, user info, file paths. If a library is needed, explicitly state it.
    - `Outcome:` Achieved/produced.
    - `Requires_Code_Gen:` (Yes/No) Does POOP generate Python?
    - `Additive_Code:` (Yes/No, if Requires_Code_Gen: Yes) Add to previous code or standalone? Default No.
        **IMPORTANT**: If the overall user request implies building a single, evolving application (e.g., "make a pygame game", "develop a desktop app", "create a data analysis script with multiple plots"),
        **MOST code-generating steps AFTER the initial setup step SHOULD BE `Additive_Code: Yes`**. This means code from the current step will be appended to the code from previous steps in the SAME FILE.
        The first code-generating step in such a sequence can be `Additive_Code: No` (or Yes if adding to an existing buffer).
    - `Requires_User_Input_During_Step:` (Optional) Python script prompts user for what?
    - `Requires_User_Action:` (Optional) Manual user action OR POOP internal non-code action (e.g., "POOP will use its AI to describe image at <path_from_previous_step>.").
    - `Screenshot_Analysis_Signal:` (Yes/No, if Requires_Code_Gen: Yes AND code *takes* screenshot for POOP AI analysis) If yes, code prints '{IMAGE_ANALYSIS_SIGNAL} <filepath>'.

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
        pattern_str = rf"^\s*{re.escape(field_name)}:\s*(.*?)(?=(" + "|".join(map(re.escape, stop_keywords_list)) + r")|$)"
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
    task_match = re.match(r"^\s*Task:\s*(.*?)(?=\n\s*(?:Details:|Dependencies:|Outcome:|Requires_Code_Gen:|$))", remaining_text, re.DOTALL | re.IGNORECASE)
    if task_match:
        details["task"] = task_match.group(1).strip()
        remaining_text = remaining_text[task_match.end():]
    else:
        temp_remaining_text = remaining_text
        for line in temp_remaining_text.splitlines():
            line_stripped = line.strip()
            if line_stripped and not any(f_kw.lower() in line_stripped.lower() for f_kw in all_fields_ordered[1:]):
                if details.get("task"): details["task"] += "\n" + line_stripped
                else: details["task"] = line_stripped
                remaining_text = remaining_text.replace(line, "", 1)
            elif details.get("task"): break
        if details.get("task"): details["task"] = details["task"].strip()

    for i, field_name_caps in enumerate(all_fields_ordered):
        if field_name_caps == "Task" and "task" in details: continue
        stop_kws = [f_kw + ":" for f_kw in all_fields_ordered[i+1:] if f_kw != field_name_caps]
        value = extract_field(field_name_caps, remaining_text, stop_kws)
        if value:
            field_key = current_field_map[field_name_caps]
            if field_key in ["requires_code_gen", "additive_code", "screenshot_analysis_signal"]:
                details[field_key] = (value.lower() == "yes")
            else:
                details[field_key] = value

    if "requires_code_gen" not in details: details["requires_code_gen"] = True
    if details["requires_code_gen"]:
        if "additive_code" not in details: details["additive_code"] = False
        if "screenshot_analysis_signal" not in details: details["screenshot_analysis_signal"] = False
    else:
        details["additive_code"] = False
        details["screenshot_analysis_signal"] = False
    return details

def parse_plan(plan_text_input):
    parsed_steps_list = []
    step_pattern = re.compile(r"^\s*(\d+)\.\s*(.*?)(?=(?:\n\s*\d+\.\s*)|$)", re.MULTILINE | re.DOTALL)
    matches = list(step_pattern.finditer(plan_text_input))

    if not matches and plan_text_input.strip():
        step_data = parse_plan_step_details(plan_text_input.strip())
        if step_data.get("task"): parsed_steps_list.append(step_data)
        elif plan_text_input.strip():
             parsed_steps_list.append({"task": plan_text_input.strip(), "requires_code_gen": True, "additive_code": False, "screenshot_analysis_signal": False})
        return parsed_steps_list

    for match_obj in matches:
        step_content_after_num = match_obj.group(2).strip()
        if not step_content_after_num: continue
        step_data = parse_plan_step_details(step_content_after_num)
        if step_data.get("task"): parsed_steps_list.append(step_data)
        else:
            if step_content_after_num:
                step_data["task"] = step_content_after_num.splitlines()[0]
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
        "You are a Python expert. Create, modify, or debug Python scripts. Use standard libraries. Add imports. Return ONLY raw Python code.",
        f"If task takes screenshot AND plan indicates 'Screenshot_Analysis_Signal: Yes' OR implies POOP analysis, script prints: '{IMAGE_ANALYSIS_SIGNAL} /path/to/screenshot.png' (actual path)."
    ]
    if is_additive_from_plan and current_code:
        prompt_parts.append("You are ADDING to existing code. Do NOT repeat imports or setup already present in the 'CURRENT SCRIPT' unless necessary for the new part. Focus on the new functionality.")


    if system_info_for_code_gen:
        prompt_parts.append("\n--- TARGET SYSTEM INFO ---")
        for key, value in system_info_for_code_gen.items(): prompt_parts.append(f"{key.replace('_', ' ').title()}: {value}")
        prompt_parts.append("Adapt script to this system (OS commands, paths).")

    if plan_context_for_code_gen:
        prompt_parts.append("\n--- EXECUTING PLAN STEP ---")
        prompt_parts.append(f"Overall Goal: {plan_context_for_code_gen.get('overall_goal', LAST_USER_INSTRUCTION)}")
        if plan_context_for_code_gen.get("full_plan"): prompt_parts.append(f"Full Plan (Context):\n{plan_context_for_code_gen['full_plan'][:500]}...")
        prompt_parts.append(f"Current Step: {plan_context_for_code_gen.get('current_step_description','N/A')}")
        if plan_context_for_code_gen.get("current_step_details"): prompt_parts.append(f"Details: {plan_context_for_code_gen['current_step_details']}")
        if previous_task_context_for_code_gen: prompt_parts.append(f"Prev. Step Context: {previous_task_context_for_code_gen}")
        prompt_parts.append(f"Generate Python for CURRENT STEP: {plan_context_for_code_gen.get('current_step_description','N/A')}.")
        if plan_context_for_code_gen.get("requires_user_input_during_step"):
            prompt_parts.append(f"Script MUST prompt user for: {plan_context_for_code_gen['requires_user_input_during_step']}")
        if plan_context_for_code_gen.get("screenshot_analysis_signal"):
            prompt_parts.append(f"This step has Screenshot_Analysis_Signal: Yes. Ensure script prints '{IMAGE_ANALYSIS_SIGNAL} <filepath>'.")
        if is_additive_from_plan:
            prompt_parts.append("This is an ADDITIVE step. The generated code will be appended to the existing script. Do not redefine existing functions/classes unless the goal is to modify them. Add new logic or extend existing logic.")


    if error_feedback:
        prompt_parts.append("\nTASK: Fix Python code based on error.")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
            prompt_parts.append(f"Script intended for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"Instruction for this code: {user_instruction_for_code_gen}")
        code_for_error_prompt = current_code
        if len(code_for_error_prompt) > 1500 :
            code_for_error_prompt = f"... (code truncated for brevity) ...\n{current_code[-1500:]}"
        prompt_parts.append(f"FAULTY CODE (or relevant part):\n```python\n{code_for_error_prompt}\n```")
        prompt_parts.append(f"ERROR:\n```\n{error_feedback}\n```")
        prompt_parts.append("FIXED PYTHON CODE (code only):")
    elif current_code : # This implies either modifying an existing script (could be additive base) or first part of additive
        task_type = "Add to the existing script" if is_additive_from_plan else "Modify the existing script"
        prompt_parts.append(f"\nTASK: {task_type}.")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
             prompt_parts.append(f"This work is for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"CURRENT SCRIPT (the code you are adding to or modifying):\n```python\n{current_code}\n```")
        prompt_parts.append(f"NEW INSTRUCTION (what to add or change): {user_instruction_for_code_gen}")
        prompt_parts.append("PYTHON SCRIPT (only the new code if additive, or full modified code if not additive):")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True
    else: # No current_code, so generate new script from scratch
        prompt_parts.append("\nTASK: Create new Python script.")
        if plan_context_for_code_gen and plan_context_for_code_gen.get("current_step_description"):
            prompt_parts.append(f"New script for plan step: {plan_context_for_code_gen['current_step_description']}")
        prompt_parts.append(f"INSTRUCTION: {user_instruction_for_code_gen}")
        prompt_parts.append("PYTHON SCRIPT (code only):")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True

    full_prompt = "\n".join(prompt_parts)
    try:
        response = M_CURRENT_TEXT_MODEL.generate_content(full_prompt, generation_config=GCFG)
        output = get_llm_response_text(response, M_CURRENT_TEXT_MODEL.model_name)
        if output.startswith("#LLM_ERR"): return output
        if output.startswith("```python"): output = output[9:]
        elif output.startswith("```"): output = output[3:]
        if output.endswith("```"): output = output[:-3]
        return output.strip()
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during code generation with {M_CURRENT_TEXT_MODEL.model_name}: {e}"
    except Exception as e:
        return f"#LLM_ERR: Error during Python code generation with {M_CURRENT_TEXT_MODEL.model_name}: {e}\n{traceback.format_exc()}"

def gmc_multimodal(image_data, text_prompt="Describe this image in detail."):
    active_multimodal_model = M_MULTI_CAPABLE_MODEL if M_MULTI_CAPABLE_MODEL else M_CURRENT_TEXT_MODEL
    if not active_multimodal_model: return "#LLM_ERR: No suitable multimodal model initialized."
    content = [text_prompt, image_data]
    try:
        response = active_multimodal_model.generate_content(content, generation_config=GCFG)
        description = get_llm_response_text(response, active_multimodal_model.model_name)
        return description
    except google.api_core.exceptions.GoogleAPIError as e:
        return f"#LLM_ERR: API Error during multimodal generation with {active_multimodal_model.model_name}: {e}"
    except Exception as e:
        return f"#LLM_ERR: Error during multimodal generation with {active_multimodal_model.model_name}: {e}\n{traceback.format_exc()}"

def create_execution_scope():
    s = {"__builtins__": __builtins__}
    libs = [('os', 'os'), ('sys', 'sys'), ('subprocess', 'sp'), ('shutil', 'sh'), ('platform', 'platform'),
            ('requests', 'req'), ('json', 'json'), ('time', 'time'), ('random', 'random'), ('datetime', 'datetime'),
            ('pandas', 'pd'), ('numpy', 'np'), ('matplotlib.pyplot', 'plt')]
    try: import mss; s['mss'] = mss
    except ImportError: pass
    for lib_name, alias in libs:
        try: exec(f"import {lib_name} as {alias}", s)
        except ImportError: pass
    return s

def execute_code(code_buffer_to_exec, last_instruction_for_fix_context, previous_task_context_for_fix, file_path=None, auto_run_source=""):
    if not code_buffer_to_exec or not code_buffer_to_exec.strip():
        return code_buffer_to_exec, False, False, [], None

    print(f"{auto_run_source}Executing Python code ({'File: ' + file_path if file_path else 'In-Memory'})...")
    fixed_this_run = False
    execution_successful = False
    error_output_for_llm = None
    current_system_info_for_fix = get_system_info()
    stdout_lines_capture = []
    plan_context_for_fix_gmc = None
    if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
        current_step_fix = CURRENT_PLAN_STEPS[PLAN_STEP_INDEX]
        plan_context_for_fix_gmc = {
            "full_plan": CURRENT_PLAN_TEXT, "current_step_description": current_step_fix.get('task', 'N/A'),
            "current_step_details": current_step_fix.get('details', 'N/A'),
            "requires_user_input_during_step": current_step_fix.get('requires_user_input_during_step'),
            "screenshot_analysis_signal": current_step_fix.get('screenshot_analysis_signal', False),
            "overall_goal": LAST_USER_INSTRUCTION,
            "is_additive": current_step_fix.get("additive_code", False) # Pass additive info for fixing
        }

    if file_path:
        try:
            with open(file_path, "w", encoding='utf-8') as f: f.write(code_buffer_to_exec)
            child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [sys.executable, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8', env=child_env
            )
            stderr_capture_list = []
            print("--- Live Python Output Start ---", flush=True)
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    sys.stdout.write(line); sys.stdout.flush(); stdout_lines_capture.append(line.strip())
                process.stdout.close()
            if process.stderr:
                for line in iter(process.stderr.readline, ""):
                    sys.stderr.write(line); sys.stderr.flush(); stderr_capture_list.append(line.strip())
                process.stderr.close()
            process.wait(); return_code = process.returncode
            print("\n--- Live Python Output End ---", flush=True)

            if return_code != 0:
                raw_error_output = "\n".join(stderr_capture_list)
                error_output_for_llm = raw_error_output
                print(f"!Python process error (code {return_code}).")

                module_not_found_match = re.search(r"ModuleNotFoundError: No module named '([\w\.]+)'", raw_error_output)
                if module_not_found_match:
                    missing_module = module_not_found_match.group(1)
                    print(f"POOP: Detected missing module: '{missing_module}'")
                    install_confirm = input(f"Attempt to install '{missing_module}' using pip? (y/N): ").strip().lower()
                    if install_confirm == 'y':
                        print(f"POOP: Attempting 'pip install {missing_module}'...")
                        try:
                            pip_process = subprocess.run(
                                [sys.executable, "-m", "pip", "install", missing_module],
                                capture_output=True, text=True, check=False, timeout=120
                            )
                            if pip_process.returncode == 0:
                                print(f"POOP: Successfully installed '{missing_module}'.")
                                error_output_for_llm = f"{MODULE_INSTALL_SIGNAL}{missing_module}"
                                fixed_this_run = True
                            else:
                                print(f"!POOP: Failed to install '{missing_module}'. Pip output:\n{pip_process.stdout}\n{pip_process.stderr}")
                        except subprocess.TimeoutExpired:
                            print(f"!POOP: 'pip install {missing_module}' timed out.")
                        except Exception as e_pip:
                            print(f"!POOP: Error during pip install attempt: {e_pip}")
                    else:
                        print(f"POOP: Installation of '{missing_module}' skipped by user.")
                
                if not (error_output_for_llm and error_output_for_llm.startswith(MODULE_INSTALL_SIGNAL)):
                    print("Attempting to fix with LLM...")
                    # Pass the full buffer that failed for fixing context, especially if additive
                    fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
                    if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
                    elif fixed_code == code_buffer_to_exec: print("LLM: No change (error not fixed).") # Or if it's just a part, this comparison is tricky
                    else:
                        print("Fixed.");
                        # If it was an additive step, the fix should ideally be just the new part, or a modification to the whole buffer.
                        # For now, assume fix replaces the whole buffer if it was non-additive, or the LLM handled additive fix.
                        code_buffer_to_exec = fixed_code;
                        fixed_this_run = True
            else: print("Python execution OK."); execution_successful = True
        except FileNotFoundError:
            error_output_for_llm = f"Interpreter {sys.executable} not found."
            print(f"!ERROR: {error_output_for_llm}")
        except Exception as e:
            error_output_for_llm = f"File exec error: {e}\n{traceback.format_exc()}"
            print(f"!FILE EXECUTION ERROR: {e}. Fixing...")
            fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
            if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
            elif fixed_code == code_buffer_to_exec: print("LLM: No change.")
            else: print("Fixed."); code_buffer_to_exec = fixed_code; fixed_this_run = True
    else: # In-memory
        original_stdout = sys.stdout
        from io import StringIO
        captured_output = StringIO()
        sys.stdout = captured_output
        execution_scope, compiled_object, compile_error_msg = create_execution_scope(), None, None
        try: compiled_object = compile(code_buffer_to_exec, '<in_memory_code>', 'exec')
        except SyntaxError as se:
            compile_error_msg = f"SYNTAX Line {se.lineno}: {se.msg} `{(se.text or '').strip()}`\n{traceback.format_exc(limit=0)}"
        if compile_error_msg:
            sys.stdout = original_stdout
            error_output_for_llm = compile_error_msg
            print(f"COMPILE ERROR: {compile_error_msg.splitlines()[0]}. Fixing...")
            fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
            if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
            elif fixed_code == code_buffer_to_exec: print("LLM: No change.")
            else: print("Fixed."); code_buffer_to_exec = fixed_code; fixed_this_run = True
        elif compiled_object:
            execution_scope['__name__'] = '__main__'
            print_to_original_stdout = lambda *args, **kwargs: print(*args, file=original_stdout, **kwargs)
            print_to_original_stdout("--- Live Python Output Start (In-Memory) ---", flush=True)
            try:
                exec(compiled_object, execution_scope, execution_scope)
                print_to_original_stdout("\nPython execution OK."); execution_successful = True
            except SystemExit: print_to_original_stdout("\nExited."); execution_successful = True
            except KeyboardInterrupt: print_to_original_stdout("\nInterrupted.")
            except Exception as e:
                sys.stdout = original_stdout
                tb_lines = traceback.format_exc().splitlines()
                specific_error_line = f"RUNTIME ERROR: {type(e).__name__}: {e}"
                for tbl_line in reversed(tb_lines):
                    if '<in_memory_code>' in tbl_line: specific_error_line = f"RUNTIME ERROR: {type(e).__name__}: {e} (Near: {tbl_line.strip()})"; break
                error_output_for_llm = f"{type(e).__name__}: {e}\n" + "\n".join(tb_lines)
                print(f"\n{specific_error_line}. Fixing...")
                fixed_code = gmc(code_buffer_to_exec, last_instruction_for_fix_context, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix, plan_context_for_fix_gmc)
                if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
                elif fixed_code == code_buffer_to_exec: print("LLM: No change.")
                else: print("Fixed."); code_buffer_to_exec = fixed_code; fixed_this_run = True
            finally:
                sys.stdout = original_stdout
                output_str = captured_output.getvalue()
                original_stdout.write(output_str)
                stdout_lines_capture.extend(output_str.splitlines())
                print_to_original_stdout("--- Live Python Output End (In-Memory) ---", flush=True)
        captured_output.close()
    return code_buffer_to_exec, fixed_this_run, execution_successful, stdout_lines_capture, error_output_for_llm

def start_code_in_background(file_path_to_start):
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if not file_path_to_start : print("!No Python file path provided."); return
    if not os.path.exists(file_path_to_start): print(f"!File to start not found: '{file_path_to_start}'"); return
    if ACTIVE_SUBPROCESS and ACTIVE_SUBPROCESS.poll() is None: print(f"!Process ({ACTIVE_SUBPROCESS_FILE}) already running. Use 'stop'."); return
    print(f"Starting '{file_path_to_start}' in background...")
    try:
        child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
        ACTIVE_SUBPROCESS = subprocess.Popen(
            [sys.executable, file_path_to_start], stdout=sys.stdout, stderr=sys.stderr,
            text=True, encoding='utf-8', env=child_env
        )
        ACTIVE_SUBPROCESS_FILE = file_path_to_start
        print(f"'{file_path_to_start}' running (PID: {ACTIVE_SUBPROCESS.pid}). Use 'stop' to terminate.")
    except FileNotFoundError: print(f"!ERROR: Python interpreter '{sys.executable}' not found."); ACTIVE_SUBPROCESS=None
    except Exception as e: print(f"!ERROR starting process: {e}"); ACTIVE_SUBPROCESS=None

def stop_active_subprocess():
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if ACTIVE_SUBPROCESS:
        if ACTIVE_SUBPROCESS.poll() is None:
            print(f"Stopping '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid})..."); ACTIVE_SUBPROCESS.terminate()
            try: ACTIVE_SUBPROCESS.wait(timeout=5)
            except subprocess.TimeoutExpired: print("!SIGTERM timeout, sending SIGKILL..."); ACTIVE_SUBPROCESS.kill(); ACTIVE_SUBPROCESS.wait()
            print("Process stopped.")
        else: print(f"Background process '{ACTIVE_SUBPROCESS_FILE}' was already stopped.")
        ACTIVE_SUBPROCESS = None; ACTIVE_SUBPROCESS_FILE = None
    else: print("No active background process.")

def get_process_status():
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if ACTIVE_SUBPROCESS:
        poll_result = ACTIVE_SUBPROCESS.poll()
        status = "running" if poll_result is None else f"stopped (Exit: {poll_result})"
        print(f"Process '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid}) is {status}.")
    else: print("No background process information.")

def handle_image_analysis_signal(script_stdout_lines_list, image_path_from_plan_dependency=None):
    image_path_to_analyze = None
    signal_found_in_stdout = False

    for line in script_stdout_lines_list:
        if line.startswith(IMAGE_ANALYSIS_SIGNAL):
            image_path_to_analyze = line.replace(IMAGE_ANALYSIS_SIGNAL, "").strip()
            signal_found_in_stdout = True
            print(f"\nPOOP: Script signaled image analysis: '{image_path_to_analyze}'")
            break

    if not image_path_to_analyze and image_path_from_plan_dependency:
        image_path_to_analyze = image_path_from_plan_dependency
        print(f"\nPOOP: Using image from plan dependency for analysis: '{image_path_to_analyze}'")

    if image_path_to_analyze:
        if os.path.exists(image_path_to_analyze):
            try:
                pil_img = Image.open(image_path_to_analyze)
                if pil_img.mode != 'RGB': pil_img = pil_img.convert('RGB')
                print("POOP: Requesting AI description...")
                description = gmc_multimodal(pil_img)
                pil_img.close()
                if description.startswith("#LLM_ERR"):
                    print(f"POOP: AI Error: {description}")
                    return False
                else:
                    print(f"POOP AI Description of '{os.path.basename(image_path_to_analyze)}':\n---\n{description}\n---")
                    global LAST_SUCCESSFUL_TASK_DESCRIPTION
                    LAST_SUCCESSFUL_TASK_DESCRIPTION += f"\nAI image description: {description[:100]}..."
                    return True
            except Exception as e_img: print(f"POOP: Error analyzing image '{image_path_to_analyze}': {e_img}")
        else: print(f"POOP: Error - Image path does not exist: '{image_path_to_analyze}'")
        return False
    return signal_found_in_stdout

if __name__ == "__main__":
    try: from PIL import Image
    except ImportError: print("!Pillow library missing. `pip install Pillow`"); sys.exit(1)

    if not GAK:
        print("🔑 GOOGLE_API_KEY missing.")
        print(f"   Get it here: {API_KEY_LINK}")
        GAK_input = input("   Paste GOOGLE_API_KEY: ").strip()
        if not GAK_input: print("🔴 No API key. Exiting."); sys.exit(1)
        else: os.environ["GOOGLE_API_KEY"] = GAK_input; GAK = GAK_input; print("✅ API key OK.")
    else: print("✅ API key found.")

    if not init_llm(): sys.exit(1)

    print(f"\nWelcome to POOP ({POOP_NAME})")
    print_poop_ascii_art()
    print(f"Type 'h' or 'help' for commands.")
    print("----------------------------------------------------")
    current_code_buffer = ""

    while True:
        try:
            user_input_raw = ""
            if PLAN_STEP_FAILED_INFO:
                failed_step_task_display = PLAN_STEP_FAILED_INFO['step_task']
                if CURRENT_PLAN_STEPS and PLAN_STEP_FAILED_INFO['index'] < len(CURRENT_PLAN_STEPS):
                    failed_step_task_display = CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']].get('task', failed_step_task_display)

                print(f"\nPOOP: Plan step {PLAN_STEP_FAILED_INFO['index'] + 1} ('{failed_step_task_display}') failed.")
                print(f"Reason: {PLAN_STEP_FAILED_INFO['reason']}")
                retry_choice = input("Action: [R]etry, [M]odify & Retry, [S]kip, [A]bort, or new instruction: ").strip().lower()
                if retry_choice == 'r':
                    print("POOP: Retrying failed step...")
                    if PLAN_STEP_FAILED_INFO.get('code_at_failure'):
                         current_code_buffer = PLAN_STEP_FAILED_INFO['code_at_failure']
                    PLAN_STEP_FAILED_INFO = None
                    user_input_raw = "#POOP_CONTINUE_PLAN"
                elif retry_choice == 'm':
                    new_instr_for_step = input(f"New instruction for step '{failed_step_task_display}': ").strip()
                    if new_instr_for_step:
                        CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']]['task'] = new_instr_for_step
                        CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']]['original_task_if_modified'] = failed_step_task_display
                        print(f"POOP: Modified instruction for step {PLAN_STEP_FAILED_INFO['index'] + 1}. Retrying...")
                        # Forcing new code gen means clearing the current_code_buffer if it's not additive or it's the first part of additive
                        is_additive_at_failure = CURRENT_PLAN_STEPS[PLAN_STEP_FAILED_INFO['index']].get("additive_code", False)
                        if not is_additive_at_failure:
                            current_code_buffer = ""
                        # If additive, gmc will receive the existing current_code_buffer as base
                        PLAN_STEP_FAILED_INFO = None
                        user_input_raw = "#POOP_CONTINUE_PLAN"
                    else:
                        print("POOP: No modification provided. Plan remains paused at failed step.")
                elif retry_choice == 's':
                    print(f"POOP: Skipping failed step {PLAN_STEP_FAILED_INFO['index'] + 1}.")
                    PLAN_STEP_INDEX = PLAN_STEP_FAILED_INFO['index'] + 1
                    PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = "" # Clear buffer from failed step for next step
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS):
                        print("\n🤖 POOP: Plan ended (skipped last step).")
                        CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0
                    else:
                        user_input_raw = "#POOP_CONTINUE_PLAN"
                elif retry_choice == 'a':
                    print("POOP: Plan aborted by user.")
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = ""
                else:
                    user_input_raw = retry_choice
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = ""

            elif PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
                user_input_raw = "#POOP_CONTINUE_PLAN"
            else:
                prompt_color = random.choice(COLORS)
                user_input_raw = input(f"{prompt_color}POOP> {RESET_COLOR}").strip()
                if not user_input_raw: continue

            parts = user_input_raw.lower().split(maxsplit=1)
            command, argument = parts[0], parts[1] if len(parts) > 1 else ""
            current_system_info = get_system_info()

            if command in ['exit', 'quit', 'q']:
                stop_active_subprocess()
                if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE) and CURRENT_TARGET_FILE.startswith("poop"):
                    del_q = input(f"Delete temp file '{CURRENT_TARGET_FILE}'? (y/N): ").lower()
                    if del_q == 'y':
                        try: os.remove(CURRENT_TARGET_FILE); print(f"'{CURRENT_TARGET_FILE}' deleted.")
                        except Exception as e: print(f"!Error deleting '{CURRENT_TARGET_FILE}': {e}")
                print(f"\n{FAREWELL}\n"); break
            elif command in ['help', 'h']: update_cmds_display(); print(CMDS)
            elif command == "sysinfo":
                for k, v_sys in current_system_info.items(): print(f"{k.replace('_',' ').title()}: {v_sys}")
            elif command in ['model', 'm']:
                if argument:
                    target_model_obj = None
                    multi_short = M_MULTI_CAPABLE_MODEL.model_name.split('/')[-1] if M_MULTI_CAPABLE_MODEL else ""
                    light_short = M_LIGHT_MODEL.model_name.split('/')[-1] if M_LIGHT_MODEL else ""
                    if M_MULTI_CAPABLE_MODEL and (argument == multi_short or argument == "primary" or argument == M_MULTI_CAPABLE_MODEL.model_name) : target_model_obj = M_MULTI_CAPABLE_MODEL
                    elif M_LIGHT_MODEL and (argument == light_short or argument == "light" or argument == M_LIGHT_MODEL.model_name): target_model_obj = M_LIGHT_MODEL
                    if target_model_obj: M_CURRENT_TEXT_MODEL = target_model_obj; print(f"Model: '{M_CURRENT_TEXT_MODEL.model_name}'.")
                    else:
                        print(f"!Model '{argument}' unknown/unavailable.")
                        if M_MULTI_CAPABLE_MODEL: print(f"  Primary: '{M_MULTI_CAPABLE_MODEL.model_name}' (primary, {multi_short})")
                        if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"  Light: '{M_LIGHT_MODEL.model_name}' (light, {light_short})")
                else:
                    print(f"Current: {M_CURRENT_TEXT_MODEL.model_name if M_CURRENT_TEXT_MODEL else 'N/A'}")
                    if M_MULTI_CAPABLE_MODEL: print(f"Primary: {M_MULTI_CAPABLE_MODEL.model_name}")
                    if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"Light: {M_LIGHT_MODEL.model_name}")

            elif command == "run":
                if not current_code_buffer.strip(): print("!No code to run."); continue
                confirmed_to_run = False
                if CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN or current_code_buffer != LAST_CODE_FOR_CONFIRMATION:
                    print(f"\n--- Generated/Modified Code ---\n{current_code_buffer[:1000]}{'...' if len(current_code_buffer)>1000 else ''}\n-----------------------------")
                    confirm = input("Execute? (y/N): ").strip().lower()
                    if confirm == 'y': confirmed_to_run = True; LAST_CODE_FOR_CONFIRMATION = current_code_buffer
                    else: print("Execution cancelled.")
                else: confirmed_to_run = True
                if confirmed_to_run:
                    target_file_for_run_cmd = CURRENT_TARGET_FILE
                    code_to_run = current_code_buffer
                    if not target_file_for_run_cmd and current_code_buffer.strip(): # New temp file for ad-hoc run
                        target_file_for_run_cmd = generate_unique_poop_filename()
                        code_to_run = add_comment_to_code(current_code_buffer, LAST_USER_INSTRUCTION)

                    ran_code_buffer, fixed, successful, script_stdout_lines, exec_error_msg = execute_code(
                        code_to_run, LAST_USER_INSTRUCTION, LAST_SUCCESSFUL_TASK_DESCRIPTION, file_path=target_file_for_run_cmd
                    )
                    if fixed and ran_code_buffer != code_to_run:
                        current_code_buffer = ran_code_buffer

                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = fixed
                    if fixed: LAST_CODE_FOR_CONFIRMATION = ""

                    if exec_error_msg and exec_error_msg.startswith(MODULE_INSTALL_SIGNAL):
                        print("POOP: Module installed. Please 'run' again.")
                    elif successful and not fixed: LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION
                    elif not successful : LAST_SUCCESSFUL_TASK_DESCRIPTION = ""

                    if successful: handle_image_analysis_signal(script_stdout_lines)

            elif command == "start":
                target_f_start = argument if argument else CURRENT_TARGET_FILE
                if not current_code_buffer.strip() and not (target_f_start and os.path.exists(target_f_start)): print("!No code/file to start."); continue

                code_to_start = current_code_buffer
                if not target_f_start and current_code_buffer.strip():
                    target_f_start = generate_unique_poop_filename()
                    code_to_start = add_comment_to_code(current_code_buffer, LAST_USER_INSTRUCTION)
                    CURRENT_TARGET_FILE = target_f_start; update_cmds_display()

                if code_to_start.strip(): # Ensure there's code to write
                    try:
                        with open(target_f_start, "w", encoding='utf-8') as f_write: f_write.write(code_to_start)
                        print(f"Code written to '{target_f_start}'.")
                        start_code_in_background(target_f_start)
                    except Exception as e: print(f"!Error writing to '{target_f_start}': {e}")
                elif os.path.exists(target_f_start): start_code_in_background(target_f_start)
                else: print(f"!No code & target file '{target_f_start}' not found.")

                if current_code_buffer.strip():
                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False; LAST_CODE_FOR_CONFIRMATION = current_code_buffer
                    LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION

            elif command == "stop": stop_active_subprocess()
            elif command == "status_process": get_process_status()
            elif command == "img_desc":
                if not argument: print("!Path to image required."); continue
                if not M_MULTI_CAPABLE_MODEL: print("!Multimodal model not available."); continue
                try:
                    image_path = os.path.abspath(argument)
                    if not os.path.exists(image_path): print(f"!Image not found: '{image_path}'"); continue
                    pil_image = Image.open(image_path)
                    if pil_image.mode != 'RGB': pil_image = pil_image.convert('RGB')
                    print("Generating image description..."); description = gmc_multimodal(pil_image)
                    if description.startswith("#LLM_ERR"): print(f"Error: {description}")
                    else: print(f"\n--- Image Description ---\n{description}\n------------------------")
                except Exception as e: print(f"!Error processing image: {e}")

            elif command == "show":
                print(f"CODE ({len(current_code_buffer)} B):\n{'-'*30}\n{current_code_buffer}\n{'-'*30}" if current_code_buffer.strip() else "!Code buffer empty.")
                print(f"Target File: {CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else 'In-Memory/Auto'}")
                if LAST_SUCCESSFUL_TASK_DESCRIPTION: print(f"Last OK Task: {LAST_SUCCESSFUL_TASK_DESCRIPTION}")
                if CURRENT_PLAN_TEXT:
                    print("\n--- Active Plan ---")
                    for i, step_show in enumerate(CURRENT_PLAN_STEPS):
                        status_char = "❌" if PLAN_STEP_FAILED_INFO and PLAN_STEP_FAILED_INFO['index'] == i else ("✅" if i < PLAN_STEP_INDEX else ("⏳" if i == PLAN_STEP_INDEX and PLAN_CONFIRMED else "📋"))
                        modified_marker = " (modified)" if 'original_task_if_modified' in step_show else ""
                        print(f"{status_char} {i+1}. {step_show.get('task','N/A')}{modified_marker}")
                        if i == PLAN_STEP_INDEX and PLAN_CONFIRMED and not PLAN_STEP_FAILED_INFO: print("    (Next)")
                        elif PLAN_STEP_FAILED_INFO and PLAN_STEP_FAILED_INFO['index'] == i: print("    (Failed - awaiting action)")
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and PLAN_CONFIRMED and not PLAN_STEP_FAILED_INFO: print("🎉 Plan Completed!")
                    elif not PLAN_CONFIRMED and CURRENT_PLAN_STEPS and not PLAN_STEP_FAILED_INFO: print("🕒 Plan Awaiting Confirmation.")

            elif command == "clear":
                current_code_buffer = ""; LAST_USER_INSTRUCTION = "print('Hello from POOP!')"; LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                CURRENT_TARGET_FILE = None; CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False; LAST_CODE_FOR_CONFIRMATION = ""
                CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                print("Buffer, history, plan cleared. Target file reset."); update_cmds_display()

            elif command in ["file", "f"]:
                if argument.lower() == "none" or argument.lower() == "--clear":
                    if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE) and CURRENT_TARGET_FILE.startswith("poop"):
                        del_q = input(f"Delete temp file '{CURRENT_TARGET_FILE}'? (y/N): ").lower()
                        if del_q == 'y':
                            try: os.remove(CURRENT_TARGET_FILE); print(f"'{CURRENT_TARGET_FILE}' deleted.")
                            except Exception as e: print(f"!Error deleting '{CURRENT_TARGET_FILE}': {e}")
                    CURRENT_TARGET_FILE = None; print("Target: In-Memory/Auto per plan."); LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                elif argument:
                    new_target_file = os.path.abspath(argument); CURRENT_TARGET_FILE = new_target_file
                    print(f"Target file: '{CURRENT_TARGET_FILE}'.")
                    if os.path.exists(CURRENT_TARGET_FILE):
                        try:
                            with open(CURRENT_TARGET_FILE, 'r', encoding='utf-8') as f_read: current_code_buffer = f_read.read()
                            print(f"Loaded '{CURRENT_TARGET_FILE}' ({len(current_code_buffer)} B).")
                            LAST_USER_INSTRUCTION = f"# Code loaded: {CURRENT_TARGET_FILE}"
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Loaded from file '{CURRENT_TARGET_FILE}'"
                        except Exception as e: print(f"!Error loading: {e}"); current_code_buffer = ""; LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                    else: print(f"File '{CURRENT_TARGET_FILE}' will be created."); current_code_buffer = ""; LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                else: print(f"Current Target: {CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else 'In-Memory/Auto'}")
                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False; LAST_CODE_FOR_CONFIRMATION = current_code_buffer; update_cmds_display()

            elif command == "#poop_continue_plan" or (not (CURRENT_PLAN_TEXT or PLAN_STEP_FAILED_INFO)):
                if command != "#poop_continue_plan":
                    LAST_USER_INSTRUCTION = user_input_raw
                    CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0; PLAN_STEP_FAILED_INFO = None
                    current_code_buffer = "" # Reset buffer for a new top-level instruction

                if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO:
                    current_step_details = CURRENT_PLAN_STEPS[PLAN_STEP_INDEX]
                    step_task = current_step_details.get('task', f"Step {PLAN_STEP_INDEX + 1}")
                    is_additive_step = current_step_details.get("additive_code", False)
                    print(f"\n🤖 Plan Step {PLAN_STEP_INDEX + 1}/{len(CURRENT_PLAN_STEPS)}: {step_task} {'(Additive)' if is_additive_step else ''}")

                    if current_step_details.get("requires_code_gen", True):
                        instruction_for_gmc = f"Implement: {step_task}."
                        if current_step_details.get('details'): instruction_for_gmc += f" Details: {current_step_details['details']}."
                        
                        code_base_for_gmc = current_code_buffer if is_additive_step else ""
                        # For non-additive, ensure target file and buffer are fresh unless it's the very first step of a plan with a user-set file.
                        if not is_additive_step:
                            # If a user explicitly set a file with 'f' and this is the first code-gen step,
                            # we might want to use it. But for general plan execution, non-additive implies new file.
                            # Let's simplify: non-additive steps in a plan always get a new file and clear buffer.
                            if PLAN_STEP_INDEX > 0 or not CURRENT_TARGET_FILE: # If not first step or no file set.
                                CURRENT_TARGET_FILE = generate_unique_poop_filename()
                                print(f"POOP: Non-additive step. Using new target file: '{CURRENT_TARGET_FILE}'")
                            current_code_buffer = "" # Clear main buffer for non-additive step's code generation
                        elif is_additive_step and not CURRENT_TARGET_FILE:
                            # This is the first code-generating step of an additive sequence
                            CURRENT_TARGET_FILE = generate_unique_poop_filename()
                            print(f"POOP: First additive step. Using new target file: '{CURRENT_TARGET_FILE}'")
                            # current_code_buffer might be empty or from 'f' command.

                        print("POOP: Generating code for this step...")
                        gmc_plan_context = {
                            "full_plan": CURRENT_PLAN_TEXT, "current_step_description": step_task,
                            "current_step_details": current_step_details.get('details', 'N/A'),
                            "requires_user_input_during_step": current_step_details.get('requires_user_input_during_step'),
                            "screenshot_analysis_signal": current_step_details.get('screenshot_analysis_signal', False),
                            "overall_goal": LAST_USER_INSTRUCTION,
                            "is_additive": is_additive_step
                        }
                        generated_code_for_step = gmc(code_base_for_gmc, instruction_for_gmc,
                            previous_task_context_for_code_gen=LAST_SUCCESSFUL_TASK_DESCRIPTION,
                            system_info_for_code_gen=current_system_info, plan_context_for_code_gen=gmc_plan_context)

                        if generated_code_for_step.startswith("#LLM_ERR"):
                            PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"Code gen failed: {generated_code_for_step}", 'step_task': step_task, 'code_at_failure': code_base_for_gmc}
                        elif not generated_code_for_step.strip():
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Step ack (no code gen): {step_task}"; PLAN_STEP_INDEX += 1
                        else:
                            step_comment_info = {'num': PLAN_STEP_INDEX + 1, 'total': len(CURRENT_PLAN_STEPS)}
                            if is_additive_step:
                                separator = "\n\n" if current_code_buffer.strip() else ""
                                new_code_part_with_comment = add_comment_to_code(generated_code_for_step, f"Additive part for: {step_task}", True, step_comment_info, LAST_USER_INSTRUCTION)
                                current_code_buffer += separator + new_code_part_with_comment
                            else:
                                current_code_buffer = add_comment_to_code(generated_code_for_step, step_task, True, step_comment_info, LAST_USER_INSTRUCTION)
                            CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True; LAST_CODE_FOR_CONFIRMATION = ""

                            if not CURRENT_TARGET_FILE: # Should be set by now
                                CURRENT_TARGET_FILE = generate_unique_poop_filename()
                                print(f"!POOP: Target file unexpectedly not set. Using new: {CURRENT_TARGET_FILE}")
                            update_cmds_display() # Update if target file name changed

                            if CURRENT_TARGET_FILE:
                                try:
                                    with open(CURRENT_TARGET_FILE, "w", encoding='utf-8') as f_w: f_w.write(current_code_buffer)
                                    # print(f"Code {'appended to' if is_additive_step and code_base_for_gmc else 'saved to'} '{CURRENT_TARGET_FILE}'.")
                                except Exception as e: print(f"!Error saving to '{CURRENT_TARGET_FILE}': {e}")

                            executed_code_buffer, fixed_by_llm_after_exec, successful_exec, script_stdout_lines, exec_error_msg = execute_code(
                                current_code_buffer, instruction_for_gmc, LAST_SUCCESSFUL_TASK_DESCRIPTION,
                                file_path=CURRENT_TARGET_FILE, auto_run_source=f"POOP (Plan Step {PLAN_STEP_INDEX + 1}): ")

                            if fixed_by_llm_after_exec and executed_code_buffer != current_code_buffer:
                                current_code_buffer = executed_code_buffer
                                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True; LAST_CODE_FOR_CONFIRMATION = ""

                            if exec_error_msg and exec_error_msg.startswith(MODULE_INSTALL_SIGNAL):
                                print(f"POOP: Module '{exec_error_msg.split(':')[1]}' installed. Retrying step.")
                                # Do not advance PLAN_STEP_INDEX, it will retry current step.
                                # PLAN_STEP_FAILED_INFO is not set.
                            elif successful_exec:
                                LAST_SUCCESSFUL_TASK_DESCRIPTION = f"OK Step: {step_task} (Goal: {LAST_USER_INSTRUCTION})"; PLAN_STEP_INDEX += 1
                                handle_image_analysis_signal(script_stdout_lines)
                            else:
                                PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"Exec failed. Error: {exec_error_msg or 'Unknown'}", 'step_task': step_task, 'code_at_failure': current_code_buffer}
                    else: # No code gen for this step
                        action_completed = False; action_desc = current_step_details.get('requires_user_action', '')
                        if action_desc:
                            print(f"ACTION REQUIRED: {action_desc}")
                            if "POOP will use its AI to describe the image at" in action_desc:
                                img_path_match = re.search(r"image at (.*?)(?:\.|$|,|\s)", action_desc)
                                img_path_from_action = img_path_match.group(1).strip() if img_path_match else None
                                dependencies_text = current_step_details.get('dependencies', '')
                                path_from_deps_match = re.search(r"(?:path to|image at|file)\s*['\"]?([/\w\.\-:\\]+(?:png|jpg|jpeg|bmp|gif))['\"]?", dependencies_text, re.IGNORECASE)
                                if path_from_deps_match: img_path_from_action = path_from_deps_match.group(1).strip()
                                if img_path_from_action:
                                    if handle_image_analysis_signal([], img_path_from_action): action_completed = True
                                    else: PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"AI image analysis failed for: {img_path_from_action}", 'step_task': step_task}
                                else:
                                    print("POOP: Could not determine image path for AI analysis from plan.")
                                    user_confirms_act = input("POOP: Action complete (or info provided)? (y/N): ").strip().lower()
                                    if user_confirms_act == 'y': action_completed = True
                            else:
                                user_confirms_act = input("POOP: Manual step complete? (y/N): ").strip().lower()
                                if user_confirms_act == 'y': action_completed = True
                        else: action_completed = True
                        if action_completed: LAST_SUCCESSFUL_TASK_DESCRIPTION = f"OK Non-code Step: {step_task}"; PLAN_STEP_INDEX += 1
                        elif not PLAN_STEP_FAILED_INFO: print("Plan paused. Complete action.")

                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and not PLAN_STEP_FAILED_INFO:
                        print("\n🤖 POOP: Plan Succeeded!"); CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0

                elif not CURRENT_PLAN_TEXT and command != "#poop_continue_plan" and not PLAN_STEP_FAILED_INFO:
                    print(f"🤖 POOP: Instruction: '{LAST_USER_INSTRUCTION}'. Generating plan...")
                    plan_text_output = gmp(LAST_USER_INSTRUCTION, current_system_info, PAST_POOP_FILES_CONTEXT)
                    if plan_text_output.startswith("#LLM_ERR"): print(plan_text_output)
                    elif not plan_text_output.strip(): print("LLM returned empty plan.")
                    else:
                        CURRENT_PLAN_TEXT = plan_text_output; CURRENT_PLAN_STEPS = parse_plan(CURRENT_PLAN_TEXT)
                        if not CURRENT_PLAN_STEPS: print(f"Could not parse plan:\n{CURRENT_PLAN_TEXT}"); CURRENT_PLAN_TEXT = ""
                        else:
                            print("\n--- POOP Proposed Plan ---")
                            for i, step_disp in enumerate(CURRENT_PLAN_STEPS): print(f"{i+1}. {step_disp.get('task','N/A')}")
                            print("--------------------------")
                            confirm_plan_input = input("Proceed? (y/N/edit): ").strip().lower()
                            if confirm_plan_input == 'y':
                                PLAN_CONFIRMED = True; PLAN_STEP_INDEX = 0; CURRENT_TARGET_FILE = None; current_code_buffer = ""
                                LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Plan confirmed for: {LAST_USER_INSTRUCTION}"
                            elif confirm_plan_input == 'edit': print("Edit not implemented. Refine instruction or reject."); CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []
                            else: print("Plan rejected."); CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []

                elif command == "#poop_continue_plan" and (not PLAN_CONFIRMED or PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS)) and not PLAN_STEP_FAILED_INFO:
                    if PLAN_STEP_INDEX >= len(CURRENT_PLAN_STEPS) and CURRENT_PLAN_STEPS:
                         print("🤖 POOP: Plan finished. New instruction?"); CURRENT_PLAN_TEXT = ""; CURRENT_PLAN_STEPS = []; PLAN_CONFIRMED = False; PLAN_STEP_INDEX = 0

        except KeyboardInterrupt:
            print(f"\n{random.choice(COLORS)}POOP> {RESET_COLOR}Input cancelled. Use 'q' to exit.")
            if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS) :
                PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': "User Interruption", 'step_task': CURRENT_PLAN_STEPS[PLAN_STEP_INDEX].get('task', 'N/A')}
        except Exception as e:
            print(f"\n!UNEXPECTED POOP LOOP ERROR: {e}"); traceback.print_exc()
            if PLAN_CONFIRMED and CURRENT_PLAN_STEPS and PLAN_STEP_INDEX < len(CURRENT_PLAN_STEPS):
                PLAN_STEP_FAILED_INFO = {'index': PLAN_STEP_INDEX, 'reason': f"Unexpected POOP Loop Error: {e}", 'step_task': CURRENT_PLAN_STEPS[PLAN_STEP_INDEX].get('task', 'N/A')}
