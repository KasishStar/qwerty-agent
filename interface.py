#!/usr/bin/env python3
"""
Qwerty v2 — Terminal User Interface
Pure Python stdlib. No dependencies. Runs anywhere.
"""

import os
import sys
import json
import textwrap
import shutil
import readline
import glob as glob_module
from datetime import datetime

from agent import process, load_knowledge, recall

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "memory", "history.json")
HIST_FILE = os.path.join(os.path.dirname(__file__), "memory", ".qwerty_history")

# ─── ANSI helpers ──────────────────────────────────────────────
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
    WHT = "\033[37m"
    LRED = "\033[91m"
    LGRN = "\033[92m"
    LYLW = "\033[93m"
    LBLU = "\033[94m"
    LMAG = "\033[95m"
    LCYN = "\033[96m"

def w():
    return shutil.get_terminal_size().columns

def strip_ansi(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def fmt_time(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%H:%M")

# ─── Load / Save History ──────────────────────────────────────
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
        "/help", "/know", "/web", "/learn", "/run",
        "/read", "/write", "/search", "/find",
        "/status", "/history", "/clear", "/exit",
    ]

    def completer(text, state):
        text_lower = text.lower()
        options = [c for c in commands if c.startswith(text_lower)]
        if state < len(options):
            return options[state]
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

# ─── Print helpers ─────────────────────────────────────────────
def print_plan_start(description):
    ww = w()
    print()
    print(C.MAG + "  ⚙ Planning" + C.RST + C.DIM + f"  {fmt_time()}" + C.RST)
    print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
    print("  " + description)
    print()

def print_step_progress(current, total, description):
    ww = w()
    bar_len = ww - 20
    filled = int(bar_len * current / max(total, 1))
    bar = C.MAG + "█" * filled + C.DIM + "░" * (bar_len - filled) + C.RST
    print(C.DIM + f"  Step {current}/{total}:" + C.RST + f" {description}")
    print("  " + bar)

def print_plan_result(text):
    ww = w()
    print(C.MAG + "  ⚙ Plan complete" + C.RST + C.DIM + f"  {fmt_time()}" + C.RST)
    print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
    for line in str(text).split("\n"):
        wrapped = textwrap.fill(line, width=ww - 4)
        for wl in wrapped.split("\n"):
            print("  " + wl)
    print()

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

def print_agent(text, tooltips=None):
    ww = w()
    print(C.BLU + "  ◇ Qwerty" + C.RST + C.DIM + f"  {fmt_time()}" + C.RST)
    print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
    result = str(text)
    for line in result.split("\n"):
        wrapped = textwrap.fill(line, width=ww - 4)
        for wl in wrapped.split("\n"):
            print("  " + wl)
    if tooltips:
        print()
        print(C.DIM + "  " + " ".join(f"[{t}]" for t in tooltips) + C.RST)
    print()

def print_error(text):
    print(C.RED + "  ✗ " + str(text) + C.RST)

def print_info(text):
    print(C.YLW + "  ℹ " + str(text) + C.RST)

# ─── Banner ────────────────────────────────────────────────────
def print_banner():
    ww = w()
    os.system("clear" if os.name == "posix" else "cls")
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
    kw = load_knowledge()
    entry_count = sum(
        len(v) if isinstance(v, dict) else 0
        for v in kw.values()
    )
    print(C.DIM + f"  Zero-dependency symbolic AI  ·  {entry_count} knowledge entries")
    print("  Type " + C.GRN + "/help" + C.RST + C.DIM + " for commands or just ask me anything" + C.RST)
    print()

# ─── Slash Commands ────────────────────────────────────────────
COMMANDS = {
    "/help": "Show this help",
    "/know": "Query local knowledge (e.g. /know what is a kernel)",
    "/web": "Search the web (e.g. /web latest rust news)",
    "/learn": "Teach Qwerty: /learn <problem> that <solution>",
    "/run": "Run a shell command (e.g. /run ls -la)",
    "/read": "Read a file (e.g. /read path/to/file)",
    "/write": "Write a file (enter content after)",
    "/search": "Search files for pattern (e.g. /search def main)",
    "/find": "Find files by name (e.g. /find *.py)",
    "/status": "Show agent status",
    "/history": "Show recent conversation history",
    "/clear": "Clear the screen",
    "/exit": "Exit Qwerty",
}

def handle_slash(cmd, args, history):
    ww = w()

    if cmd == "help":
        print()
        print(C.BLD + "  Commands" + C.RST)
        print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
        for c, desc in COMMANDS.items():
            print(C.CYN + f"  {c:<10}" + C.RST + C.DIM + " " + desc + C.RST)
        print()
        print(C.DIM + "  You can also ask anything in plain English." + C.RST)
        print(C.DIM + "  Qwerty will figure out what to do." + C.RST)
        print()
        return True

    if cmd == "know":
        if not args:
            print_info("Usage: /know <query>")
            return True
        result = recall(args)
        if isinstance(result, list):
            result = str(result[0]) if result else "No knowledge found."
        print_agent(result, ["knowledge"])
        return True

    if cmd == "web":
        if not args:
            print_info("Usage: /web <query>")
            return True
        from agent import tool_web_search
        print_info("Searching the web...")
        result = tool_web_search(args)
        print_agent(result, ["web"])
        return True

    if cmd == "learn":
        if not args:
            print_info("Usage: /learn <problem> that <solution>")
            return True
        parts = args.split(" that ", 1)
        if len(parts) > 1:
            result = process(f"learn that {parts[0].strip()} that {parts[1].strip()}")
            print_agent(result, ["learned"])
        else:
            print_info("Usage: /learn <problem> that <solution>")
        return True

    if cmd == "run":
        if not args:
            print_info("Usage: /run <command>")
            return True
        from agent import tool_run_command
        print_info("Running...")
        result = tool_run_command(args)
        print_agent(result, ["shell"])
        return True

    if cmd == "read":
        if not args:
            print_info("Usage: /read <path>")
            return True
        from agent import tool_read_file
        result = tool_read_file(args)
        print_agent(result, ["file"])
        return True

    if cmd == "write":
        if not args:
            print_info("Usage: /write <path>")
            return True
        from agent import tool_write_file
        print_info("Enter content (Ctrl+D or '.' on its own line to finish):")
        lines = []
        while True:
            try:
                line = input()
                if line == '.':
                    break
                lines.append(line)
            except EOFError:
                break
        content = "\n".join(lines)
        result = tool_write_file(args, content)
        print_agent(result, ["file"])
        return True

    if cmd == "search":
        if not args:
            print_info("Usage: /search <pattern>")
            return True
        from agent import tool_search_files
        print_info("Searching...")
        result = tool_search_files(args, ".")
        print_agent(result, ["search"])
        return True

    if cmd == "find":
        if not args:
            print_info("Usage: /find <pattern>")
            return True
        from agent import tool_find_files
        print_info("Finding...")
        result = tool_find_files(args, ".")
        print_agent(result, ["find"])
        return True

    if cmd == "status":
        kw = load_knowledge()
        entry_count = sum(
            len(v) if isinstance(v, dict) else 0
            for v in kw.values()
        )
        print()
        print(C.BLD + "  Qwerty v2 — Status" + C.RST)
        print(C.DIM + "  " + "─" * (ww - 4) + C.RST)
        print(f"  {C.CYN}CWD:{C.RST}        {os.getcwd()}")
        print(f"  {C.CYN}Knowledge:{C.RST}   {entry_count} entries in {len(kw)} files")
        print(f"  {C.CYN}History:{C.RST}    {len(history)} messages")
        print(f"  {C.CYN}Terminal:{C.RST}   {ww}x{shutil.get_terminal_size().lines}")
        print(f"  {C.CYN}Python:{C.RST}     {sys.version}")
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
            if role == "user":
                print(C.GRN + f"  ▸ [{ts}]" + C.RST + " " + content)
            else:
                print(C.BLU + f"  ◇ [{ts}]" + C.RST + " " + content)
        print()
        return True

    if cmd == "clear":
        print_banner()
        return True

    if cmd in ("exit", "quit"):
        return False

    print_error(f"Unknown command: /{cmd}")
    print_info(f"Type {C.GRN}/help{C.RST} for available commands")
    return True

# ─── Main ──────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        print_banner()
        print(C.DIM + "  Thinking..." + C.RST)
        result = process(text)
        if str(result).startswith("Plan:"):
            print_plan_result(result)
        elif str(result).startswith("Explored:"):
            print_agent(result)
        else:
            print_agent(result)
        return

    history = load_history()
    setup_readline()
    print_banner()

    while True:
        try:
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
        if str(result).startswith("Plan:"):
            print_plan_result(result)
        elif str(result).startswith("Explored:"):
            print_agent(result)
        else:
            print_agent(result)

    save_history(history)
    print(C.DIM + "\n  Goodbye." + C.RST)
    print()

if __name__ == "__main__":
    main()
