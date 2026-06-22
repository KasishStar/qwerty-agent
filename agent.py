#!/usr/bin/env python3
"""
Qwerty v2 — Autonomous Symbolic Agent
Zero external dependencies. Pure Python stdlib. Runs anywhere.

Architecture:
  1. User input → Constitution check → Intent classify → Plan → Execute → Result
  2. Layered execution: react → routine → explore → internet → report
  3. Every action checked against constitution
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

# Genius neural engine (optional — falls back to deterministic if unavailable)
try:
    from genius import generate_response as genius_respond
    HAS_GENIUS = True
except ImportError:
    HAS_GENIUS = False

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSTITUTION_PATH = os.path.join(BASE_DIR, "constitution.json")
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
WORKFLOWS_DIR = os.path.join(BASE_DIR, "workflows")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")

# ─── Load Constitution ─────────────────────────────────────────────────────────
def load_constitution():
    with open(CONSTITUTION_PATH) as f:
        return json.load(f)

CONSTITUTION = load_constitution()
RULES = CONSTITUTION.get("rules", [])
IDENTITY = CONSTITUTION.get("identity", {})
AUTHORIZED_TOOLS = CONSTITUTION.get("authorized_tools", [])
LAYERS = CONSTITUTION.get("layers", {}).get("order", [])

# ─── Knowledge System ──────────────────────────────────────────────────────────
_knowledge_cache = {}

def load_knowledge():
    """Load all JSON knowledge files from the knowledge directory."""
    global _knowledge_cache
    if _knowledge_cache:
        return _knowledge_cache
    knowledge = {}
    if os.path.isdir(KNOWLEDGE_DIR):
        for fname in os.listdir(KNOWLEDGE_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(KNOWLEDGE_DIR, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    key = fname.replace(".json", "")
                    knowledge[key] = data
                except Exception as e:
                    knowledge[fname] = {"error": str(e)}
    _knowledge_cache = knowledge
    return knowledge

def recall(problem, top_k=3):
    """Find best matching knowledge entry using string similarity (no vectors).
    Navigates 3 levels deep: category → subcategory → problem_key → solution.
    Normalizes input for typo/shorthand tolerance."""
    knowledge = load_knowledge()
    # Normalize the problem text for fuzzy matching
    normalized, _ = normalize(problem)
    problem_lower = normalized if normalized else problem.lower().strip()
    prob_kw = _meaningful(problem_lower)

    matches = []

    for category, entries in knowledge.items():
        if isinstance(entries, dict):
            for subcat, sub_entries in entries.items():
                if isinstance(sub_entries, dict):
                    # Level 3: individual problem keys — best matches
                    for key, value in sub_entries.items():
                        key_lower = key.lower().strip()
                        _match_key(problem_lower, key_lower, value, matches)
                        # Also check if query keywords appear in the value
                        if prob_kw:
                            value_lower = str(value).lower()
                            if any(kw in value_lower for kw in prob_kw):
                                matches.append((0.3, value))
                    # Level 2: subcategory name — only on strong direct match
                    subcat_lower = subcat.lower().strip()
                    if not problem_lower.startswith("tell me"):
                        if problem_lower == subcat_lower or subcat_lower in problem_lower or problem_lower in subcat_lower:
                            for key, value in sub_entries.items():
                                matches.append((0.6, value))
                else:
                    # Level 2: direct values (flat entries)
                    key_lower = subcat.lower().strip()
                    _match_key(problem_lower, key_lower, sub_entries, matches)

    matches.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by value content
    seen = set()
    unique = []
    for score, value in matches:
        val_str = str(value)[:100]
        if val_str not in seen:
            seen.add(val_str)
            unique.append((score, value))

    return [m[1] for m in unique[:top_k]]

STOPWORDS = {"what", "how", "is", "are", "the", "a", "an", "in", "on", "at", "to",
             "for", "of", "with", "and", "or", "do", "does", "did", "i", "you",
             "we", "they", "he", "she", "it", "this", "that", "these", "those",
             "tell", "me", "about", "explain", "show", "find", "list", "run"}

def _meaningful(s):
    return {w for w in re.findall(r'\w+', s.lower()) if w not in STOPWORDS and len(w) > 1}

def _match_key(problem_lower, key_lower, value, matches):
    """Compare problem against a single knowledge key.
    Multi-phase: exact → substring → keyword overlap → fuzzy word → n-gram + difflib."""

    # 1. Exact match — instant win
    if problem_lower == key_lower or problem_lower.startswith(key_lower) or key_lower.startswith(problem_lower):
        matches.append((1.0, value))
        return

    # 2. Substring match — strong signal
    if key_lower in problem_lower or problem_lower in key_lower:
        score = len(key_lower) / max(len(problem_lower), len(key_lower), 1)
        matches.append((0.8 + score * 0.2, value))
        return

    # 3. Keyword overlap — best semantic signal with no ML
    prob_kw = _meaningful(problem_lower)
    key_kw = _meaningful(key_lower)

    if prob_kw and key_kw:
        overlap = prob_kw & key_kw
        if overlap:
            query_cov = len(overlap) / len(prob_kw)
            entry_cov = len(overlap) / len(key_kw)
            combined = (query_cov + entry_cov) / 2
            score = min(0.5 + combined * 0.4, 0.9)  # Range: 0.5–0.9
            matches.append((score, value))
            return

    # 4. Fuzzy word matching — meaningful query words vs key words
    prob_meaningful = [w for w in re.findall(r'\w+', problem_lower)
                       if w not in STOPWORDS and len(w) > 2]
    key_words = set(re.findall(r'\w+', key_lower))
    if prob_meaningful and key_words:
        fuzzy_matches = 0
        for qw in prob_meaningful:
            for kw in key_words:
                if levenshtein(qw, kw) <= max(1, len(kw) // 3):
                    fuzzy_matches += 1
                    break
        if fuzzy_matches > 0:
            denom = len(prob_meaningful)
            score = fuzzy_matches / denom
            matches.append((min(0.3 + score * 0.65, 0.95), value))
            return

    # 5. Character n-gram Jaccard — robust to typos ('kernul' vs 'kernel')
    ngram_sim = ngram_jaccard(problem_lower, key_lower, 3)
    if ngram_sim > 0.35:
        matches.append((ngram_sim * 0.7 + 0.2, value))
        return

    # 6. Difflib ratio — last resort for very fuzzy matches
    ratio = difflib.SequenceMatcher(None, problem_lower, key_lower).ratio()
    if ratio > 0.5:
        matches.append((ratio * 0.6, value))
        return

# ─── Text Normalization ────────────────────────────────────────────────────────
# Handles typos, shorthand, slang, character repeats, informal speech

SHORTHAND = {
    # Common internet/text shorthand
    "u": "you", "r": "are", "ur": "your", "y": "why", "d": "the",
    "wat": "what", "wht": "what", "waht": "what", "wut": "what",
    "plz": "please", "pls": "please", "thx": "thanks", "ty": "thank you",
    "btw": "by the way", "idk": "i do not know", "imo": "in my opinion",
    "imho": "in my humble opinion", "afaik": "as far as i know",
    "rn": "right now", "tbh": "to be honest", "brb": "be right back",
    "np": "no problem", "nvm": "never mind", "omw": "on my way",
    "lol": "ha", "lmao": "ha", "rofl": "ha",
    "w": "with", "w/o": "without", "w/": "with",
    "bc": "because", "cuz": "because", "b/c": "because",
    "tho": "though", "thru": "through", "ppl": "people",
    "msg": "message", "info": "information", "doc": "documentation",
    "convo": "conversation", "diff": "difference",
    # Developer shorthand
    "repo": "repository", "config": "configuration",
    "impl": "implementation", "info": "information",
    "param": "parameter", "init": "initialize",
    "util": "utility", "tmp": "temporary",
    "bin": "binary", "exe": "executable",
    "lib": "library", "src": "source",
    "dev": "development", "prod": "production",
    "env": "environment", "dep": "dependency",
    "pkg": "package", "dir": "directory",
    "cmd": "command", "comp": "compile",
    "dbg": "debug", "doc": "documentation",
}

PHONETIC_SUBS = [
    # Common phonetic patterns in misspellings
    (r'\bph\b', 'f'),       # phone → fone (standardize on f)
    (r'\bkn\b', 'n'),        # knowledge → nowledge
    (r'\bwr\b', 'r'),        # write → rite
    (r'\bps\b', 's'),        # psychology → sychology
    (r'k', 'k'),             # keep hard c/k as-is
]

def normalize(text):
    """Normalize messy text: shorthand → full, dedup chars, fix common typos.
    Returns (normalized_text, original_text) for traceability."""
    if not text or not text.strip():
        return text, text

    original = text
    t = text.lower().strip()

    # Phase 1: Shorthand expansion (word boundaries)
    for short, full in sorted(SHORTHAND.items(), key=lambda x: -len(x[0])):
        t = re.sub(r'\b' + re.escape(short) + r'\b', full, t)

    # Phase 2: Character deduplication (hellooo → hello, noooope → nope)
    # Preserve intentional doubles ("ss" in "kernel", "ll" in "will")
    t = re.sub(r'(.)\1{3,}', r'\1\1', t)  # 4+ same → 2
    # Remove triple repeats only for vowels (aaah → ah, but keep "aaa")
    t = re.sub(r'([aeiou])\1{2,}', r'\1', t)

    # Phase 3: Expand common contractions for consistent matching
    contraction_map = {
        r"\bdont\b": "do not", r"\bdon't\b": "do not",
        r"\bcan't\b": "cannot", r"\bcant\b": "cannot",
        r"\bwont\b": "will not", r"\bwon't\b": "will not",
        r"\bdidnt\b": "did not", r"\bdidn't\b": "did not",
        r"\bisnt\b": "is not", r"\bisn't\b": "is not",
        r"\barent\b": "are not", r"\baren't\b": "are not",
        r"\bwasnt\b": "was not", r"\bwasn't\b": "was not",
        r"\bwerent\b": "were not", r"\bweren't\b": "were not",
        r"\bhasnt\b": "has not", r"\bhasn't\b": "has not",
        r"\bhavent\b": "have not", r"\bhaven't\b": "have not",
        r"\bcouldnt\b": "could not", r"\bcouldn't\b": "could not",
        r"\bwouldnt\b": "would not", r"\bwouldn't\b": "would not",
        r"\bshouldnt\b": "should not", r"\bshouldn't\b": "should not",
        r"\bdont\b": "do not",
        r"\bim\b": "i am", r"\bi'm\b": "i am",
        r"\byoure\b": "you are", r"\byou're\b": "you are",
        r"\bhes\b": "he is", r"\bhe's\b": "he is",
        r"\bshes\b": "she is", r"\bshe's\b": "she is",
        r"\bits\b": "it is", r"\bit's\b": "it is",
        r"\btheres\b": "there is", r"\bthere's\b": "there is",
        r"\bwhats\b": "what is", r"\bwhat's\b": "what is",
        r"\bthats\b": "that is", r"\bthat's\b": "that is",
        r"\bheres\b": "here is", r"\bhere's\b": "here is",
        r"\bwhos\b": "who is", r"\bwho's\b": "who is",
        r"\bgonna\b": "going to", r"\bwanna\b": "want to",
        r"\bgotta\b": "got to", r"\bdunno\b": "do not know",
        r"\bgimme\b": "give me", r"\blemme\b": "let me",
        r"\bcmon\b": "come on",
    }
    for pattern, replacement in contraction_map.items():
        t = re.sub(pattern, replacement, t)

    # Phase 4: Remove excess punctuation but keep sentence structure
    t = re.sub(r'[!?]{2,}', '?', t)  # ??? → ?, !!! → !
    t = re.sub(r'[,.]+', ',', t)      # ,,, → ,

    return t, original


def levenshtein(s1, s2):
    """Pure Python Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(
                curr[j] + 1,       # insertion
                prev[j + 1] + 1,   # deletion
                prev[j] + cost     # substitution
            ))
        prev = curr
    return prev[-1]


def fuzzy_word(word, vocabulary, max_dist=2):
    """Find the closest word in vocabulary to `word` within edit distance `max_dist`.
    Returns (best_match, distance) or (None, max_dist+1) if no match found."""
    word = word.lower().strip()
    if not word or len(word) <= 1:
        return word, 0

    best_match = word
    best_dist = max_dist + 1

    for vocab_word in vocabulary:
        # Quick length-based filter (must be within max_dist by length)
        if abs(len(vocab_word) - len(word)) > max_dist:
            continue
        dist = levenshtein(word, vocab_word.lower())
        if dist < best_dist:
            best_dist = dist
            best_match = vocab_word
            if best_dist == 0:
                return best_match, 0

    if best_dist <= max_dist:
        return best_match, best_dist
    return word, best_dist


def build_vocabulary():
    """Build a vocabulary of all meaningful words from knowledge keys."""
    vocab = set()
    knowledge = load_knowledge()
    for category, entries in knowledge.items():
        if isinstance(entries, dict):
            for subcat, sub_entries in entries.items():
                vocab.add(subcat.lower())
                if isinstance(sub_entries, dict):
                    for key in sub_entries:
                        for w in re.findall(r'\w+', key.lower()):
                            if len(w) > 2:
                                vocab.add(w)
                else:
                    for w in re.findall(r'\w+', subcat.lower()):
                        if len(w) > 2:
                            vocab.add(w)
    # Add pattern keywords
    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            for w in re.findall(r'\w+', p.lower()):
                if len(w) > 2:
                    vocab.add(w)
    return vocab

# Build vocabulary once (lazy: built after module fully loads)
_KNOWLEDGE_VOCAB = None
def get_vocab():
    global _KNOWLEDGE_VOCAB
    if _KNOWLEDGE_VOCAB is None:
        _KNOWLEDGE_VOCAB = build_vocabulary()
    return _KNOWLEDGE_VOCAB


def char_ngrams(s, n=3):
    """Generate character n-grams from a string."""
    s = s.lower().strip()
    return {s[i:i+n] for i in range(len(s) - n + 1)}


def ngram_jaccard(s1, s2, n=3):
    """Jaccard similarity of character n-grams between two strings.
    Robust to typos: 'kernul' and 'kernel' share most 3-grams."""
    n1 = char_ngrams(s1, n)
    n2 = char_ngrams(s2, n)
    if not n1 or not n2:
        return 0.0
    intersection = n1 & n2
    union = n1 | n2
    return len(intersection) / max(len(union), 1)


# ─── Vibe / Tone Detection ─────────────────────────────────────────────────────

def detect_tone(text):
    """Detect the user's tone from their input. Returns a tone profile dict."""
    t = text.lower().strip()

    tone = {
        "urgent": False,
        "question": False,
        "frustrated": False,
        "excited": False,
        "short": False,
        "formal": True,
        "casual": False,
    }

    # Question detection
    if '?' in t or t.startswith(("what", "how", "why", "when", "where", "who", "is ", "are ", "can ", "do ", "does ")):
        tone["question"] = True

    # Urgency markers
    if any(w in t for w in ["urgent", "asap", "quick", "fast", "hurry", "now"]):
        tone["urgent"] = True

    # Frustration markers
    if any(w in t for w in ["wtf", "why the", "not working", "broken", "error", "fix this", "stupid", "annoying"]):
        tone["frustrated"] = True

    # Excitement markers
    if '!!' in text or any(w in t for w in ["awesome", "great", "amazing", "cool", "nice", "perfect", "love"]):
        tone["excited"] = True

    # Casual vs formal
    if any(w in t for w in SHORTHAND if len(w) <= 3):
        tone["casual"] = True
        tone["formal"] = False
    if len(t.split()) <= 3:
        tone["short"] = True

    return tone

# ─── Ethics Check ──────────────────────────────────────────────────────────────
def check_constitution(action, params=None):
    """
    Check an action against every rule in the constitution.
    Returns (allowed: bool, reason: str)
    """
    if params is None:
        params = {}

    # Check if tool is authorized
    if action not in AUTHORIZED_TOOLS:
        return False, f"Tool '{action}' is not in authorized tools list"

    # Check each rule
    for rule in RULES:
        rule_pattern = rule.get("pattern", "")
        rule_action = rule.get("action", "")

        # Build action string for pattern matching
        action_str = action
        if isinstance(params, dict):
            action_str += " " + json.dumps(params)

        # Check destructive filesystem operations
        if rule_pattern == "destructive_filesystem":
            if action == "write_file" and params.get("path") and os.path.exists(params.get("path", "")):
                return False, f"r001: File exists at '{params['path']}'. User confirmation required before overwriting."

        # Check dangerous commands
        if rule_pattern == "dangerous_commands":
            if action == "run_command":
                cmd = params.get("command", "").lower()
                dangerous = [
                    "rm -rf /", "rm -rf /*", "rm -rf --no-preserve-root",
                    "dd if=", "format ", "mkfs", "mkswap", "> /dev/sd",
                    "sudo rm", "sudo dd", "sudo mkfs", "sudo fdisk",
                    "chmod 000", "chmod -r 000", "chown -r 0:0",
                    "kill -9", "pkill -9", "shutdown", "reboot",
                    "poweroff", "init 0", "init 6",
                    "mv / ", "cp -r / ", ":(){ :|:& };:", "> /dev/sda",
                ]
                for d in dangerous:
                    if d in cmd:
                        return False, f"r002: Blocked dangerous command pattern: '{d}'"

        # Check secrets
        if rule_pattern == "secrets":
            content = json.dumps(params)
            secret_patterns = ["password", "api_key", "token", "secret", "auth"]
            # Only flag if value looks like a credential (long random string)
            for pat in secret_patterns:
                if pat in content.lower() and len(content) > 50:
                    return False, f"r003: Potential secret detected. Redacted for safety."

    return True, "ok"

# ─── Tool Implementations ──────────────────────────────────────────────────────

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
        escaped_pat = shlex.quote(pattern)
        escaped_path = shlex.quote(path)
        result = subprocess.run(
            f'grep -rn {escaped_pat} {escaped_path} 2>/dev/null | head -30',
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
        # Normalize pattern: strip trailing noise, add wildcard if needed
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
    # Block dangerous commands before execution
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
    """Search the web using DuckDuckGo (no API key needed)."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Qwerty/2.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # Simple HTML snippet extraction (no parser needed)
        snippets = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>.*?<a class="result__snippet".*?>(.*?)</a>',
                              html, re.DOTALL)
        results = []
        for url, title, snippet in snippets[:max_results]:
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            results.append(f"{clean_title}\n  {url}\n  {clean_snippet[:200]}")

        if results:
            return "\n\n".join(results)

        # Fallback: try different regex
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

def tool_read_knowledge(query):
    """Query the local knowledge base."""
    result = recall(query)
    if isinstance(result, list):
        if result:
            return str(result[0])
        return "No knowledge found for that query."
    return str(result)

def tool_learn(problem, solution):
    """Store a new knowledge entry."""
    memory_file = os.path.join(MEMORY_DIR, "learned.json")
    if os.path.exists(memory_file):
        with open(memory_file) as f:
            memory = json.load(f)
    else:
        memory = {}

    memory[problem] = {
        "solution": solution,
        "learned_at": datetime.now().isoformat()
    }

    with open(memory_file, 'w') as f:
        json.dump(memory, f, indent=2)

    # Also add to knowledge cache
    if "learned" in _knowledge_cache:
        _knowledge_cache["learned"][problem] = solution
    else:
        _knowledge_cache["learned"] = {problem: solution}

    return f"Learned: '{problem}' → '{solution[:50]}...'"


def tool_analyze_error(output):
    """Analyze error output, extract error type, key terms, and file info."""
    if not output or len(output) < 5:
        return {"error_type": "unknown", "key_terms": [], "files": [], "suggested_query": ""}

    lines = output.split('\n')
    error_type = "unknown"
    key_terms = set()
    files = set()

    if any(w in output.lower() for w in ["error[", "error:", "compilation error", "cannot find"]):
        error_type = "compilation"
        for line in lines:
            m = re.search(r'(?:-->\s+)?([^\s]+):(\d+):(\d+)', line)
            if m:
                files.add(m.group(1))
            ec = re.findall(r'error\[([A-Z]\d+)\]', line)
            for e in ec:
                key_terms.add(e.lower())

    if any(w in output.lower() for w in ["traceback", "exception", "panic", "segmentation fault", "killed"]):
        error_type = "runtime"
        for line in lines:
            m = re.search(r'Error:\s*(.+)', line)
            if m:
                key_terms.add(m.group(1).strip().lower()[:40])

    if "command not found" in output.lower() or "not found" in output.lower():
        error_type = "missing_command"
        for line in lines:
            m = re.search(r'(\w+):\s*(command|not found)', line)
            if m:
                key_terms.add(m.group(1).lower())

    m = re.search(r'exit code (\d+)', output.lower())
    if m and m.group(1) != '0':
        if error_type == "unknown":
            error_type = f"exit_code_{m.group(1)}"

    for w in re.findall(r'\w+', output.lower()):
        if w not in STOPWORDS and len(w) > 3 and w not in ('error', 'line', 'file', 'note', 'help'):
            key_terms.add(w)

    query_words = [w for w in key_terms if len(w) > 2][:6]
    suggested_query = " ".join(query_words) if query_words else ""

    return {
        "error_type": error_type,
        "key_terms": list(key_terms)[:10],
        "files": list(files)[:3],
        "suggested_query": suggested_query,
    }


def tool_web_and_learn(query, max_results=3):
    """Search the web, auto-learn the results, return them."""
    result = tool_web_search(query, max_results)
    if result and "No web results found" not in result and "Web search unavailable" not in result:
        try:
            _persist_knowledge(f"web:{query}", result[:500], f"auto-learned from web at {datetime.now().isoformat()[:16]}")
        except Exception:
            pass
    return result


def _persist_knowledge(problem, solution, source="learned"):
    """Store a knowledge entry permanently."""
    memory_file = os.path.join(MEMORY_DIR, "learned.json")
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if os.path.exists(memory_file):
            with open(memory_file) as f:
                memory = json.load(f)
        else:
            memory = {}
        key = problem[:100]
        memory[key] = {
            "solution": solution[:1000],
            "source": source,
            "learned_at": datetime.now().isoformat()
        }
        with open(memory_file, 'w') as f:
            json.dump(memory, f, indent=2)
        global _knowledge_cache
        if _knowledge_cache:
            if "learned" not in _knowledge_cache:
                _knowledge_cache["learned"] = {}
            sub = problem[:40]
            _knowledge_cache["learned"][sub] = solution[:300]
        return True
    except Exception:
        return False


def tool_wikipedia(query, max_sentences=5):
    """Query Wikipedia API for a topic summary. Stores result in knowledge."""
    def _fetch(title):
        params = {
            "action": "query", "prop": "extracts",
            "exintro": True, "explaintext": True,
            "titles": title, "redirects": 1,
            "format": "json", "origin": "*",
        }
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": "QwertyAgent/2.0 (on-demand learning)"
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
            "User-Agent": "QwertyAgent/2.0 (on-demand search)"
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
                # Try search fallback
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
                                result = " ".join(kept) if kept else cleaned[:300]
                                _persist_knowledge(f"wiki:{found[:60]}", result[:1000], source="wikipedia_api")
                                return result
                return "No Wikipedia article found for that query."

            extract = page.get("extract", "")
            if not extract or len(extract) < 20:
                return "Wikipedia article has no extract."

            cleaned = re.sub(r'\s+', ' ', extract).strip()
            sentences = re.split(r'(?<=[.!?])\s+', cleaned)
            kept = [s for s in sentences if len(s) > 20][:max_sentences]
            result = " ".join(kept) if kept else cleaned[:300]
            _persist_knowledge(f"wiki:{query[:60]}", result[:1000], source="wikipedia_api")
            return result

        return "No Wikipedia article found."
    except urllib.error.HTTPError as e:
        return f"Wikipedia API error (rate limited: {e.code}). Try again later."
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"


# Map tool names to functions
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
    "web_and_learn": tool_web_and_learn,
    "read_knowledge": tool_read_knowledge,
    "learn": tool_learn,
    "analyze_error": tool_analyze_error,
    "wikipedia": tool_wikipedia,
}

# ─── Intent Classification ──────────────────────────────────────────────────────
# Pure keyword + similarity matching. No ML. No vectors.

INTENT_PATTERNS = {
    "read_file": ["read file", "show file", "cat ", "open file", "view file", "display file", "what's in"],
    "write_file": ["create file", "write file", "make a file", "save file", "create a script", "generate"],
    "edit_line": ["edit line", "change line", "modify line", "update line"],
    "replace_text": ["replace", "find and replace", "substitute", "search and replace"],
    "append_file": ["append", "add to file", "add content", "add line"],
    "list_files": ["list files", "show files", "what files", "ls", "list directory", "dir", "what's here", "list in", "list what's"],
    "search_files": ["search files", "search for ", "find in files", "grep", "search text", "search code"],
    "find_files": ["find file", "find files", "find all", "locate file", "find by name", "glob", "find "],
    "run_command": ["run command", "run ", "execute", "run terminal", "build ", "compile ", "install ", "make "],
    "web_search": ["search web", "search internet", "look up", "find online", "google", "what is on the web"],
    "read_knowledge": ["what is", "how do i", "how does", "tell me about", "explain", "define", "meaning of"],
    "learn": ["remember this", "remember that ", "learn that ", "store that", "save this knowledge", "learn this"],
    "wikipedia": ["lookup ", "look up ", "wikipedia ", "what is on wikipedia", "search wikipedia", "find on wikipedia"],
}

def classify_intent(text, use_fuzzy=True):
    """Classify user intent using keyword + fuzzy matching.
    Three-phase: exact (fast) → normalized exact → normalized fuzzy."""
    text_lower = text.lower().strip()
    if not text_lower:
        return None, 0.0

    # Phase 1: Exact prefix match on original text (fast path, 0 extra cost)
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if text_lower.startswith(pattern.lower()):
                return intent, 1.0

    # Phase 1b: Exact substring match with scoring
    best_intent = None
    best_score = 0.0
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            pat_lower = pattern.lower()
            if pat_lower in text_lower:
                score = len(pat_lower) / max(len(text_lower), 1)
                if score > best_score:
                    best_score = score
                    best_intent = intent

    if best_score > 0.4:
        return best_intent, best_score

    if not use_fuzzy:
        if best_score > 0.3:
            return best_intent, best_score
        return None, 0.0

    # Phase 2: Normalize text and retry
    normalized, _ = normalize(text)
    if normalized != text_lower:
        # Retry exact prefix/substring on normalized text
        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                pat_lower = pattern.lower()
                if normalized.startswith(pat_lower):
                    return intent, 0.95
                if pat_lower in normalized:
                    score = len(pat_lower) / max(len(normalized), 1)
                    if score > best_score:
                        best_score = score
                        best_intent = intent

        if best_score > 0.4:
            return best_intent, best_score

    # Phase 3: Fuzzy match — compute difflib + ngram similarity for each pattern
    text_ngrams = set()
    for i in range(len(normalized) - 2):
        text_ngrams.add(normalized[i:i+3])

    text_words = set(re.findall(r'\w+', normalized))

    fuzzy_best_intent = None
    fuzzy_best_score = 0.0

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            pat = pattern.lower().strip()
            if len(pat) < 2:
                continue
            if len(pat) < 4 and normalized.find(pat) < 0:
                continue  # short patterns only match via exact substring

            # Combined fuzzy score
            ratio = difflib.SequenceMatcher(None, normalized, pat).ratio()

            pat_ngrams = set()
            for i in range(len(pat) - 2):
                pat_ngrams.add(pat[i:i+3])
            ngram_score = 0.0
            if text_ngrams and pat_ngrams:
                inter = text_ngrams & pat_ngrams
                union = text_ngrams | pat_ngrams
                ngram_score = len(inter) / max(len(union), 1)

            combined = max(ratio, ngram_score)

            # Boost if pattern keywords appear (exact or fuzzy) in text
            pat_words = set(re.findall(r'\w+', pat))
            if pat_words and text_words:
                exact_overlap = len(pat_words & text_words)
                fuzzy_overlap = 0
                for pw in pat_words:
                    if len(pw) < 3:
                        continue  # skip short stopword-like words
                    for tw in text_words:
                        dist = levenshtein(pw, tw)
                        max_dist = 1 if len(pw) <= 5 else 2
                        if dist <= max_dist:
                            fuzzy_overlap += 1
                            break
                word_hit = max(exact_overlap, fuzzy_overlap) / max(len([w for w in pat_words if len(w) >= 3]), 1)
                if word_hit >= 0.5:
                    boost = word_hit * 0.25 + 0.05
                    combined = max(combined, min(ratio + boost, 0.9))

            if combined > fuzzy_best_score:
                fuzzy_best_score = combined
                fuzzy_best_intent = intent

    if fuzzy_best_score >= 0.4:
        return fuzzy_best_intent, round(fuzzy_best_score, 2)

    # Final fallback: return best exact match even if low
    return best_intent if best_intent else None, best_score if best_intent else 0.0

# ─── Entity Extraction ──────────────────────────────────────────────────────────

PATH_PREFIXES = ["read ", "cat ", "show ", "list ", "dir ", "ls ",
                 "find ", "glob ", "search ", "grep ", "open ", "write ",
                 "edit ", "replace ", "append "]

def extract_search_pattern(text):
    """Extract search/find pattern, handling 'in <path>' suffix."""
    m = re.search(r'"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r"'([^']+)'", text)
    if m:
        return m.group(1)
    # Remove "in <path>" suffix
    text_no_path = re.sub(r'\s+in\s+\S+(\s*/\s*\S+)*\s*$', '', text, count=1)
    parts = text_no_path.split(None, 1)
    if len(parts) > 1:
        pat = parts[-1].strip()
        # Strip noise words
        for noise in ["files ", "file ", "for ", "all "]:
            if pat.startswith(noise):
                pat = pat[len(noise):].strip()
        if pat:
            return pat
    # Fallback: try normalized text for typo'd prefixes
    norm, _ = normalize(text)
    if norm != text.lower().strip():
        return extract_search_pattern(norm)
    return text

def extract_search_path(text, pattern=None):
    """Extract path from 'in <path>' suffix."""
    m = re.search(r'\s+in\s+(\S+(?:\s*/\s*\S+)*)\s*$', text)
    if m:
        p = os.path.expanduser(m.group(1).rstrip('/'))
        if os.path.exists(p) or '/' in p:
            return p
    # Fall back to original extract_path
    p = extract_path(text)
    if p and p != pattern and p != '.' and p != 'files' and os.path.exists(p):
        return p
    # Try to parse "in <path>" more loosely
    m2 = re.search(r'\b(in|from)\s+(\S+)', text)
    if m2:
        p = os.path.expanduser(m2.group(2).rstrip('/'))
        if os.path.exists(p):
            return p
    return None


def extract_path_from_in(text):
    """Extract path from 'in <path>' suffix or standalone path."""
    m = re.search(r'\s+in\s+(\S+(?:\s*/\s*\S+)*)\s*$', text)
    if m:
        p = os.path.expanduser(m.group(1).rstrip('/'))
        if os.path.exists(p) or '/' in p:
            return p
    return None

def extract_path(text):
    """Extract file path from natural language input."""
    stripped = text.strip()

    # Try original text first (exact match is best for paths)
    for prefix in PATH_PREFIXES:
        if stripped.lower().startswith(prefix):
            stripped = stripped[len(prefix):].strip()
            break
    else:
        # Try normalized text for typo'd prefixes ("listt" → "list")
        norm, _ = normalize(text)
        for prefix in PATH_PREFIXES:
            if norm.startswith(prefix):
                offset = text.lower().find(prefix.rstrip())
                if offset >= 0:
                    stripped = text[offset + len(prefix.rstrip()):].strip()
                    break

    candidates = re.findall(r'(?:^|\s)(/[^\s]+|~[^\s]*|\.\.?[^\s]+|[^\s]+\.[^\s]+)', stripped)
    if candidates:
        return os.path.expanduser(candidates[0])
    words = [w for w in stripped.split() if not w.startswith('-') and not w.startswith('"') and not w.startswith("'")]
    if words:
        return os.path.expanduser(words[0])
    return None

def extract_pattern(text):
    """Extract search pattern from input."""
    m = re.search(r'"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(r"'([^']+)'", text)
    if m:
        return m.group(1)
    parts = text.split(None, 1)
    if len(parts) > 1:
        return parts[-1].strip()
    return text

def extract_line_number(text):
    m = re.search(r'line\s+(\d+)', text, re.I)
    if m:
        return int(m.group(1))
    return None

def extract_command(text):
    t = text.lower().strip()
    known_prefixes = ["run ", "execute ", "run command "]

    for prefix in known_prefixes:
        p = prefix.strip()
        if t.startswith(prefix.lower()):
            return text[len(prefix):].strip()

    # Fuzzy: scan for prefix words anywhere in text
    for prefix in known_prefixes:
        p = prefix.strip()
        first_prefix_word = p.split()[0] if p.split() else ""
        if not first_prefix_word:
            continue
        # Find the prefix word in the text (fuzzy)
        words = t.split()
        for i, w in enumerate(words):
            dist = levenshtein(w, first_prefix_word)
            max_dist = max(1, len(first_prefix_word) // 3)
            if dist <= max_dist:
                # Found it — return everything after it
                char_offset = t.find(w)
                if char_offset >= 0:
                    rest = text[char_offset + len(w):].strip()
                    if rest:
                        return rest
                    # If nothing after, return the rest of words
                    remaining = " ".join(words[i+1:])
                    if remaining:
                        return remaining

    return text

def extract_entities(text, intent):
    """Extract parameters from natural language based on intent."""
    entities = {}
    if intent == "read_file":
        entities["path"] = extract_path(text) or "."
    elif intent == "list_files":
        p = extract_path_from_in(text) or extract_path(text)
        entities["path"] = p if (p and os.path.exists(p)) else "."
    elif intent == "write_file":
        entities["content"] = text
        path = extract_path(text)
        if path:
            entities["path"] = path
    elif intent == "edit_line":
        entities["path"] = extract_path(text) or "."
        entities["line"] = extract_line_number(text) or 1
        entities["content"] = text
    elif intent == "replace_text":
        entities["path"] = extract_path(text) or "."
        m = re.search(r'"([^"]+)"\s+"([^"]+)"', text)
        if m:
            entities["old"] = m.group(1)
            entities["new"] = m.group(2)
    elif intent == "append_file":
        entities["path"] = extract_path(text) or "."
        entities["content"] = text
    elif intent == "search_files":
        entities["pattern"] = extract_search_pattern(text)
        entities["path"] = extract_search_path(text, entities["pattern"]) or "."
    elif intent == "find_files":
        entities["pattern"] = extract_search_pattern(text)
        entities["path"] = extract_search_path(text, entities["pattern"]) or "."
    elif intent == "run_command":
        entities["command"] = extract_command(text)
    elif intent == "web_search":
        entities["query"] = text
    elif intent == "wikipedia":
        query = text.lower().strip()
        for prefix in ["lookup ", "look up ", "wikipedia ", "what is on wikipedia ", "search wikipedia ", "find on wikipedia "]:
            if query.startswith(prefix):
                entities["query"] = text[len(prefix):].strip()
                break
        if "query" not in entities:
            entities["query"] = text
    elif intent == "read_knowledge":
        entities["query"] = text
    elif intent == "learn":
        # Pattern: learn/remember <something> that <solution>
        # Or: learn/remember that <solution> (problem = same query for later use)
        parts = text.split(" that ", 1)
        if len(parts) > 1:
            problem_part = parts[0].replace("remember", "").replace("learn", "").replace("that", "").strip()
            if problem_part:
                entities["problem"] = problem_part
            else:
                # "remember that X" — use first meaningful word as problem hint
                hint = parts[1].strip()[:40]
                entities["problem"] = hint
            entities["solution"] = parts[1].strip()
        else:
            entities["problem"] = text.replace("remember", "").replace("learn", "").strip()
            entities["solution"] = text.replace("remember", "").replace("learn", "").strip()
    return entities

# ─── Planning ───────────────────────────────────────────────────────────────────

def build_plan(intent, entities, text):
    """Build a plan: list of (tool, params) steps to execute."""
    if intent is None:
        # Unknown intent → use layered approach
        return [{"tool": "read_knowledge", "params": {"query": text}}]

    plans = {
        "read_file": [{"tool": "read_file", "params": entities}],
        "write_file": [{"tool": "write_file", "params": entities}],
        "edit_line": [{"tool": "edit_line", "params": entities}],
        "replace_text": [{"tool": "replace_text", "params": entities}],
        "append_file": [{"tool": "append_file", "params": entities}],
        "list_files": [{"tool": "list_files", "params": entities}],
        "search_files": [{"tool": "search_files", "params": entities}],
        "find_files": [{"tool": "find_files", "params": entities}],
        "run_command": [{"tool": "run_command", "params": entities}],
        "web_search": [{"tool": "web_search", "params": entities}],
        "read_knowledge": [{"tool": "read_knowledge", "params": entities}],
        "learn": [{"tool": "learn", "params": entities}],
        "wikipedia": [{"tool": "wikipedia", "params": entities}],
    }
    return plans.get(intent, [{"tool": "read_knowledge", "params": {"query": text}}])

# ─── Workflow System ────────────────────────────────────────────────────────────

def load_workflows():
    """Load all workflow JSON files."""
    workflows = {}
    if os.path.isdir(WORKFLOWS_DIR):
        for fname in os.listdir(WORKFLOWS_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(WORKFLOWS_DIR, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    key = fname.replace(".json", "")
                    workflows[key] = data
                except Exception as e:
                    pass
    return workflows

def match_workflow(text, workflows):
    """Find a workflow matching the input text."""
    text_lower = text.lower().strip()
    for name, workflow in workflows.items():
        triggers = workflow.get("triggers", [])
        for trigger in triggers:
            if trigger.lower() in text_lower or text_lower.startswith(trigger.lower()):
                return workflow
    return None

def _alternatives(failed_approach, problem_text, error_info=None):
    """Generate alternative approaches when one fails."""
    alts = []

    # If error info is available, derive alternatives from it
    if error_info and error_info.get("suggested_query"):
        alts.append({
            "tool": "web_and_learn",
            "params": {"query": error_info["suggested_query"]},
            "reason": f"Searching web for: {error_info['suggested_query']}"
        })

    # If it was a read_file, try search_files
    if failed_approach == "read_file":
        alts.append({
            "tool": "search_files",
            "params": {"pattern": problem_text, "path": "."},
            "reason": "File not found, searching for content"
        })

    # If it was run_command, try with different shell
    if failed_approach == "run_command":
        alts.append({
            "tool": "read_knowledge",
            "params": {"query": problem_text},
            "reason": "Looking up similar command in knowledge"
        })

    # If it was read_knowledge, try web
    if failed_approach == "read_knowledge" or failed_approach == "recall":
        alts.append({
            "tool": "web_and_learn",
            "params": {"query": problem_text},
            "reason": "Knowledge search failed, checking web"
        })

    # If it was search_files, try find_files
    if failed_approach == "search_files":
        keywords = [w for w in re.findall(r'\w+', problem_text) if w not in STOPWORDS and len(w) > 2]
        if keywords:
            alts.append({
                "tool": "find_files",
                "params": {"pattern": f"*{keywords[0]}*", "path": "."},
                "reason": f"Searching for files matching '{keywords[0]}'"
            })

    # Generic fallback: web search for the problem
    alts.append({
        "tool": "web_and_learn",
        "params": {"query": problem_text},
        "reason": "Attempting web search as fallback"
    })

    return alts


# ─── Execution Layers (Ultra Mode) ─────────────────────────────────────────────

def execute_tool(tool, params):
    """Execute a single tool with ethics check."""
    allowed, reason = check_constitution(tool, params)
    if not allowed:
        return {"tool": tool, "status": "blocked", "reason": reason}

    impl = TOOLS.get(tool)
    if not impl:
        return {"tool": tool, "status": "error", "reason": f"Unknown tool: {tool}"}

    try:
        result = impl(**params)
        return {"tool": tool, "status": "ok", "result": result}
    except Exception as e:
        return {"tool": tool, "status": "error", "reason": str(e)}


def layer_react(intent, entities, text, workflows):
    """Layer 1: Match known patterns and execute immediately."""
    if intent:
        plan = build_plan(intent, entities, text)
        results = []
        for step in plan:
            results.append(execute_tool(step["tool"], step["params"]))
        return results

    workflow = match_workflow(text, workflows)
    if workflow:
        steps = workflow.get("steps", [])
        results = []
        for step in steps:
            tool = step.get("tool")
            params = step.get("params", {})
            results.append(execute_tool(tool, params))
        return results

    return None


def layer_think(text, intent, entities, tone):
    """Layer 2: Reason about the problem, generate multi-pronged plan."""
    thought_log = []
    thought_log.append(f"Problem: {text[:80]}")

    # Decomposition
    if intent:
        thought_log.append(f"Identified intent: {intent}")
        if entities:
            thought_log.append(f"Entities: { {k: str(v)[:30] for k, v in entities.items()} }")
    else:
        thought_log.append("Intent unclear — will explore multiple approaches")
        thought_log.append("Strategy: knowledge search → file search → web search")

    # Generate the execution plan with alternatives
    plan = []
    primary_tool = None
    primary_params = {}

    if intent == "read_knowledge" or intent is None:
        primary_tool = "read_knowledge"
        primary_params = {"query": text}
        plan.append(("knowledge_lookup", "read_knowledge", {"query": text}))
        plan.append(("alternative_web", "web_and_learn", {"query": text}))
    elif intent == "run_command":
        primary_tool = "run_command"
        primary_params = {"command": entities.get("command", text)}
        plan.append(("execute_command", "run_command", {"command": entities.get("command", text)}))
    elif intent == "search_files":
        plan.append(("search_files", "search_files", {"pattern": entities.get("pattern", text), "path": entities.get("path", ".")}))
        plan.append(("find_by_keywords", "find_files", {"pattern": "*", "path": entities.get("path", ".")}))
    elif intent == "find_files":
        plan.append(("find_files", "find_files", {"pattern": entities.get("pattern", text), "path": entities.get("path", ".")}))
        plan.append(("search_content", "search_files", {"pattern": entities.get("pattern", text), "path": entities.get("path", ".")}))
    elif intent == "web_search":
        plan.append(("web_search", "web_and_learn", {"query": text}))
    elif intent == "wikipedia":
        plan.append(("wikipedia_lookup", "wikipedia", {"query": entities.get("query", text)}))
        plan.append(("fallback_web", "web_and_learn", {"query": text}))
    elif intent == "learn":
        plan.append(("learn", "learn", {"problem": entities.get("problem", text), "solution": entities.get("solution", text)}))
    elif intent == "list_files":
        plan.append(("list_dir", "list_files", {"path": entities.get("path", ".")}))
    elif intent == "read_file":
        plan.append(("read_file", "read_file", {"path": entities.get("path", ".")}))
    elif intent == "write_file":
        plan.append(("write_file", "write_file", {"path": entities.get("path", ""), "content": entities.get("content", text)}))
    else:
        # Generic fallback plan
        plan.append(("knowledge_search", "read_knowledge", {"query": text}))
        plan.append(("file_search", "search_files", {"pattern": text, "path": "."}))
        plan.append(("web_research", "web_and_learn", {"query": text}))

    return plan, thought_log


def layer_routine(intent, entities, text):
    """Layer 3: Execute primary plan, with error analysis + recovery."""
    plan, thought_log = layer_think(text, intent, entities, {})
    results = []
    attempts = []

    for step_name, tool, params in plan:
        r = execute_tool(tool, params)
        r["step_name"] = step_name
        results.append(r)

        if r["status"] == "ok" and r.get("result") and len(str(r["result"])) > 3:
            # Success! Persist what worked
            if tool not in ("list_files", "run_command"):
                try:
                    _persist_knowledge(
                        f"resolved:{text[:60]}",
                        f"tool={tool}, result={str(r['result'])[:200]}",
                        source="successful_execution"
                    )
                except Exception:
                    pass
            return results

        # Error analysis for failed attempts
        if r["status"] in ("error", "blocked") or (r["status"] == "ok" and len(str(r.get("result", ""))) <= 3):
            error_text = r.get("reason", r.get("result", ""))
            error_info = tool_analyze_error(str(error_text))
            attempts.append({"tool": tool, "error": error_text, "analysis": error_info})

            # Generate and try alternatives
            alts = _alternatives(tool, text, error_info)
            for alt in alts:
                if len(results) > 8:  # Cap total attempts
                    break
                r2 = execute_tool(alt["tool"], alt["params"])
                r2["step_name"] = f"alt_{alt['tool']}"
                results.append(r2)
                if r2["status"] == "ok" and r2.get("result") and len(str(r2["result"])) > 3:
                    # Auto-learn from success
                    try:
                        _persist_knowledge(
                            f"resolved:{text[:60]}",
                            f"approach={alt['tool']}: {str(r2['result'])[:200]}",
                            source="alternative_execution"
                        )
                    except Exception:
                        pass
                    return results

    return results


def layer_explore(intent, entities, text):
    """Layer 4: Deep search — project files + learned memory + analyze."""
    results = []

    # Full-text search across project
    r = execute_tool("search_files", {"pattern": text, "path": "."})
    r["step_name"] = "project_search"
    results.append(r)

    # Search with key terms from the query
    keywords = [w for w in re.findall(r'\w+', text.lower()) if w not in STOPWORDS and len(w) > 3]
    for kw in keywords[:3]:
        r2 = execute_tool("search_files", {"pattern": kw, "path": "."})
        r2["step_name"] = f"keyword_search:{kw}"
        results.append(r2)

    # Check learned memory
    memory_file = os.path.join(MEMORY_DIR, "learned.json")
    if os.path.exists(memory_file):
        try:
            with open(memory_file) as f:
                memory = json.load(f)
            # Find matching entries in learned memory
            text_lower = text.lower()
            for key, entry in memory.items():
                if any(w in key.lower() for w in keywords) or any(w in entry.get("solution", "").lower() for w in keywords):
                    results.append({
                        "tool": "read_knowledge",
                        "status": "ok",
                        "result": f"[Learned] {key}: {entry.get('solution', '')[:200]}",
                        "step_name": "learned_memory"
                    })
                    break
        except Exception:
            pass

    return results


def layer_internet(text):
    """Layer 5: Web research with auto-learning."""
    results = []

    # Primary web search
    r = execute_tool("web_and_learn", {"query": text})
    r["step_name"] = "web_primary"
    results.append(r)

    # If no results, try with key terms
    if "No web results" in str(r.get("result", "")) or "unavailable" in str(r.get("result", "")):
        keywords = [w for w in re.findall(r'\w+', text) if w not in STOPWORDS and len(w) > 3]
        if keywords:
            kw_query = " ".join(keywords[:4])
            r2 = execute_tool("web_and_learn", {"query": kw_query})
            r2["step_name"] = "web_keywords"
            results.append(r2)

    return results


def layer_report(intent, text, all_results, tone=None):
    """Layer 6: Diagnostic report with what was tried and what's next."""
    report_parts = []

    # Summary
    successes = [r for r in all_results if r.get("status") == "ok" and r.get("result")]
    failures = [r for r in all_results if r.get("status") in ("error", "blocked")]
    report_parts.append(f"Analysis for: {text[:80]}")
    report_parts.append(f"Tried {len(all_results)} approaches ({len(successes)} succeeded, {len(failures)} failed)")

    # What succeeded
    if successes:
        report_parts.append("\nWhat worked:")
        for r in successes[:3]:
            step = r.get("step_name", r.get("tool", "?"))
            result = str(r.get("result", ""))[:100]
            report_parts.append(f"  [{step}] {result}")

    # What failed and why
    if failures:
        report_parts.append("\nWhat failed:")
        for r in failures[:3]:
            tool = r.get("tool", "?")
            reason = str(r.get("reason", "no output"))[:80]
            report_parts.append(f"  [{tool}] {reason}")

    # Suggestions based on what was learned
    report_parts.append("\nSuggestions:")
    if intent:
        report_parts.append(f"- Try rephrasing the {intent} request")
    else:
        report_parts.append("- Be more specific about what you want")
    report_parts.append("- Use /help for available commands")

    # If knowledge was found from web, offer to apply it
    for r in all_results:
        if r.get("tool") == "web_and_learn" and r.get("status") == "ok":
            result = str(r.get("result", ""))
            if len(result) > 20:
                report_parts.append(f"\nWeb research found: {result[:200]}")
                break

    return "\n".join(report_parts)


# ─── Main Processing Loop (Ultra Mode) ─────────────────────────────────────────

def result_has_content(r, min_len=4):
    """Check if a result dict has useful content."""
    return (r.get("status") == "ok"
            and r.get("result")
            and len(str(r.get("result", ""))) > min_len)


def find_best_result(results, exclude_tools=None):
    """Find the first result with actual useful content, optionally excluding tools."""
    if exclude_tools is None:
        exclude_tools = set()
    for r in results:
        if r.get("tool") in exclude_tools:
            continue
        if result_has_content(r):
            return r
    return None


def process(text):
    """Ultra processing: recursive solve loop with error analysis, alternatives, web learning."""
    if not text or not text.strip():
        return "No input received."

    # Step 0: Normalize
    normalized, original = normalize(text)
    input_for_classify = normalized if normalized != original.lower().strip() else original
    tone = detect_tone(original)
    workflows = load_workflows()

    # Try multi-step planner first (handles complex tasks with recipes)
    try:
        from qwerty_agent.planner import plan_and_execute, explore
        plan_result = plan_and_execute(original)
        if plan_result is not None:
            return plan_result
    except Exception:
        pass

    # Classify intent
    intent, confidence = classify_intent(input_for_classify)
    entities = extract_entities(original, intent)

    # Try Genius neural engine for knowledge queries (feels more LLM-like)
    if HAS_GENIUS and intent in (None, "read_knowledge"):
        try:
            genius_result = genius_respond(original)
            if genius_result and len(genius_result) > 30:
                return genius_result
        except Exception:
            pass

    all_results = []
    max_iterations = 3

    for iteration in range(max_iterations):
        # Track what we've tried so far
        tried_tools = {r.get("tool") for r in all_results}

        # Layer 1: React (fast path)
        if iteration == 0:
            results = layer_react(intent, entities, original, workflows)
            if results:
                all_results.extend(results)
                best = find_best_result(results, exclude_tools={"list_files"})
                if best:
                    # If success, persist and return
                    if best["tool"] not in ("run_command", "list_files", "write_file", "edit_line"):
                        _persist_knowledge(
                            f"resolved:{original[:60]}",
                            f"react: {str(best['result'])[:200]}",
                            source="layer_react"
                        )
                    return format_response([best], intent, original, tone)

        # Layer 2: Think + Routine (plan + execute with alternatives)
        plan, thought_log = layer_think(original, intent, entities, tone)
        results = []
        for step_name, tool, params in plan:
            if tool in tried_tools:
                continue  # Don't repeat failed approaches
            r = execute_tool(tool, params)
            r["step_name"] = step_name
            results.append(r)
            tried_tools.add(tool)

            if result_has_content(r):
                # Success! Persist and return
                _persist_knowledge(
                    f"resolved:{original[:60]}",
                    f"{step_name}: {str(r['result'])[:200]}",
                    source="layer_routine"
                )
                all_results.extend(results)
                return format_response([r], intent, original, tone)

            # Error analysis + alternatives
            if r["status"] in ("error", "blocked") or not result_has_content(r):
                error_text = r.get("reason", r.get("result", ""))
                error_info = tool_analyze_error(str(error_text))
                alts = _alternatives(tool, original, error_info)

                for alt in alts:
                    if alt["tool"] in tried_tools or len(results) > 10:
                        continue
                    r2 = execute_tool(alt["tool"], alt["params"])
                    r2["step_name"] = f"alt:{alt['tool']}"
                    results.append(r2)
                    tried_tools.add(alt["tool"])

                    if result_has_content(r2):
                        _persist_knowledge(
                            f"resolved:{original[:60]}",
                            f"alt_{alt['tool']}: {str(r2['result'])[:200]}",
                            source="layer_alternatives"
                        )
                        all_results.extend(results)
                        return format_response([r2], intent, original, tone)

        all_results.extend(results)

        # Layer 3: Explore (deep project search + memory)
        if iteration <= 1:
            results = layer_explore(intent, entities, original)
            if results:
                all_results.extend(results)
                best = find_best_result(results)
                if best:
                    return format_response([best], intent, original, tone)

        # Layer 4: Internet (web research + auto-learn)
        results = layer_internet(original)
        if results:
            all_results.extend(results)
            best = find_best_result(results)
            if best:
                # Web found something — return it AND store for next time
                return f"[Web Research]\n{best['result']}"

        # Layer 5: If we failed, try one more time with the original text as web query
        if iteration == max_iterations - 1:
            r = execute_tool("web_and_learn", {"query": original})
            r["step_name"] = "final_web_attempt"
            all_results.append(r)
            if result_has_content(r):
                return f"[Web Research]\n{r['result']}"

    # Final fallback: explore across all sources
    try:
        from qwerty_agent.planner import explore
        explore_result = explore(original)
        if explore_result:
            return explore_result
    except Exception:
        pass

    # Everything failed — detailed diagnostic report
    return layer_report(intent, original, all_results, tone)


def format_response(results, intent, original_text, tone=None):
    """Format execution results into a readable response."""
    outputs = []
    for r in results:
        if r.get("status") == "blocked":
            return f"[Blocked] {r['reason']}"
        if r.get("status") == "error":
            return f"Error: {r['reason']}"
        if r.get("status") == "ok":
            result = r.get("result", "")
            if result:
                outputs.append(result)

    if outputs:
        result_text = "\n".join(outputs)
        return result_text

    return "Done. No output."

# ─── Interactive REPL ──────────────────────────────────────────────────────────

def repl():
    """Run interactive prompt loop."""
    print(f"{IDENTITY.get('name', 'Qwerty')} v2 — {IDENTITY.get('purpose', 'Autonomous Agent')}")
    print(f"Constitution: {len(RULES)} rules. Tools: {len(TOOLS)} available.")
    print(f"Layers: {', '.join(l['name'] for l in LAYERS)}")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            text = input("> ").strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit", "/exit", "/quit"):
                break
            if text.lower() in ("help", "/help"):
                print("Commands:")
                for intent, patterns in sorted(INTENT_PATTERNS.items()):
                    print(f"  {intent}: e.g. '{patterns[0]}'")
                print("  exit: quit\n")
                continue

            result = process(text)
            print(result)
            print()
        except KeyboardInterrupt:
            print("\nBye.")
            break
        except Exception as e:
            print(f"Error: {e}")

# ─── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result = process(text)
        print(result)
    else:
        repl()

if __name__ == "__main__":
    main()
