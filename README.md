# POOP: Programmatic Operations Optimization Protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) 
[![Powered by Google Gemini](https://img.shields.io/badge/Powered%20by-Google%20Gemini-blue.svg)](https://ai.google.dev/models)

**Your AI-Powered Python Co-Pilot for Seamless Terminal Workflows**

---

## ✨ What is POOP?

POOP (Programmatic Operations Optimization Protocol) is an interactive command-line agent that leverages the power of large language models (LLMs) like Google Gemini to help you build, execute, and debug Python scripts for complex system tasks.

Instead of just generating a single code block, POOP works like an intelligent co-pilot, allowing you to iteratively build up solutions step-by-step, executing and debugging as you go. It bridges the gap between natural language instructions and executable code, right in your terminal.

Think of it as a conversational Python shell with AI super powers, designed to optimize your programmatic operations. *Essentia Ad Meliora* (Essential for Better Things).

## 🚀 Features

*   **AI-Driven Code Generation:** Translate natural language instructions into executable Python code using a connected LLM.
*   **Iterative Workflow:** Build complex scripts step-by-step, with the AI understanding the context of previous successful actions.
*   **Interactive Execution (`run`):** Execute the current code buffer with live output streaming and automatic LLM-powered debugging upon failure. **Requires user confirmation before running new/modified code.**
*   **Background Execution (`start`):** Launch scripts as detached background processes with output streaming to your terminal.
*   **Automatic Debugging:** When a script run fails, POOP automatically sends the error traceback and code back to the LLM to generate a fix, which is then presented for your review.
*   **File Management (`f`, unique names):** Easily load code from files, save the current buffer to a file, or let POOP manage unique filenames automatically for new tasks.
*   **Code Buffer Control (`show`, `clear`):** Inspect or clear the current Python code buffer and task history.
*   **Multimodal Capabilities (`img_desc`):** Use POOP's connected multimodal model to describe images.
*   **Automated Image Analysis Trigger:** Generated scripts can signal POOP (e.g., after taking a screenshot) to automatically load an image and request an AI description using a special print statement (`#POOP_ANALYZE_IMAGE_PATH:`).
*   **System Context Awareness:** POOP detects your operating system details and provides this information to the LLM to improve platform-specific code generation (e.g., package managers, file paths).
*   **Engaging Interface:** Randomly colored prompt and ASCII art welcome.

## 💡 Why Use POOP?

*   **Rapid Prototyping:** Quickly generate and test Python code snippets for tasks without manually writing boilerplate.
*   **Automate Complex Sequences:** Chain together simple instructions to build and execute sophisticated automation scripts.
*   **Learn By Doing:** See how the AI translates ideas into code and observe debugging in action.
*   **Overcome Writer's Block:** Get a starting point for scripting tasks you're unsure how to approach.
*   **Bridge AI and System Interaction:** Leverage LLM intelligence to interact with your file system, run shell commands via subprocess, and manage processes, all through a Python layer.

## ▶️ Demo

*(Since a live terminal isn't possible in Markdown, imagine this interactive flow)*

1.  **Start POOP:**
    ```bash
    python poop_agent.py # Or whatever you name the file
    ```
    (You'll see the welcome message, ASCII art, and the colored `POOP>` prompt)

2.  **Ask POOP to create a script to check free disk space:**
    ```
    POOP> write a python script to show free disk space in the current directory
    ```
    *(POOP contacts LLM, generates code)*
    `Generating new Python code...`
    `Python code received/modified from LLM.`
    `Code saved to '/path/to/your/poop<timestamp>.py'.`
    `Use 'run' to confirm and execute it.`

3.  **Run and confirm the generated code:**
    ```
    POOP> run
    ```
    *(POOP displays the generated Python code)*
    `--- The following Python code was generated/modified ---`
    `import os`
    `# Code using os.statvfs or similar`
    `...`
    `-------------------------------------------------------`
    `Execute this code? (y/N): y`
    *(You type `y`, POOP executes the script)*
    `Executing Python code (File: ...)...`
    `--- Live Python Output Start ---`
    `Free space: XX GB`
    `--- Live Python Output End ---`
    `Python execution OK.`

4.  **Ask POOP to build upon the last task (e.g., save the info to a file):**
    ```
    POOP> now save that information to a file called disk_info.txt
    ```
    *(POOP uses the previous context and code, asks LLM to modify)*
    `Continuing task (last did: 'write a python script to show free disk space...'). Modifying code...`
    `Python code received/modified from LLM.`
    `Code saved to '...'.`
    `Use 'run' to confirm and execute it.`

5.  **Run the modified script:**
    ```
    POOP> run
    ```
    *(POOP displays the combined code, including the disk space check and file writing)*
    `--- The following Python code was generated/modified ---`
    `import os`
    `# Original code to get space`
    `...`
    `# New code to write to file`
    `with open("disk_info.txt", "w") as f:`
    `    f.write(...)`
    `-------------------------------------------------------`
    `Execute this code? (y/N): y`
    *(You type `y`, POOP executes)*
    `Executing Python code (File: ...)...`
    `--- Live Python Output Start ---`
    `# Script Output`
    `--- Live Python Output End ---`
    `Python execution OK.`
    `disk_info.txt created.`

*(Consider replacing this section with a real animated GIF or video link demonstrating the workflow for maximum impact!)*

## ⚙️ Installation

1.  **Prerequisites:**
    *   **Python 3.7+:** Ensure you have a compatible Python version installed.
    *   **Google AI API Key:** Obtain one from [Google AI Studio](https://makersuite.google.com/app/apikey). You'll need to provide this via the `GOOGLE_API_KEY` environment variable or when prompted on first run.
    *   **Git (Optional but recommended):** For cloning this repository.

2.  **Clone the Repository (Recommended):**
    ```bash
    git clone <repository_url> # Replace with the actual repository URL
    cd <repository_name>
    ```
    Or manually save the provided code as a `.py` file (e.g., `poop_agent.py`).

3.  **Install Python Dependencies:**
    POOP requires the `google-generativeai` and `Pillow` libraries. Other libraries might be needed for specific tasks the LLM generates code for (e.g., `requests`, `pandas`, `numpy`, `matplotlib`).
    ```bash
    pip install google-generativeai Pillow requests pandas numpy matplotlib # Install common ones
    ```
    You might need to install other libraries (`pip install <library_name>`) later if a generated script fails with `ModuleNotFoundError`.

4.  **Install System Dependencies (Crucial!):**
    Generated scripts often rely on calling external system commands via `subprocess`. These commands need to be installed on your operating system. The specific commands depend on the tasks you ask POOP to perform and your OS/distribution.
    *   **Common on Linux:** `cat`, `ls`, `mkdir`, `rm`, `sudo`, package managers (`apt`, `pacman`, `dnf`, `yum`).
    *   **For Screenshots:** `scrot`, `grim`, `maim`, `gnome-screenshot`, `spectacle`, `imagemagick` (`import` command).
    *   **For Image Analysis (beyond Pillow):** `tesseract` (for OCR).
    *   **For Opening Files/URLs:** `xdg-open` (Linux), `open` (macOS), `start` (Windows).

    You will likely encounter `FileNotFoundError` when running scripts if a required system command is not installed. POOP's debugging might suggest installation commands (`sudo apt install ...`, `sudo pacman -S ...` etc.), but you'll need to run these manually or confirm the AI's installation script if it generates one.

## 🚀 Getting Started

1.  **Set your Google AI API Key:**
    Export it in your terminal (recommended):
    ```bash
    export GOOGLE_API_KEY='YOUR_API_KEY_HERE'
    ```
    Or have it ready to paste on the first run.

2.  **Run the script:**
    ```bash
    python poop_agent.py # Or the name you saved the file as
    ```

3.  **Start Interacting!**
    You'll see the welcome message and the `POOP>` prompt. Try typing instructions:
    *   `show my current directory contents`
    *   `create a simple calculator script`
    *   `save the current code to calculator.py`
    *   `run` (to execute the calculator script)
    *   `add a function to the calculator that calculates square root`
    *   `run` (to execute the modified calculator script)
    *   `make a screenshot and tell me what is on it` (This should trigger the AI image analysis after the script takes the shot)
    *   `img_desc /path/to/some/other/image.jpg`
    *   `sysinfo`
    *   `h` (for help)

## 🔐 Safety First!

POOP is a powerful tool that generates and executes code on your system based on AI output. **This comes with inherent risks.**

*   **ALWAYS REVIEW THE CODE:** Before typing `y` when prompted to execute new or modified code (`run` command), **carefully read and understand** what the generated Python script does.
*   **DANGEROUS COMMANDS:** Scripts may use `subprocess` to run system commands, including potentially destructive ones (`rm -rf`, `format`, etc.) or commands requiring `sudo` (which will prompt for your password). **Exercise extreme caution and verify these commands.**
*   **AI Limitations:** LLMs can hallucinate or generate incorrect/malicious code. The debugging feature helps, but it's not foolproof.
*   **Untrusted Input:** Do not paste instructions from untrusted sources without careful consideration.

**You are responsible for any code executed by POOP on your system.**

## 🛠️ How it Works (Under the Hood)

POOP operates as a loop:

1.  It captures your input command or instruction.
2.  Based on the command:
    *   If it's a built-in command (`run`, `show`, `clear`, `f`, `h`, `q`, `sysinfo`, `img_desc`, `m`, `start`, `stop`), it performs the corresponding action.
    *   If it's general text:
        *   It prepares a detailed prompt for the LLM, including the current Python code buffer, the history of the last successful task, the new user instruction, and detected system information.
        *   It sends this prompt to the connected LLM (Google Gemini).
        *   The LLM generates Python code (intended to modify the existing code or create a new script for the task).
        *   This generated code updates the internal `current_code_buffer`.
        *   The `CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN` flag is set.
3.  When the `run` command is issued (and the code needs confirmation):
    *   The full `current_code_buffer` is displayed to the user.
    *   The user is prompted to confirm execution.
    *   If confirmed, the code is written to the `CURRENT_TARGET_FILE` (a unique file if none is set) and executed using `subprocess`. For in-memory mode, `exec()` is used.
    *   Live `stdout` and `stderr` from the executed script are streamed back to the user.
    *   After execution, POOP checks the script's `stdout` for the `#POOP_ANALYZE_IMAGE_PATH: <filepath>` signal. If found and a multimodal model is available, it loads the image and calls `gmc_multimodal`.
    *   If the script execution resulted in an error (non-zero exit code for subprocess, uncaught exception for in-memory), the error output and traceback are captured.
    *   If an error occurred, POOP calls `gmc` again, this time providing the faulty code, the original instruction, the task context, system info, *and* the error feedback, asking the LLM to generate a *fixed* version of the code.
    *   The `current_code_buffer` is updated with the (potentially fixed) code, and the `CODE_MODIFIED_BY_LLM_SINCE_LAST_RUN` flag is updated/set based on whether a fix was generated.
    *   If the run was successful and no fix was needed, `LAST_SUCCESSFUL_TASK_DESCRIPTION` is updated.

## 🗺️ Future Ideas

*   Persistent history of commands and generated code.
*   More sophisticated parsing of script output to capture structured data or specific results.
*   Integration with version control (e.g., git) to track script changes.
*   Support for other programming languages (though Python is the core).
*   More advanced safety checks (e.g., static analysis of generated code for dangerous patterns).
*   Creating a dedicated POOP file format that includes code and task history.
*   A simple graphical interface.

## 👋 Contributing

Ideas, bug reports, and pull requests are welcome! Please feel free to open an issue or contribute to the codebase.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. (Note: You'll need to create a LICENSE file in your repository with the MIT license text).

## 🙏 Acknowledgements

*   Powered by Google's Gemini models via the `google-generativeai` library.
*   Uses the Pillow library for image handling.
*   Inspired by the potential of conversational AI interfaces for development and system interaction.

---

*Programmatic Operations Optimization Protocol* - *Ad Meliora*
