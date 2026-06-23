"""
Qwerty v3 — Brain (LLM connector)
Optional Ollama integration. Zero extra deps. Falls back gracefully.
"""

import json
import os
import re
import urllib.request
import urllib.error

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("QWERTY_MODEL", "qwen2.5:7b")

_TOOL_DESCRIPTIONS = None
_CONSTITUTION = None


def _load_constitution():
    global _CONSTITUTION
    if _CONSTITUTION is None:
        path = os.path.join(os.path.dirname(__file__), "constitution.json")
        try:
            with open(path) as f:
                _CONSTITUTION = json.load(f)
        except Exception:
            _CONSTITUTION = {}
    return _CONSTITUTION


def _build_tool_descriptions():
    global _TOOL_DESCRIPTIONS
    if _TOOL_DESCRIPTIONS is not None:
        return _TOOL_DESCRIPTIONS

    tools = [
        {
            "name": "read_file",
            "description": "Read the contents of a file",
            "params": {"path": "string (file path)"},
        },
        {
            "name": "write_file",
            "description": "Write content to a file (creates directories if needed)",
            "params": {"path": "string (file path)", "content": "string (file content)"},
        },
        {
            "name": "edit_line",
            "description": "Replace a specific line in a file",
            "params": {"path": "string (file path)", "line": "integer (line number)", "content": "string (new line content)"},
        },
        {
            "name": "replace_text",
            "description": "Find and replace text in a file",
            "params": {"path": "string (file path)", "old": "string (text to find)", "new": "string (replacement text)"},
        },
        {
            "name": "append_file",
            "description": "Append content to a file",
            "params": {"path": "string (file path)", "content": "string (content to append)"},
        },
        {
            "name": "list_files",
            "description": "List files in a directory",
            "params": {"path": "string (directory path, default '.')"},
        },
        {
            "name": "search_files",
            "description": "Search files for a text pattern",
            "params": {"pattern": "string (text to search for)", "path": "string (directory, default '.')"},
        },
        {
            "name": "find_files",
            "description": "Find files by name pattern",
            "params": {"pattern": "string (glob pattern like *.py)", "path": "string (directory, default '.')"},
        },
        {
            "name": "run_command",
            "description": "Execute a shell command and return output",
            "params": {"command": "string (shell command)"},
        },
        {
            "name": "web_search",
            "description": "Search the web for current information (use when you need up-to-date data)",
            "params": {"query": "string (search query)"},
        },
        {
            "name": "wikipedia",
            "description": "Look up a topic on Wikipedia",
            "params": {"query": "string (topic to look up)"},
        },
        {
            "name": "learn",
            "description": "Store a new fact or solution in long-term memory",
            "params": {"problem": "string (what was learned)", "solution": "string (the answer)"},
        },
    ]
    _TOOL_DESCRIPTIONS = tools
    return tools


def _build_system_prompt():
    const = _load_constitution()
    identity = const.get("identity", {})
    rules = const.get("rules", [])

    lines = [
        f"You are {identity.get('name', 'Qwerty')}, {identity.get('purpose', 'an autonomous AI assistant')}.",
        "",
        "## Your character",
        "- You are helpful, honest, and direct.",
        "- You can answer from your own knowledge OR use tools below.",
        "- When asked to build code, generate working solutions.",
        "- When asked to explain something, be clear and thorough.",
        "- Keep responses concise unless detail is requested.",
        "",
        "## Tools available to you",
        "When you need info beyond your training or want to interact with files/system,",
        "use a tool by outputting EXACTLY this format:",
        "",
        "[[TOOL]]",
        '{"tool": "tool_name", "params": {"key": "value"}}',
        "[[TOOL]]",
        "",
        "I will execute the tool and give you the result. Then you respond normally.",
        "",
    ]

    for t in _build_tool_descriptions():
        params_str = ", ".join(f"{k}: {v}" for k, v in t["params"].items())
        lines.append(f"- {t['name']}({params_str}) — {t['description']}")

    lines.extend([
        "",
        "## Rules",
        "- Never execute destructive commands (rm -rf /, dd, mkfs, etc.).",
        "- Never expose passwords, tokens, or secrets.",
        "- Never overwrite existing files without user confirmation.",
    ])

    for rule in rules:
        if rule.get("pattern") == "destructive_filesystem":
            lines.append("- Do not overwrite existing files without asking.")
        elif rule.get("pattern") == "dangerous_commands":
            lines.append("- Block dangerous system commands.")

    lines.extend([
        "",
        "## Response style",
        "- Answer in plain text.",
        "- Use code blocks (```) for code.",
        "- If you don't know something, use web_search or wikipedia.",
        "- If asked to build or create, use write_file.",
    ])

    return "\n".join(lines)


def _call_ollama(messages, timeout=30):
    payload = json.dumps({
        "model": DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 8192},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get("message", {}).get("content", "")
    except Exception as e:
        return None


def _parse_tool_call(text):
    m = re.search(r'\[\[TOOL\]\]\s*(\{.*?\})\s*\[\[TOOL\]\]', text, re.DOTALL)
    if not m:
        return None, text
    try:
        call = json.loads(m.group(1))
        tool = call.get("tool")
        params = call.get("params", {})
        remaining = text[:m.start()] + text[m.end():]
        return (tool, params), remaining.strip()
    except (json.JSONDecodeError, KeyError):
        return None, text


def _execute_tool(tool_name, params):
    try:
        from qwerty_agent.agent import TOOLS
    except ImportError:
        from agent import TOOLS

    if tool_name not in TOOLS:
        return f"Error: unknown tool '{tool_name}'"

    fn = TOOLS[tool_name]
    try:
        result = fn(**params)
        return str(result) if result is not None else "(no output)"
    except Exception as e:
        return f"Error: {e}"


def check():
    """Check if Ollama is available and the model exists."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            for m in models:
                if DEFAULT_MODEL in m or m in DEFAULT_MODEL:
                    return True
            return len(models) > 0
    except Exception:
        return False


def list_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def think(user_input, conversation=None, max_tool_rounds=5):
    """Main thinking loop. Returns (response_text, tool_used_count)."""
    if conversation is None:
        conversation = []

    system = _build_system_prompt()
    messages = [{"role": "system", "content": system}]
    for msg in conversation[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})

    tool_count = 0
    final_response = ""

    for _ in range(max_tool_rounds):
        raw = _call_ollama(messages)
        if raw is None:
            return None, 0

        call_info, clean_text = _parse_tool_call(raw)

        if call_info is None:
            final_response = clean_text
            break

        tool_name, params = call_info
        tool_count += 1
        result = _execute_tool(tool_name, params)
        tool_text = f"[Tool {tool_name} returned]:\n{result[:1000]}"
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": tool_text})

    if not final_response:
        final_response = raw

    return final_response.strip(), tool_count
