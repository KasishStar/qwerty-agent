#!/usr/bin/env python3
"""
Qwerty v3 — Tool Agent with optional LLM Brain
Architecture: LLM (optional) → tools → response
"""

import difflib
import glob as glob_module
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ─── Paths ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSTITUTION_PATH = os.path.join(BASE_DIR, "constitution.json")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")

# ─── Load Constitution ─────────────────────────────────────────
def load_constitution():
    with open(CONSTITUTION_PATH) as f:
        return json.load(f)

CONSTITUTION = load_constitution()
RULES = CONSTITUTION.get("rules", [])
IDENTITY = CONSTITUTION.get("identity", {})

# ─── Text Normalization ────────────────────────────────────────
SHORTHAND = {
    "u": "you", "r": "are", "ur": "your", "y": "why", "d": "the",
    "wat": "what", "wht": "what", "waht": "what", "wut": "what",
    "plz": "please", "pls": "please", "thx": "thanks", "ty": "thank you",
    "btw": "by the way", "idk": "i do not know", "imo": "in my opinion",
    "imho": "in my humble opinion", "afaik": "as far as i know",
    "rn": "right now", "tbh": "to be honest", "brb": "be right back",
    "np": "no problem", "nvm": "never mind",
    "bc": "because", "cuz": "because", "tho": "though",
    "ppl": "people", "msg": "message",
    "repo": "repository", "config": "configuration",
    "impl": "implementation", "param": "parameter",
    "init": "initialize", "util": "utility",
    "tmp": "temporary", "bin": "binary",
    "lib": "library", "src": "source",
    "dev": "development", "prod": "production",
    "env": "environment", "dep": "dependency",
    "pkg": "package", "dir": "directory",
    "cmd": "command", "dbg": "debug",
    "doc": "documentation",
}

def normalize(text):
    if not text or not text.strip():
        return text, text
    original = text
    t = text.lower().strip()
    for short, full in sorted(SHORTHAND.items(), key=lambda x: -len(x[0])):
        t = re.sub(r'\b' + re.escape(short) + r'\b', full, t)
    t = re.sub(r'(.)\1{3,}', r'\1\1', t)
    t = re.sub(r'([aeiou])\1{2,}', r'\1', t)
    contraction_map = {
        r"\bdont\b": "do not", r"\bdon't\b": "do not",
        r"\bcan't\b": "cannot", r"\bcant\b": "cannot",
        r"\bwont\b": "will not", r"\bwon't\b": "will not",
        r"\bdidnt\b": "did not", r"\bdidn't\b": "did not",
        r"\bisnt\b": "is not", r"\bisn't\b": "is not",
        r"\barent\b": "are not", r"\baren't\b": "are not",
        r"\bim\b": "i am", r"\bi'm\b": "i am",
        r"\byoure\b": "you are", r"\byou're\b": "you are",
        r"\bhes\b": "he is", r"\bhe's\b": "he is",
        r"\bshes\b": "she is", r"\bshe's\b": "she is",
        r"\bits\b": "it is", r"\bit's\b": "it is",
        r"\bwhats\b": "what is", r"\bwhat's\b": "what is",
        r"\bthats\b": "that is", r"\bthat's\b": "that is",
        r"\bgonna\b": "going to", r"\bwanna\b": "want to",
        r"\bgotta\b": "got to", r"\bdunno\b": "do not know",
        r"\bgimme\b": "give me", r"\blemme\b": "let me",
    }
    for pattern, replacement in contraction_map.items():
        t = re.sub(pattern, replacement, t)
    t = re.sub(r'[!?]{2,}', '?', t)
    t = re.sub(r'[,.]+', ',', t)
    return t, original

def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]

def fuzzy_word(word, vocabulary, max_dist=2):
    word = word.lower().strip()
    if not word or len(word) <= 1:
        return word, 0
    best_match = word
    best_dist = max_dist + 1
    for vw in vocabulary:
        if abs(len(vw) - len(word)) > max_dist:
            continue
        dist = levenshtein(word, vw.lower())
        if dist < best_dist:
            best_dist = dist
            best_match = vw
            if best_dist == 0:
                return best_match, 0
    return (best_match, best_dist) if best_dist <= max_dist else (word, best_dist)

def char_ngrams(s, n=3):
    s = s.lower().strip()
    return {s[i:i+n] for i in range(len(s) - n + 1)}

def ngram_jaccard(s1, s2, n=3):
    n1 = char_ngrams(s1, n)
    n2 = char_ngrams(s2, n)
    if not n1 or not n2:
        return 0.0
    return len(n1 & n2) / max(len(n1 | n2), 1)

# ─── Ethics Check ──────────────────────────────────────────────
def check_constitution(action, params=None):
    if params is None:
        params = {}
    allowed_tools = CONSTITUTION.get("authorized_tools", [])
    if action not in allowed_tools:
        return False, f"Tool '{action}' is not authorized"

    for rule in RULES:
        pattern = rule.get("pattern", "")
        if pattern == "destructive_filesystem":
            if action == "write_file" and params.get("path") and os.path.exists(params["path"]):
                return False, f"File exists at '{params['path']}'. Confirmation required."
        if pattern == "dangerous_commands":
            if action == "run_command":
                cmd = params.get("command", "").lower()
                dangerous = [
                    "rm -rf /", "rm -rf /*", "dd if=", "format ", "mkfs",
                    "sudo rm", "sudo dd", "chmod 000", "shutdown",
                    "reboot", "poweroff", "mv / ", "cp -r / ",
                ]
                for d in dangerous:
                    if d in cmd:
                        return False, f"Blocked dangerous command: '{d}'"
        if pattern == "secrets":
            content = json.dumps(params)
            if any(p in content.lower() for p in ["api_key", "token", "secret"]) and len(content) > 50:
                return False, "Potential secret detected. Redacted."
    return True, "ok"

# ─── Tool Implementations ──────────────────────────────────────
def tool_read_file(path):
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

def tool_write_file(path, content):
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def tool_edit_line(path, line, content):
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            lines = f.readlines()
        if 1 <= line <= len(lines):
            lines[line - 1] = content + '\n'
            with open(path, 'w') as f:
                f.writelines(lines)
            return f"Edited line {line} in {path}"
        return f"Line {line} out of range (file has {len(lines)} lines)"
    except Exception as e:
        return f"Error: {e}"

def tool_replace_text(path, old, new):
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            content = f.read()
        count = content.count(old)
        if count == 0:
            return f"No matches for '{old[:30]}' in {path}"
        content = content.replace(old, new)
        with open(path, 'w') as f:
            f.write(content)
        return f"Replaced {count} occurrence(s) in {path}"
    except Exception as e:
        return f"Error: {e}"

def tool_append_file(path, content):
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'a') as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def tool_list_files(path="."):
    path = os.path.expanduser(path)
    try:
        files = os.listdir(path)
        return "\n".join(sorted(files)) if files else "(empty)"
    except Exception as e:
        return f"Error: {e}"

def tool_search_files(pattern, path="."):
    path = os.path.expanduser(path)
    try:
        result = subprocess.run(
            f'grep -rn {shlex.quote(pattern)} {shlex.quote(path)} 2>/dev/null | head -30',
            shell=True, capture_output=True, text=True, timeout=10
        )
        output = result.stdout.strip()
        if not output:
            matches = []
            for root, dirs, files in os.walk(path):
                for fname in files[:20]:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, errors='ignore') as f:
                            for i, line in enumerate(f.readlines()[:100], 1):
                                if pattern in line:
                                    matches.append(f"{fpath}:{i}: {line.strip()[:100]}")
                    except:
                        pass
            output = '\n'.join(matches[:30]) if matches else "No matches found."
        return output
    except Exception as e:
        return f"Error: {e}"

def tool_find_files(pattern, path="."):
    path = os.path.expanduser(path)
    try:
        pat = pattern.strip()
        for noise in [" files", " file"]:
            if pat.endswith(noise):
                pat = pat[:-len(noise)]
        if pat.startswith(".") and "*" not in pat:
            pat = "*" + pat
        matches = glob_module.glob(f"**/{pat}", root_dir=path, recursive=True)
        if not matches:
            result = subprocess.run(
                f'find {path} -name "{pattern}" 2>/dev/null | head -30',
                shell=True, capture_output=True, text=True, timeout=10
            )
            matches = result.stdout.strip().split('\n') if result.stdout.strip() else []
        return '\n'.join(matches[:30]) if matches else "No files found."
    except Exception as e:
        return f"Error: {e}"

def tool_run_command(command):
    allowed, reason = check_constitution("run_command", {"command": command})
    if not allowed:
        return f"[Blocked] {reason}"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            output = f"(exit code {result.returncode}, no output)"
        else:
            output = f"[exit code {result.returncode}]\n{output}"
        return output
    except subprocess.TimeoutExpired:
        return "Command timed out (30s)"
    except Exception as e:
        return f"Error: {e}"

def tool_web_search(query, max_results=3):
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Qwerty/3.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        snippets = re.findall(
            r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>.*?<a class="result__snippet".*?>(.*?)</a>',
            html, re.DOTALL
        )
        results = []
        for url, title, snippet in snippets[:max_results]:
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            results.append(f"{clean_title}\n  {url}\n  {clean_snippet[:200]}")
        if results:
            return "\n\n".join(results)
        snippets = re.findall(r'<a class="result__a".*?href="(.*?)".*?>(.*?)</a>', html, re.DOTALL)
        results = []
        for url, title in snippets[:max_results]:
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            results.append(f"{clean_title}\n  {url}")
        if results:
            return "\n\n".join(results)
        return "No web results found."
    except Exception as e:
        return f"Web search unavailable: {e}"

def tool_wikipedia(query, max_sentences=5):
    def _fetch(title):
        params = {
            "action": "query", "prop": "extracts",
            "exintro": True, "explaintext": True,
            "titles": title, "redirects": 1,
            "format": "json", "origin": "*",
        }
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": "QwertyAgent/3.0 (on-demand learning)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _search(term):
        params = {
            "action": "query", "list": "search",
            "srsearch": term, "srlimit": 3, "srprop": "",
            "format": "json", "origin": "*",
        }
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": "QwertyAgent/3.0 (on-demand search)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("query", {}).get("search", [])
            return results[0]["title"] if results else None

    try:
        data = _fetch(query)
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                found = _search(query)
                if found:
                    data = _fetch(found)
                    pages = data.get("query", {}).get("pages", {})
                    for pid2, page2 in pages.items():
                        if pid2 != "-1":
                            extract = page2.get("extract", "")
                            if extract and len(extract) >= 20:
                                cleaned = re.sub(r'\s+', ' ', extract).strip()
                                sentences = re.split(r'(?<=[.!?])\s+', cleaned)
                                kept = [s for s in sentences if len(s) > 20][:max_sentences]
                                return " ".join(kept) if kept else cleaned[:300]
                return "No Wikipedia article found for that query."
            extract = page.get("extract", "")
            if not extract or len(extract) < 20:
                return "Wikipedia article has no extract."
            cleaned = re.sub(r'\s+', ' ', extract).strip()
            sentences = re.split(r'(?<=[.!?])\s+', cleaned)
            kept = [s for s in sentences if len(s) > 20][:max_sentences]
            return " ".join(kept) if kept else cleaned[:300]
        return "No Wikipedia article found."
    except urllib.error.HTTPError as e:
        return f"Wikipedia API error (rate limited: {e.code}). Try again later."
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"

def tool_learn(problem, solution):
    memory_file = os.path.join(MEMORY_DIR, "learned.json")
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if os.path.exists(memory_file):
            with open(memory_file) as f:
                memory = json.load(f)
        else:
            memory = {}
        memory[problem[:100]] = {
            "solution": solution[:1000],
            "learned_at": datetime.now().isoformat()
        }
        with open(memory_file, 'w') as f:
            json.dump(memory, f, indent=2)
        return f"Learned: '{problem[:40]}'"
    except Exception as e:
        return f"Error learning: {e}"

# ─── Tool Map ──────────────────────────────────────────────────
TOOLS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_line": tool_edit_line,
    "replace_text": tool_replace_text,
    "append_file": tool_append_file,
    "list_files": tool_list_files,
    "search_files": tool_search_files,
    "find_files": tool_find_files,
    "run_command": tool_run_command,
    "web_search": tool_web_search,
    "wikipedia": tool_wikipedia,
    "learn": tool_learn,
}

# ─── Process ───────────────────────────────────────────────────
def process(text):
    if not text or not text.strip():
        return "No input received."

    normalized, original = normalize(text)

    # Try LLM brain first
    try:
        from qwerty_agent.brain import think, check
        if check():
            result, tool_count = think(original)
            if result is not None:
                if tool_count == 0:
                    return result
                return result
    except Exception:
        pass

    # Fallback: direct tool execution for known patterns
    low = normalized.lower()
    for tool_name, patterns in [
        ("web_search", ["/web", "search web", "search internet", "look up", "find online"]),
        ("wikipedia", ["/wiki", "wikipedia", "lookup "]),
        ("run_command", ["/run", "run command"]),
        ("read_file", ["/read", "read file "]),
        ("find_files", ["/find", "find file"]),
        ("search_files", ["/search"]),
        ("list_files", ["/list", "ls", "list files"]),
    ]:
        for p in patterns:
            if low.startswith(p):
                return _execute_direct(tool_name, low, original)

    return "I don't understand. Install Ollama for full AI capabilities: ollama pull qwen2.5:7b"

def _execute_direct(tool_name, low, original):
    params = {}
    if tool_name == "web_search":
        for p in ["/web", "search web", "search internet", "look up", "find online"]:
            low = low.replace(p, "", 1) if low.startswith(p) else low
        params["query"] = original.strip()
    elif tool_name == "wikipedia":
        low = re.sub(r'^(/wiki|wikipedia|lookup)\s*', '', low)
        params["query"] = low.strip()
    elif tool_name == "run_command":
        low = re.sub(r'^/run\s*', '', low)
        params["command"] = low.strip()
    elif tool_name == "read_file":
        low = re.sub(r'^/read\s*', '', low)
        params["path"] = low.strip()
    elif tool_name == "find_files":
        low = re.sub(r'^/find\s*', '', low)
        params["pattern"] = low.strip()
    elif tool_name == "search_files":
        low = re.sub(r'^/search\s*', '', low)
        params["pattern"] = low.strip()
    elif tool_name == "list_files":
        params["path"] = "."

    fn = TOOLS.get(tool_name)
    if fn:
        try:
            return str(fn(**params))
        except Exception as e:
            return f"Error: {e}"
    return "Tool not available."

# ─── CLI ───────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result = process(text)
        print(result)
    else:
        repl()

def repl():
    print(f"{IDENTITY.get('name', 'Qwerty')} v3 — {IDENTITY.get('purpose', 'Agent')}")
    print("Type 'exit' to quit.\n")
    while True:
        try:
            text = input("> ").strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break
            result = process(text)
            print(result)
            print()
        except KeyboardInterrupt:
            print("\nBye.")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
