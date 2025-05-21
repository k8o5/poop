import google.generativeai as genai
import os
import traceback
import subprocess
import sys
import shutil
import time
import platform 
import random   
from PIL import Image

GAK = os.environ.get("GOOGLE_API_KEY")
M_CURRENT_TEXT_MODEL = None
M_MULTI_CAPABLE_MODEL = None
M_LIGHT_MODEL = None
GCFG = genai.types.GenerationConfig(temperature=0.3)
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

COLORS = [
    "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[34m", "\x1b[35m", "\x1b[36m",
    "\x1b[91m", "\x1b[92m", "\x1b[93m", "\x1b[94m", "\x1b[95m", "\x1b[96m",
]
RESET_COLOR = "\x1b[0m"
BRIGHT_WHITE_COLOR = "\x1b[97m"

IMAGE_ANALYSIS_SIGNAL = "#POOP_ANALYZE_IMAGE_PATH:"

_CMDS_TEMPLATE = f"""CMDS for POOP ({POOP_NAME}):
h(elp): Show this help.
q(uit)/exit: Exit the agent.
run: If new/modified Python code exists, show for confirmation, then execute it
     (blocking, live output) and attempt to debug errors. Updates last successful task.
     If script signals for image analysis, POOP will attempt it.
start [path]: Start Python code in the target file in the background (live output).
              No confirmation before start; assumes code is tested.
              If no path given, uses the current target file. If none, a new unique file is created.
stop: Stop the last background process started with 'start'.
status_process: Check the status of the background process.
show: Display the current Python code buffer.
clear: Clear the Python code buffer and task history. Resets confirmation status and target file.
m(odel) [name]: Change the default LLM. Available: '{{multi_model_name}}', '{{light_model_name}}'.
img_desc [path]: Describe an image using POOP's multimodal AI.
f(ile) [path]: Set the Python target file. 'f none' for in-memory.
               Loads code if file exists, resets confirmation and task history.
sysinfo: Display detected system information.
[any other text]: Generate/Modify Python code based on the instruction.
                  If the instruction implies taking a screenshot AND describing it,
                  the generated script should print '{IMAGE_ANALYSIS_SIGNAL} <filepath>'
                  to stdout upon successful screenshot creation for POOP to analyze.
                  Code is NOT automatically executed. Use 'run' to confirm and execute.
                  If no target file is set, a new unique 'poop<timestamp>.py' will be used.
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
            with open("/etc/os-release") as f:
                for line_content in f:
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

def update_cmds_display():
    global CMDS
    default_file_display = CURRENT_TARGET_FILE if CURRENT_TARGET_FILE else "new unique file on generation"
    multi_name = M_MULTI_CAPABLE_MODEL.model_name if M_MULTI_CAPABLE_MODEL else 'N/A'
    light_name = M_LIGHT_MODEL.model_name if M_LIGHT_MODEL else 'N/A'
    CMDS = _CMDS_TEMPLATE.format(
        current_default_file=default_file_display,
        multi_model_name=multi_name,
        light_model_name=light_name,
        IMAGE_ANALYSIS_SIGNAL=IMAGE_ANALYSIS_SIGNAL 
    )

def init_llm(model_name_primary='gemini-2.5-flash-preview-05-20', model_name_secondary='gemini-2.0-flash,'):
    global GAK, M_CURRENT_TEXT_MODEL, M_MULTI_CAPABLE_MODEL, M_LIGHT_MODEL
    if not GAK: return False
    try:
        genai.configure(api_key=GAK)
        try: 
            M_MULTI_CAPABLE_MODEL = genai.GenerativeModel(model_name_primary)
            print(f"Primary LLM ({model_name_primary}): Initialized.")
        except Exception as e: print(f"!Init {model_name_primary} (Primary) FAILED: {e}"); M_MULTI_CAPABLE_MODEL = None
        if model_name_primary != model_name_secondary:
            try: 
                M_LIGHT_MODEL = genai.GenerativeModel(model_name_secondary)
                print(f"Secondary LLM ({model_name_secondary}): Initialized.")
            except Exception as e: print(f"!Init {model_name_secondary} (Secondary) FAILED: {e}"); M_LIGHT_MODEL = None
        elif M_MULTI_CAPABLE_MODEL : M_LIGHT_MODEL = M_MULTI_CAPABLE_MODEL; print(f"Secondary LLM is same as Primary ({model_name_secondary}).")

        if M_MULTI_CAPABLE_MODEL: M_CURRENT_TEXT_MODEL = M_MULTI_CAPABLE_MODEL
        elif M_LIGHT_MODEL: M_CURRENT_TEXT_MODEL = M_LIGHT_MODEL; print("!Warning: Primary model failed, using secondary model as current text model.")
        
        if M_CURRENT_TEXT_MODEL: print(f"Current text model set to: {M_CURRENT_TEXT_MODEL.model_name}")
        else: print("!No LLM could be initialized as current text model."); update_cmds_display(); return False
        update_cmds_display(); return True
    except Exception as e:
        print(f"!General LLM Init FAILED: {e}")
        M_CURRENT_TEXT_MODEL = M_MULTI_CAPABLE_MODEL = M_LIGHT_MODEL = None
        update_cmds_display(); return False

def gmc(current_code="", user_instruction=LAST_USER_INSTRUCTION, error_feedback=None, previous_task_context="", system_info=None):
    global CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN
    if not M_CURRENT_TEXT_MODEL: return "#LLM_ERR: Current text model not initialized."
    prompt_parts = [
        "You are a Python expert. Your task is to create, modify, or debug Python scripts step-by-step.",
        "The scripts can perform any task, including file system operations, external processes, network requests, etc.",
        "Use standard libraries. Add necessary imports. Return ONLY raw Python code. No markdown or explanations outside code.",
        f"If a task involves taking a screenshot AND then describing/analyzing its content, the script should, after successfully saving the screenshot, print a special line to standard output: '{IMAGE_ANALYSIS_SIGNAL} /path/to/the/saved/screenshot.png'. Replace '/path/to/the/saved/screenshot.png' with the actual absolute path of the saved image file. POOP will detect this signal and perform the AI image analysis."
    ]
    if system_info:
        prompt_parts.append("\n--- TARGET SYSTEM INFORMATION ---")
        for key, value in system_info.items(): prompt_parts.append(f"{key.replace('_', ' ').title()}: {value}")
        prompt_parts.append("---------------------------------")
        prompt_parts.append("Adapt your Python script (especially for OS commands, package management, or file paths) to this target system.")
    if error_feedback:
        prompt_parts.append("\nTASK: Fix the Python code based on the error.")
        if previous_task_context: prompt_parts.append(f"The overall goal of the script (related to previous step) was: {previous_task_context}")
        prompt_parts.append(f"The specific instruction that led to the error was: {user_instruction}")
        prompt_parts.append(f"FAULTY PYTHON CODE:\n```python\n{current_code}\n```")
        prompt_parts.append(f"ERROR MESSAGE:\n```\n{error_feedback}\n```")
        prompt_parts.append("FIXED PYTHON CODE (code only):")
    elif current_code:
        prompt_parts.append("\nTASK: Modify or add to the existing Python script.")
        if previous_task_context:
            prompt_parts.append(f"The script so far (from previous successful steps) has achieved: {previous_task_context}")
            prompt_parts.append("Consider this context when fulfilling the new instruction.")
        prompt_parts.append(f"CURRENT SCRIPT:\n```python\n{current_code}\n```")
        prompt_parts.append(f"NEW INSTRUCTION: {user_instruction}")
        prompt_parts.append("MODIFIED OR EXTENDED PYTHON SCRIPT (code only):")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True
    else: 
        prompt_parts.append("\nTASK: Create a new Python script.")
        if previous_task_context: prompt_parts.append(f"This new script might be related to a previous broader goal: {previous_task_context}")
        prompt_parts.append(f"INSTRUCTION FOR THE NEW SCRIPT: {user_instruction}")
        prompt_parts.append("PYTHON SCRIPT (code only):")
        CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = True
    full_prompt = "\n".join(prompt_parts)
    try:
        response = M_CURRENT_TEXT_MODEL.generate_content(full_prompt, generation_config=GCFG)
        output = response.text.strip()
        if output.startswith("```python"): output = output[9:]
        elif output.startswith("```"): output = output[3:]
        if output.endswith("```"): output = output[:-3]
        return output.strip()
    except Exception as e: return f"#LLM_ERR: Error during Python code generation: {e}"

def gmc_multimodal(image_data, text_prompt="Describe this image in detail."):
    active_multimodal_model = M_MULTI_CAPABLE_MODEL if M_MULTI_CAPABLE_MODEL else M_CURRENT_TEXT_MODEL
    if not active_multimodal_model: return "#LLM_ERR: No suitable multimodal model initialized."
    content = [text_prompt, image_data]
    try:
        response = active_multimodal_model.generate_content(content, generation_config=GCFG)
        return response.text.strip()
    except Exception as e: return f"#LLM_ERR: Error during multimodal generation with {active_multimodal_model.model_name if active_multimodal_model else 'N/A'}: {e}"

def create_execution_scope():
    s = {"__builtins__": __builtins__}
    libs = [('os', 'os'), ('sys', 'sys'), ('subprocess', 'sp'), ('shutil', 'sh'), ('platform', 'platform'),
            ('requests', 'req'), ('json', 'json'), ('time', 'time'), ('random', 'random'), ('datetime', 'datetime'),
            ('pandas', 'pd'), ('numpy', 'np'), ('matplotlib.pyplot', 'plt')]
    for lib_name, alias in libs:
        try: exec(f"import {lib_name} as {alias}", s)
        except ImportError: pass
    return s

def execute_code(code_buffer, last_instruction_for_fix, previous_task_context_for_fix, file_path=None, auto_run_source=""):
    if not code_buffer or not code_buffer.strip():
        print("!No Python code to execute (empty or whitespace only)."); return code_buffer, False, False, []
    
    print(f"{auto_run_source}Executing Python code ({'File: ' + file_path if file_path else 'In-Memory'})...")
    fixed_this_run = False
    execution_successful = False
    error_output_for_llm = None
    current_system_info_for_fix = get_system_info()
    stdout_lines_capture = [] 

    if file_path:
        try:
            with open(file_path, "w", encoding='utf-8') as f: f.write(code_buffer)
            child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [sys.executable, file_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                bufsize=1, encoding='utf-8', env=child_env
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
                error_output_for_llm = "\n".join(stderr_capture_list)
                print(f"!Python process finished with error code {return_code}.")
                print("Attempting to fix...")
                fixed_code = gmc(code_buffer, last_instruction_for_fix, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix)
                if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
                elif fixed_code == code_buffer: print("LLM: No change (error not fixed).")
                else: print("Fixed."); code_buffer = fixed_code; fixed_this_run = True
            else: print("Python execution OK."); execution_successful = True
        except FileNotFoundError: print(f"!ERROR: Python interpreter '{sys.executable}' not found.")
        except Exception as e:
            print(f"!FILE EXECUTION ERROR (Python): {e}")
            error_output_for_llm = f"File system/Subprocess error: {e}\n{traceback.format_exc()}"
            print("Attempting to fix...")
            fixed_code = gmc(code_buffer, last_instruction_for_fix, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix)
            if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
            elif fixed_code == code_buffer: print("LLM: No change.")
            else: print("Fixed."); code_buffer = fixed_code; fixed_this_run = True
    else: 
        original_stdout = sys.stdout
        from io import StringIO
        captured_output = StringIO()
        sys.stdout = captured_output # Redirect stdout

        execution_scope, compiled_object, compile_error_msg = create_execution_scope(), None, None
        try: compiled_object = compile(code_buffer, '<in_memory_code>', 'exec')
        except SyntaxError as se:
            compile_error_msg = f"SYNTAX ERROR Line {se.lineno}: {se.msg} `{(se.text or '').strip()}`\n{traceback.format_exc(limit=0)}"
        
        if compile_error_msg:
            sys.stdout = original_stdout # Restore stdout
            print(f"COMPILE ERROR (Python): {compile_error_msg.splitlines()[0]}"); print("Attempting to fix...")
            error_output_for_llm = compile_error_msg
            fixed_code = gmc(code_buffer, last_instruction_for_fix, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix)
            if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
            elif fixed_code == code_buffer: print("LLM: No change.")
            else: print("Fixed."); code_buffer = fixed_code; fixed_this_run = True
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
                sys.stdout = original_stdout # Restore stdout before printing error
                tb_lines = traceback.format_exc().splitlines()
                specific_error_line = f"RUNTIME ERROR (Python): {type(e).__name__}: {e}"
                for tbl_line in reversed(tb_lines):
                    if '<in_memory_code>' in tbl_line:
                        specific_error_line = f"RUNTIME ERROR (Python): {type(e).__name__}: {e} (Near: {tbl_line.strip()})"; break
                error_output_for_llm = f"{type(e).__name__}: {e}\n" + "\n".join(tb_lines)
                print(f"\n{specific_error_line}"); print("Attempting to fix...") # Prints to original_stdout
                fixed_code = gmc(code_buffer, last_instruction_for_fix, error_output_for_llm, previous_task_context_for_fix, current_system_info_for_fix)
                if fixed_code.startswith("#LLM_ERR"): print(fixed_code)
                elif fixed_code == code_buffer: print("LLM: No change.")
                else: print("Fixed."); code_buffer = fixed_code; fixed_this_run = True
            finally:
                sys.stdout = original_stdout # Ensure stdout is always restored
                output_str = captured_output.getvalue()
                original_stdout.write(output_str) # Print captured output to actual console
                stdout_lines_capture.extend(output_str.splitlines())
                print_to_original_stdout("--- Live Python Output End (In-Memory) ---", flush=True)
        captured_output.close()
    return code_buffer, fixed_this_run, execution_successful, stdout_lines_capture


def start_code_in_background(file_path):
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if not file_path : print("!No Python file path provided to start."); return
    if not os.path.exists(file_path): print(f"!Python file to start not found: '{file_path}'"); return
    if ACTIVE_SUBPROCESS and ACTIVE_SUBPROCESS.poll() is None: print(f"!Process ({ACTIVE_SUBPROCESS_FILE}) already running. Use 'stop' first."); return
    print(f"Starting Python script '{file_path}' in background...")
    try:
        child_env = os.environ.copy(); child_env["PYTHONUNBUFFERED"] = "1"
        ACTIVE_SUBPROCESS = subprocess.Popen(
            [sys.executable, file_path], stdout=sys.stdout, stderr=sys.stderr,
            text=True, encoding='utf-8', env=child_env
        )
        ACTIVE_SUBPROCESS_FILE = file_path
        print(f"'{file_path}' running (PID: {ACTIVE_SUBPROCESS.pid}). Use 'stop' to terminate.")
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
        else: print(f"Background process '{ACTIVE_SUBPROCESS_FILE}' was already stopped (Exit: {ACTIVE_SUBPROCESS.returncode}).")
        ACTIVE_SUBPROCESS = None; ACTIVE_SUBPROCESS_FILE = None
    else: print("No active background process to stop.")

def get_process_status():
    global ACTIVE_SUBPROCESS, ACTIVE_SUBPROCESS_FILE
    if ACTIVE_SUBPROCESS:
        poll_result = ACTIVE_SUBPROCESS.poll()
        if poll_result is None: print(f"Process '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid}) is running.")
        else: print(f"Process '{ACTIVE_SUBPROCESS_FILE}' (PID: {ACTIVE_SUBPROCESS.pid}) has stopped (Exit Code: {poll_result}).")
    else: print("No background process was started or it has been cleared.")

if __name__ == "__main__":
    try: from PIL import Image
    except ImportError: print("!Pillow library is missing. Please install with `pip install Pillow`"); sys.exit(1)

    if not GAK:
        print("🔑 GOOGLE_API_KEY is missing.")
        print(f"   Get it here: {API_KEY_LINK}")
        GAK = input("   Paste your GOOGLE_API_KEY: ").strip()
        if not GAK: print("🔴 No API key provided. Exiting."); sys.exit(1)
        else: print("✅ API key OK.")
    else:
        print("✅ API key found in environment.")

    if not init_llm(): sys.exit(1)

    print(f"\nWelcome to POOP ({POOP_NAME})")
    print_poop_ascii_art()
    print(f"Type 'h' or 'help' for a list of commands.")
    print("----------------------------------------------------")

    current_code_buffer = ""
    
    while True: 
        try:
            prompt_color = random.choice(COLORS)
            user_input_raw = input(f"{prompt_color}POOP> {RESET_COLOR}").strip()
            if not user_input_raw: continue

            parts = user_input_raw.lower().split(maxsplit=1)
            command, argument = parts[0], parts[1] if len(parts) > 1 else ""
            
            current_system_info = get_system_info()

            if command in ['exit', 'quit', 'q']:
                stop_active_subprocess() 
                if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE):
                    del_q = input(f"Python target file '{CURRENT_TARGET_FILE}' exists. Delete? (y/N): ").lower()
                    if del_q == 'y': 
                        try: os.remove(CURRENT_TARGET_FILE); print(f"'{CURRENT_TARGET_FILE}' deleted.")
                        except Exception as e: print(f"!Error deleting file '{CURRENT_TARGET_FILE}': {e}")
                print(f"\n{FAREWELL}\n"); break
            elif command in ['help', 'h']: update_cmds_display(); print(CMDS)
            elif command == "sysinfo":
                print("--- Current System Information ---")
                for k, v_sys in current_system_info.items(): print(f"{k.replace('_',' ').title()}: {v_sys}")
                print("--------------------------------")
            elif command in ['model', 'm']:
                if argument:
                    target_model_obj = None
                    if M_MULTI_CAPABLE_MODEL and argument == M_MULTI_CAPABLE_MODEL.model_name: target_model_obj = M_MULTI_CAPABLE_MODEL
                    elif M_LIGHT_MODEL and argument == M_LIGHT_MODEL.model_name: target_model_obj = M_LIGHT_MODEL
                    elif argument == "primary" and M_MULTI_CAPABLE_MODEL: target_model_obj = M_MULTI_CAPABLE_MODEL
                    elif argument == "light" and M_LIGHT_MODEL: target_model_obj = M_LIGHT_MODEL
                    if target_model_obj: M_CURRENT_TEXT_MODEL = target_model_obj; print(f"Model set to: '{M_CURRENT_TEXT_MODEL.model_name}'.")
                    else:
                        print(f"!Model '{argument}' unknown, unavailable, or alias incorrect.")
                        print(f"  Available by name: ")
                        if M_MULTI_CAPABLE_MODEL: print(f"    '{M_MULTI_CAPABLE_MODEL.model_name}' (primary alias: 'primary')")
                        if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"    '{M_LIGHT_MODEL.model_name}' (secondary alias: 'light')")
                        elif M_LIGHT_MODEL == M_MULTI_CAPABLE_MODEL : print(f"    (Secondary model is same as primary)")
                else:
                    print(f"Current text model: {M_CURRENT_TEXT_MODEL.model_name if M_CURRENT_TEXT_MODEL else 'N/A'}")
                    if M_MULTI_CAPABLE_MODEL: print(f"Primary (multimodal capable) model: {M_MULTI_CAPABLE_MODEL.model_name}")
                    if M_LIGHT_MODEL and M_LIGHT_MODEL != M_MULTI_CAPABLE_MODEL: print(f"Secondary (light) model: {M_LIGHT_MODEL.model_name}")

            elif command == "run":
                if not current_code_buffer.strip():
                    print("!No code in buffer to run.")
                    continue
                confirmed_to_run = False
                if CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN or current_code_buffer != LAST_CODE_FOR_CONFIRMATION:
                    print("\n--- The following Python code was generated/modified ---")
                    display_code = current_code_buffer
                    if len(display_code) > 2000: display_code = display_code[:1000] + "\n...\n(Code too long to display fully)\n...\n" + display_code[-500:]
                    print(f"{display_code}")
                    print("-------------------------------------------------------")
                    confirm = input("Execute this code? (y/N): ").strip().lower()
                    if confirm == 'y':
                        confirmed_to_run = True
                        LAST_CODE_FOR_CONFIRMATION = current_code_buffer 
                    else: print("Execution cancelled. Code remains in buffer.")
                else: confirmed_to_run = True

                if confirmed_to_run:
                    target_file_for_run = CURRENT_TARGET_FILE
                    if not target_file_for_run and current_code_buffer.strip():
                        target_file_for_run = generate_unique_poop_filename()
                        print(f"No target file set for run. Using new file: '{target_file_for_run}'")
                        CURRENT_TARGET_FILE = target_file_for_run
                        update_cmds_display()
                    
                    current_code_buffer, fixed, successful, script_stdout_lines = execute_code(
                        current_code_buffer, LAST_USER_INSTRUCTION, LAST_SUCCESSFUL_TASK_DESCRIPTION,
                        file_path=target_file_for_run
                    )
                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = fixed 
                    if fixed: LAST_CODE_FOR_CONFIRMATION = "" 
                    
                    if successful and not fixed: LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION
                    elif not successful : LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                    
                    if successful:
                        for line in script_stdout_lines:
                            if line.startswith(IMAGE_ANALYSIS_SIGNAL):
                                image_path_to_analyze = line.replace(IMAGE_ANALYSIS_SIGNAL, "").strip()
                                print(f"\nPOOP: Script signaled to analyze image: '{image_path_to_analyze}'")
                                if os.path.exists(image_path_to_analyze):
                                    try:
                                        pil_img = Image.open(image_path_to_analyze)
                                        if pil_img.mode != 'RGB': pil_img = pil_img.convert('RGB')
                                        print("POOP: Requesting description from multimodal AI...")
                                        description = gmc_multimodal(pil_img)
                                        pil_img.close()
                                        if description.startswith("#LLM_ERR"): print(f"POOP: AI Error: {description}")
                                        else: print(f"POOP AI Description of '{os.path.basename(image_path_to_analyze)}':\n---\n{description}\n---")
                                    except FileNotFoundError: print(f"POOP: Error - Image file not found at path from signal: '{image_path_to_analyze}'")
                                    except ImportError: print("POOP: Error - Pillow (PIL) library is missing. Cannot analyze image.")
                                    except Exception as e_img: print(f"POOP: Error analyzing image '{image_path_to_analyze}': {e_img}")
                                else: print(f"POOP: Error - Image path from signal does not exist: '{image_path_to_analyze}'")
                                break 
            elif command == "start":
                target_file_for_start = argument if argument else CURRENT_TARGET_FILE
                if not current_code_buffer.strip() and not (target_file_for_start and os.path.exists(target_file_for_start)):
                    print("!No code in buffer and no existing target file to start.")
                    continue
                if not target_file_for_start and current_code_buffer.strip():
                    target_file_for_start = generate_unique_poop_filename()
                    print(f"No target file for start. Using new file for current buffer: '{target_file_for_start}'")
                    CURRENT_TARGET_FILE = target_file_for_start
                    update_cmds_display()
                elif not target_file_for_start and not current_code_buffer.strip():
                    print("!Cannot start: No target file specified and code buffer is empty."); continue

                if current_code_buffer.strip(): 
                    try:
                        with open(target_file_for_start, "w", encoding='utf-8') as f: f.write(current_code_buffer)
                        print(f"Python code written to '{target_file_for_start}'.")
                        start_code_in_background(target_file_for_start)
                    except Exception as e: print(f"!Error writing Python file '{target_file_for_start}': {e}")
                elif os.path.exists(target_file_for_start): 
                    print(f"Buffer empty, starting existing file '{target_file_for_start}'...")
                    start_code_in_background(target_file_for_start)
                else: print(f"!No code in buffer and target file '{target_file_for_start}' not found.")
                if current_code_buffer.strip():
                    CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False 
                    LAST_CODE_FOR_CONFIRMATION = current_code_buffer
                    LAST_SUCCESSFUL_TASK_DESCRIPTION = LAST_USER_INSTRUCTION 

            elif command == "stop": stop_active_subprocess()
            elif command == "status_process": get_process_status()
            elif command == "img_desc":
                if not argument: print("!Path to image required."); continue
                if not M_MULTI_CAPABLE_MODEL: print("!Multimodal model (primary) not available for img_desc."); continue
                try:
                    image_path = os.path.abspath(argument)
                    if not os.path.exists(image_path): print(f"!Image not found: '{image_path}'"); continue
                    print(f"Loading: '{image_path}'..."); 
                    pil_image = Image.open(image_path)
                    if pil_image.mode != 'RGB': pil_image = pil_image.convert('RGB')
                    print("Generating image description..."); 
                    description = gmc_multimodal(pil_image)
                    if description.startswith("#LLM_ERR"): print(f"Error: {description}")
                    else: print(f"\n--- Image Description ---\n{description}\n------------------------")
                except Exception as e: print(f"!Error processing image: {e}")

            elif command == "show":
                print(f"PYTHON CODE ({len(current_code_buffer)} B):\n{'-'*30}\n{current_code_buffer}\n{'-'*30}" if current_code_buffer.strip() else "!Python code buffer is empty.")
                if CURRENT_TARGET_FILE: print(f"Python Target File: {CURRENT_TARGET_FILE}")
                else: print("Python Target: In-Memory / New unique file on next generation/run.")
                if LAST_SUCCESSFUL_TASK_DESCRIPTION: print(f"Last successful task context: {LAST_SUCCESSFUL_TASK_DESCRIPTION}")
            
            elif command == "clear":
                current_code_buffer = ""; LAST_USER_INSTRUCTION = "print('Hello from POOP!')"; LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                CURRENT_TARGET_FILE = None 
                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False
                LAST_CODE_FOR_CONFIRMATION = ""
                print("Python code buffer & task history cleared. Target file reset.")
                update_cmds_display()

            elif command in ["file", "f"]:
                if argument.lower() == "none" or argument.lower() == "--clear":
                    if CURRENT_TARGET_FILE and os.path.exists(CURRENT_TARGET_FILE):
                        del_q = input(f"File '{CURRENT_TARGET_FILE}' exists. Delete? (y/N): ").lower()
                        if del_q == 'y': 
                            try: os.remove(CURRENT_TARGET_FILE); print(f"'{CURRENT_TARGET_FILE}' deleted.")
                            except Exception as e: print(f"!Error deleting file '{CURRENT_TARGET_FILE}': {e}")
                    CURRENT_TARGET_FILE = None; print("Mode: In-Memory Python execution. Target file reset.")
                    LAST_SUCCESSFUL_TASK_DESCRIPTION = "" 
                elif argument:
                    new_target_file = os.path.abspath(argument)
                    CURRENT_TARGET_FILE = new_target_file
                    print(f"Python target file set to: '{CURRENT_TARGET_FILE}'.")
                    if os.path.exists(CURRENT_TARGET_FILE):
                        try:
                            with open(CURRENT_TARGET_FILE, 'r', encoding='utf-8') as f: current_code_buffer = f.read()
                            print(f"Content of '{CURRENT_TARGET_FILE}' ({len(current_code_buffer)} B) loaded into buffer.")
                            LAST_USER_INSTRUCTION = f"# Code loaded from {CURRENT_TARGET_FILE}"
                            LAST_SUCCESSFUL_TASK_DESCRIPTION = f"Code loaded from file '{CURRENT_TARGET_FILE}'"
                        except Exception as e: print(f"!Error loading file: {e}"); current_code_buffer = ""; LAST_SUCCESSFUL_TASK_DESCRIPTION = ""
                    else:
                        print(f"File '{CURRENT_TARGET_FILE}' does not exist. It will be created if code is generated/run.")
                        LAST_SUCCESSFUL_TASK_DESCRIPTION = "" 
                else: 
                    if CURRENT_TARGET_FILE: print(f"Current Python target file: '{CURRENT_TARGET_FILE}'")
                    else: print("Current Python Target: In-Memory / New unique file on next generation/run.")
                CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN = False 
                LAST_CODE_FOR_CONFIRMATION = current_code_buffer 
                update_cmds_display()
            
            else: 
                LAST_USER_INSTRUCTION = user_input_raw 
                
                if not CURRENT_TARGET_FILE and (not current_code_buffer.strip() or (current_code_buffer.strip() and not LAST_SUCCESSFUL_TASK_DESCRIPTION)):
                    new_file = generate_unique_poop_filename()
                    print(f"No active target file. Using new file: '{new_file}' for this task sequence.")
                    CURRENT_TARGET_FILE = new_file
                    update_cmds_display()
                
                current_op_desc = "Modifying Python code..." if current_code_buffer.strip() and LAST_SUCCESSFUL_TASK_DESCRIPTION else "Generating new Python code..."
                if LAST_SUCCESSFUL_TASK_DESCRIPTION and current_code_buffer.strip():
                     current_op_desc = f"Continuing task (last did: '{LAST_SUCCESSFUL_TASK_DESCRIPTION}'). Modifying code..."
                print(current_op_desc)
                
                generated_code = gmc(current_code_buffer, LAST_USER_INSTRUCTION, 
                                     previous_task_context=LAST_SUCCESSFUL_TASK_DESCRIPTION,
                                     system_info=current_system_info)

                if generated_code.startswith("#LLM_ERR"):
                    print(generated_code)
                elif not generated_code.strip() and current_code_buffer.strip():
                    print("LLM: Returned empty code. Previous code remains unchanged.")
                elif generated_code == current_code_buffer:
                    print("LLM: No change made to the code.")
                else:
                    current_code_buffer = generated_code
                    LAST_CODE_FOR_CONFIRMATION = "" 
                    print("Python code received/modified from LLM.")
                    if CURRENT_TARGET_FILE:
                        try:
                            with open(CURRENT_TARGET_FILE, "w", encoding='utf-8') as f: f.write(current_code_buffer)
                            print(f"Code saved to '{CURRENT_TARGET_FILE}'.")
                        except Exception as e: print(f"!Error saving code to '{CURRENT_TARGET_FILE}': {e}")
                    else: 
                        print("!Warning: Code generated but no target file is set (should have been auto-assigned).")
                    print("Use 'run' to confirm and execute it.")

        except KeyboardInterrupt: print(f"\n{random.choice(COLORS)}POOP> {RESET_COLOR}Input cancelled. Use 'q' to exit.")
        except Exception as e:
            print(f"\n!UNEXPECTED ERROR in main loop (the 'poop loop'!): {e}") 
            traceback.print_exc()
