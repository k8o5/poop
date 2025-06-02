# POOP: Programmatic Operations Optimization Protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ⚙️ Installation

Folge diesen Schritten, um POOP auf deinem System einzurichten und zu starten.

**1. Voraussetzungen:**

*   **Python 3.7+:** Stelle sicher, dass Python installiert ist. Du kannst es von [python.org](https://www.python.org/downloads/) herunterladen.
*   **Git (Empfohlen):** Für das Klonen des Repositories. Installation unter [git-scm.com](https://git-scm.com/downloads).
*   **Google AI API Key:** Du benötigst einen API-Schlüssel von [Google AI Studio](https://makersuite.google.com/app/apikey).

**2. Projekt einrichten & Virtuelle Umgebung (venv) erstellen:**

Es wird dringend empfohlen, eine virtuelle Umgebung zu verwenden, um Abhängigkeiten zu isolieren.

   a. **Klone das Repository:**
      ```bash
      git clone https://github.com/k8o5/poop
      cd poop
      ```

   b. **Erstelle eine virtuelle Umgebung:**
      Führe im `poop`-Verzeichnis folgenden Befehl aus:
      ```bash
      python3 -m venv .venv
      ```
      (Oder `python -m venv .venv` wenn `python3` nicht dein Standardbefehl für Python 3 ist.)

   c. **Aktiviere die virtuelle Umgebung:**
      *   **Linux/macOS:**
          ```bash
          source .venv/bin/activate
          ```
      *   **Windows (PowerShell):**
          ```powershell
          .\.venv\Scripts\Activate.ps1
          ```
          (Möglicherweise musst du zuerst `Set-ExecutionPolicy Unrestricted -Scope Process` ausführen, wenn Skripte blockiert werden.)
      *   **Windows (CMD):**
          ```cmd
          .\.venv\Scripts\activate.bat
          ```
      Dein Terminal-Prompt sollte sich ändern und `(.venv)` davor anzeigen.

**3. Python-Abhängigkeiten installieren:**

Stelle sicher, dass deine virtuelle Umgebung aktiv ist. Installiere dann die benötigten Python-Pakete:
```bash
pip install google-generativeai Pillow requests pandas numpy matplotlib
```


```bash
     |o_o |
     |:_/ |
    //   \ \
   (|     | )
  /'\_   _/`\
  \___)=(___/k8o5
```

    


Use code with caution.

❤️ 
📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
