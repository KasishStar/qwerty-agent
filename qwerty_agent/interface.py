#!/usr/bin/env python3
"""
Qwerty v3 — Terminal User Interface
"""

import os
import sys
import json
import textwrap
import shutil
import readline
from datetime import datetime

from qwerty_agent.agent import process

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "memory", "history.json")
HIST_FILE = os.path.join(os.path.dirname(__file__), "memory", ".qwerty_history")

class C:
    RST = "\033[0m"
    BLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GRN = "\033[32m"
    YLW = "\033[33m"
    BLU = "\033[34m"
    MAG = "\033[35m"
    CYN = "\033[36m"
    LGRN = "\033[92m"
    LRED = "\033[91m"

def w():
    return shutil.get_terminal_size().columns

def strip_ansi(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def fmt_time(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%H:%M")

# ─── History ───────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history[-200:], f, indent=2)

def setup_readline():
    os.makedirs(os.path.dirname(HIST_FILE), exist_ok=True)
    try:
        readline.read_history_file(HIST_FILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(500)
    commands = [
        "/help", "/web", "/run", "/read", "/write",
        "/search", "/find", "/status", "/history",
        "/clear", "/exit", "/brain",
    ]
    def completer(text, state):
        text_lower = text.lower()
        options = [c for c in commands if c.startswith(text_lower)]
        if state < len(options):
            return options[state]
        return None
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

# ─── Brain Status ──────────────────────────────────────────────
def brain_status():
    try:
        from qwerty_agent.brain import check, DEFAULT_MODEL
        if check():
            return C.LGRN + f"◆ {DEFAULT_MODEL}" + C.RST
        return C.DIM + "◇ no LLM" + C.RST
    except Exception:
        return C.DIM + "◇ no LLM" + C.RST

# ─── Print helpers ─────────────────────────────────────────────
def print_user(text):
    ww = w()
    print()
    print(C.GRN + "  ▸ You" + C.RST + C.DIM + f"  {fmt_time()}" + C.RST)
    print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
    for line in text.split("\n"):
        wrapped = textwrap.fill(line, width=ww - 4)
        for wl in wrapped.split("\n"):
            print("  " + wl)
    print()

def print_agent(text):
    ww = w()
    print(C.BLU + "  ◇ Qwerty" + C.RST + C.DIM + f"  {fmt_time()}" + C.RST)
    print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
    result = str(text)
    for line in result.split("\n"):
        wrapped = textwrap.fill(line, width=ww - 4)
        for wl in wrapped.split("\n"):
            print("  " + wl)
    print()

def print_error(text):
    print(C.RED + "  ✗ " + str(text) + C.RST)

def print_info(text):
    print(C.YLW + "  ℹ " + str(text) + C.RST)

# ─── Banner ────────────────────────────────────────────────────
def print_banner():
    os.system("clear" if os.name == "posix" else "cls")
    ww = w()
    logo = (
        C.CYN
        + "  ██████╗ ██╗    ██╗███████╗██████╗ ████████╗██╗   ██╗\n"
        + " ██╔═══██╗██║    ██║██╔════╝██╔══██╗╚══██╔══╝╚██╗ ██╔╝\n"
        + " ██║██╗  ██║██║ █╗ ██║█████╗  ██████╔╝   ██║    ╚████╔╝\n"
        + " ██║╚██╗ ██║██║███╗██║██╔══╝  ██╔══██╗   ██║     ╚██╔╝\n"
        + " ╚██████╔╝╚███╔███╔╝███████╗██║  ██║   ██║      ██║\n"
        + "  ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝   ╚═╝      ╚═╝"
        + C.RST
    )
    print()
    for line in logo.split("\n"):
        print("  " + line)
    print()
    print(C.DIM + "  Pure Python tool agent  ·  optional LLM brain via Ollama" + C.RST)
    print("  " + brain_status() + C.DIM + "  ·  " + C.RST + "Type " + C.GRN + "/help" + C.RST + C.DIM + " for commands" + C.RST)
    print()

# ─── Commands ──────────────────────────────────────────────────
COMMANDS = {
    "/help": "Show this help",
    "/web <query>": "Search the web",
    "/wiki <topic>": "Look up Wikipedia",
    "/run <cmd>": "Run a shell command",
    "/read <path>": "Read a file",
    "/write <path>": "Write a file (enter content after)",
    "/search <text>": "Search files for text",
    "/find <pattern>": "Find files by name",
    "/status": "Show agent status",
    "/brain": "Check LLM status",
    "/history": "Show recent history",
    "/clear": "Clear screen",
    "/exit": "Quit",
}

def handle_slash(cmd, args, history):
    ww = w()

    if cmd == "help":
        print()
        print(C.BLD + "  Commands" + C.RST)
        print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
        for c, desc in COMMANDS.items():
            print(C.CYN + f"  {c:<18}" + C.RST + C.DIM + " " + desc + C.RST)
        print()
        print(C.DIM + "  For everything else, talk naturally. If Ollama is" + C.RST)
        print(C.DIM + "  installed, Qwerty uses AI to understand you." + C.RST)
        print()
        return True

    if cmd == "brain":
        try:
            from qwerty_agent.brain import check, list_models, DEFAULT_MODEL
            if check():
                models = list_models()
                print(C.LGRN + "  ✓ Brain online" + C.RST)
                print(f"  Model: {C.CYN}{DEFAULT_MODEL}{C.RST}")
                print(f"  Available: {', '.join(models[:5])}")
            else:
                print(C.YLW + "  ◇ Brain offline" + C.RST)
                print("  Install Ollama: https://ollama.com")
                print(f"  Then: ollama pull {DEFAULT_MODEL}")
        except Exception as e:
            print_error(str(e))
        print()
        return True

    if cmd == "status":
        print()
        print(C.BLD + "  Qwerty v3 — Status" + C.RST)
        print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
        print(f"  {C.CYN}Brain:{C.RST}     {brain_status()}")
        print(f"  {C.CYN}CWD:{C.RST}       {os.getcwd()}")
        print(f"  {C.CYN}History:{C.RST}   {len(history)} messages")
        print(f"  {C.CYN}Terminal:{C.RST}  {ww}x{shutil.get_terminal_size().lines}")
        print()
        return True

    if cmd == "history":
        if not history:
            print_info("No history yet.")
            return True
        print()
        for entry in history[-15:]:
            role = entry.get("role", "?")
            content = entry.get("content", "")[:80]
            ts = entry.get("timestamp", "")[:16]
            color = C.GRN if role == "user" else C.BLU
            icon = "▸" if role == "user" else "◇"
            print(color + f"  {icon} [{ts}]" + C.RST + " " + content)
        print()
        return True

    if cmd == "clear":
        print_banner()
        return True

    if cmd in ("exit", "quit"):
        return False

    # Direct tool commands via process
    result = process(f"/{cmd} {args}")
    print_agent(result)
    return True

# ─── Main ──────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        print_banner()
        print(C.DIM + "  Thinking..." + C.RST)
        result = process(text)
        print_agent(result)
        return

    history = load_history()
    setup_readline()
    print_banner()

    while True:
        try:
            bs = brain_status()
            prompt = C.LGRN + "◆" + C.RST + " "
            text = input(prompt).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print(C.DIM + "\n  Use /exit to quit" + C.RST)
            continue

        if not text:
            continue

        readline.write_history_file(HIST_FILE)

        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            if not handle_slash(cmd, args, history):
                break
            continue

        ts = datetime.now().isoformat()
        history.append({"role": "user", "content": text[:200], "timestamp": ts})
        print_user(text)

        print(C.DIM + "  Thinking..." + C.RST, end="\r")
        sys.stdout.flush()
        result = process(text)
        print(" " * 20 + "\r", end="")

        history.append({"role": "qwerty", "content": str(result)[:500], "timestamp": datetime.now().isoformat()})
        print_agent(result)

    save_history(history)
    print(C.DIM + "\n  Goodbye." + C.RST)
    print()

if __name__ == "__main__":
    main()
