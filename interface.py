#!/usr/bin/env python3
"""
Qwerty v2 — Text Interface
Pure Python stdlib. No external dependencies. Runs anywhere.
"""

import os
import sys
import json
from datetime import datetime

from agent import process, load_knowledge, recall

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "memory", "history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history[-100:], f, indent=2)

def print_banner():
    banner = """
  ██████╗ ██╗    ██╗███████╗██████╗ ████████╗██╗   ██╗
 ██╔▄▄▄▄█║██║    ██║██╔════╝██╔══██╗╚══██╔══╝╚██╗ ██╔╝
 ██║██╗  ██║██║ █╗ ██║█████╗  ██████╔╝   ██║    ╚████╔╝ 
 ██║╚██╗ ██║██║███╗██║██╔══╝  ██╔══██╗   ██║     ╚██╔╝  
 ╚██████╔╝╚███╔███╔╝███████╗██║  ██║   ██║      ██║   
  ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝   ╚═╝      ╚═╝   
                                                         
  Autonomous Development Agent v2
  Zero ML dependencies. Pure symbolic. Constitution-bound.
    """
    print(banner)
    print(f"  Knowledge: {sum(len(v) if isinstance(v, dict) else 0 for v in load_knowledge().values())} entries")
    print(f"  Rules: {len(json.load(open(os.path.join(os.path.dirname(__file__), 'constitution.json'))).get('rules', []))}")
    print(f"  Tools: read, write, edit, search, run, web, learn, know")
    print()

def handle_slash(cmd, args, history):
    if cmd == "help":
        print("  Commands:")
        print("    /help              Show this help")
        print("    /know <query>      Query local knowledge")
        print("    /web <query>       Search the web")
        print("    /learn <p> that <s> Teach Qwerty something")
        print("    /run <command>     Execute shell command")
        print("    /read <path>       Read a file")
        print("    /write <path>      Write a file (then paste content, end with Ctrl+D or '.')")
        print("    /search <pattern>  Search files for pattern")
        print("    /find <pattern>    Find files by name")
        print("    /status            Show agent status")
        print("    /history           Show recent history")
        print("    /clear             Clear screen")
        print("    /exit              Quit")
        return True
    elif cmd == "know":
        result = recall(args)
        if isinstance(result, list):
            result = str(result[0]) if result else "No knowledge found."
        print(result)
        return True
    elif cmd == "web":
        from agent import tool_web_search
        print(tool_web_search(args))
        return True
    elif cmd == "learn":
        parts = args.split(" that ", 1)
        if len(parts) > 1:
            result = process(f"learn that {parts[0].strip()} that {parts[1].strip()}")
            print(result)
        else:
            print("Usage: /learn <problem> that <solution>")
        return True
    elif cmd == "run":
        from agent import tool_run_command
        print(tool_run_command(args))
        return True
    elif cmd == "read":
        from agent import tool_read_file
        print(tool_read_file(args))
        return True
    elif cmd == "write":
        from agent import tool_write_file
        print("Enter content (end with Ctrl+D or '.' on its own line):")
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
        print(tool_write_file(args, content))
        return True
    elif cmd == "search":
        from agent import tool_search_files
        print(tool_search_files(args, "."))
        return True
    elif cmd == "find":
        from agent import tool_find_files
        print(tool_find_files(args, "."))
        return True
    elif cmd == "status":
        print(f"  Agent: Qwerty v2")
        print(f"  CWD: {os.getcwd()}")
        print(f"  Knowledge files: {len(load_knowledge())}")
        print(f"  History entries: {len(history)}")
        return True
    elif cmd == "history":
        for entry in history[-10:]:
            role = entry.get("role", "?")
            content = entry.get("content", "")[:60]
            ts = entry.get("timestamp", "")[:16]
            print(f"  [{ts}] {role}: {content}")
        return True
    elif cmd == "clear":
        os.system('clear' if os.name == 'posix' else 'cls')
        print_banner()
        return True
    elif cmd in ("exit", "quit"):
        return False
    else:
        print(f"Unknown command: /{cmd}. Type /help")
        return True

def main():
    print_banner()
    history = load_history()

    while True:
        try:
            text = input("qwerty> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\nBye.")
            break

        if not text:
            continue

        # Handle slash commands
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            if not handle_slash(cmd, args, history):
                break
            continue

        # Regular input → agent processing
        ts = datetime.now().isoformat()
        history.append({"role": "user", "content": text[:200], "timestamp": ts})

        result = process(text)

        history.append({"role": "qwerty", "content": str(result)[:500], "timestamp": datetime.now().isoformat()})

        print(result)
        print()

    save_history(history)
    print("Goodbye.")

if __name__ == "__main__":
    main()
