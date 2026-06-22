"""Comprehensive tests for Qwerty v2. Zero external dependencies."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import (
    normalize, levenshtein, ngram_jaccard, fuzzy_word,
    detect_tone, recall, classify_intent, extract_entities,
    extract_path, extract_command, extract_pattern, extract_line_number,
    extract_search_pattern, extract_search_path,
    tool_analyze_error, check_constitution, build_plan, execute_tool,
    _meaningful, _match_key, _persist_knowledge, MEMORY_DIR,
    load_knowledge, load_constitution, RULES, AUTHORIZED_TOOLS,
    process, format_response, layer_report, tool_read_file,
    tool_write_file, tool_run_command, tool_find_files,
    TOOLS,
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))

def test_normalize():
    print("\n=== normalize() ===")
    # Shorthand expansion
    t, _ = normalize("plz tell me wat uefi is")
    check("shorthand: plz → please", "please" in t)
    check("shorthand: wat → what", "what" in t)
    # Contractions
    t, _ = normalize("dont go to the store")
    check("contractions: dont → do not", "do not" in t)
    t, _ = normalize("im gonna leave")
    check("contractions: gonna → going to", "going to" in t)
    # Character dedup
    t, _ = normalize("hellooo")
    check("dedup vowels: hellooo → hello", t == "hello")
    t, _ = normalize("ruuun")
    check("dedup consonants: ruuun → ruun", "uu" not in t)
    # Punctuation
    t, _ = normalize("what???")
    check("excess punct: ??? → ?", "?" in t and "??" not in t)
    # Empty/edge
    t, _ = normalize("")
    check("empty string", t == "")
    t, _ = normalize("   ")
    check("whitespace only", t[0] if t else True)
    # Long shorthand
    t, _ = normalize("idk tbh afaik")
    check("shorthand chain", "i do not know" in t and "to be honest" in t)

def test_levenshtein():
    print("\n=== levenshtein() ===")
    check("same string", levenshtein("hello", "hello") == 0)
    check("one insertion", levenshtein("cat", "cats") == 1)
    check("one deletion", levenshtein("cats", "cat") == 1)
    check("one substitution", levenshtein("cat", "cut") == 1)
    check("completely different", levenshtein("abc", "xyz") == 3)
    check("empty vs non-empty", levenshtein("", "abc") == 3)
    check("both empty", levenshtein("", "") == 0)
    check("kernul → kernel", levenshtein("kernul", "kernel") == 1)
    check("filles → files", levenshtein("filles", "files") == 1)

def test_ngram_jaccard():
    print("\n=== ngram_jaccard() ===")
    check("identical", ngram_jaccard("kernel", "kernel") > 0.99)
    check("kernul vs kernel", ngram_jaccard("kernul", "kernel") > 0.3)
    check("completely different", ngram_jaccard("abc", "xyz") < 0.2)
    check("empty strings", ngram_jaccard("", "hello") == 0.0)

def test_fuzzy_word():
    print("\n=== fuzzy_word() ===")
    vocab = ["kernel", "memory", "process", "filesystem", "driver"]
    match, dist = fuzzy_word("kernul", vocab)
    check("kernul → kernel", match == "kernel" and dist == 1)
    match, dist = fuzzy_word("drivr", vocab)
    check("drivr → driver", match == "driver" and dist == 1)

def test_detect_tone():
    print("\n=== detect_tone() ===")
    tone = detect_tone("What is UEFI?")
    check("question detection", tone["question"] is True)
    tone = detect_tone("FIX THIS NOW")
    check("frustration detection", tone["frustrated"] is True)
    tone = detect_tone("plz help")
    check("casual detection", tone["casual"] is True)

def test_recall():
    print("\n=== recall() ===")
    # Exact match
    result = recall("Who is Qwerty?")
    check("exact recall returns results", result is not None and len(result) > 0)
    # Fuzzy match
    result = recall("kernul")
    check("fuzzy recall 'kernul'", len(result) > 0)

def test_classify_intent():
    print("\n=== classify_intent() ===")
    intent, conf = classify_intent("list files")
    check("list files intent", intent == "list_files" and conf > 0.9)
    intent, conf = classify_intent("what is UEFI")
    check("read_knowledge intent", intent == "read_knowledge")
    intent, conf = classify_intent("runn ls -la")
    check("run_command with typo", intent == "run_command" and conf > 0.3)
    intent, conf = classify_intent("")
    check("empty input", conf == 0.0 and intent is None)

def test_extract_entities():
    print("\n=== extract_entities() ===")
    entities = extract_entities("read_file /etc/hostname", "read_file")
    check("read_file path", entities.get("path") is not None)
    entities = extract_entities("run_command ls -la", "run_command")
    check("run_command extraction", "ls" in entities.get("command", ""))
    entities = extract_entities("learn that kernel panics are bad", "learn")
    check("learn entity", "problem" in entities)

def test_tool_analyze_error():
    print("\n=== tool_analyze_error() ===")
    # Compilation error
    result = tool_analyze_error("error[E0308]: mismatched types\n  --> src/main.rs:10:5")
    check("compilation error type", result["error_type"] == "compilation")
    check("error code extracted", "e0308" in result["key_terms"])
    check("file extracted", "src/main.rs" in result["files"])
    # Runtime error
    result = tool_analyze_error("Traceback (most recent call last):\n  File \"test.py\", line 5, in <module>\nZeroDivisionError: division by zero")
    check("runtime error type", result["error_type"] == "runtime")
    # Command not found
    result = tool_analyze_error("bash: foo: command not found")
    check("missing command type", result["error_type"] == "missing_command")
    # Empty input
    result = tool_analyze_error("")
    check("empty input error", result["error_type"] == "unknown")
    result = tool_analyze_error("ok")
    check("short input error", result["error_type"] == "unknown")

def test_constitution():
    print("\n=== check_constitution() ===")
    allowed, reason = check_constitution("run_command", {"command": "ls -la"})
    check("safe command allowed", allowed is True)
    allowed, reason = check_constitution("run_command", {"command": "rm -rf /"})
    check("dangerous command blocked", allowed is False and "r002" in reason)
    allowed, reason = check_constitution("write_file", {"path": "/nonexistent/test.txt", "content": "hello"})
    check("write new file allowed", allowed is True)
    allowed, reason = check_constitution("unknown_tool")
    check("unknown tool blocked", allowed is False)

def test_build_plan():
    print("\n=== build_plan() ===")
    plan = build_plan("read_file", {"path": "/tmp/test"}, "read /tmp/test")
    check("read_file plan", len(plan) == 1 and plan[0]["tool"] == "read_file")
    plan = build_plan(None, {}, "random stuff")
    check("none intent fallback", len(plan) == 1 and plan[0]["tool"] == "read_knowledge")

def test_persist_knowledge():
    print("\n=== _persist_knowledge() ===")
    result = _persist_knowledge("test_problem", "test_solution", "unit_test")
    check("persist returns true", result is True)
    memory_file = os.path.join(MEMORY_DIR, "learned.json")
    if os.path.exists(memory_file):
        with open(memory_file) as f:
            data = json.load(f)
        check("persist stored entry", "test_problem" in data)
        check("persist solution correct", data["test_problem"]["solution"] == "test_solution")
        # Clean up after
        if "test_problem" in data:
            del data["test_problem"]
        with open(memory_file, 'w') as f:
            json.dump(data, f, indent=2)

def test_tools():
    print("\n=== tools (basic) ===")
    # read_file on an existing file
    result = tool_read_file(os.path.join(os.path.dirname(__file__), "__init__.py"))
    check("read_file exists", result is not None)
    # read_file on nonexistent file
    result = tool_read_file("/nonexistent_file_12345")
    check("read_file nonexistent", "Error" in result or result is None)
    # write_file to temp location
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        tmppath = f.name
    result = tool_write_file(tmppath, "hello world")
    check("write_file returns success", "Written" in str(result))
    os.unlink(tmppath)
    # find_files
    result = tool_find_files("*.py", path=os.path.dirname(__file__))
    check("find_files returns something", result is not None and len(result) > 0)
    result = tool_find_files("__init__.py", path=os.path.dirname(__file__))
    check("find_files specific", "__init__.py" in str(result))

def test_layer_report():
    print("\n=== layer_report() ===")
    results = [
        {"tool": "read_knowledge", "status": "ok", "result": "Hello", "step_name": "knowledge"},
        {"tool": "web_search", "status": "error", "reason": "connect failed", "step_name": "web"},
    ]
    report = layer_report("read_knowledge", "test query", results)
    check("report lists attempts", "Tried" in report)
    check("report shows successes", "What worked" in report)
    check("report shows failures", "What failed" in report)

def test_end_to_end():
    print("\n=== process() end-to-end ===")
    # Knowledge query
    result = process("what is a kernel")
    check("knowledge query returns", result is not None and len(str(result)) > 10)
    # Empty input
    result = process("")
    check("empty input handled", "No input" in str(result))
    result = process("   ")
    check("whitespace input handled", "No input" in str(result))

def test_load_knowledge():
    print("\n=== load_knowledge() ===")
    knowledge = load_knowledge()
    check("knowledge is dict", isinstance(knowledge, dict))
    check("has multiple domains", len(knowledge) >= 8)
    for domain in ["osdev", "rust", "personality", "programming", "linux", "git", "science", "general"]:
        check(f"domain exists: {domain}", domain in knowledge)

def test_load_constitution():
    print("\n=== load_constitution() ===")
    constitution = load_constitution()
    check("constitution has rules", len(constitution.get("rules", [])) >= 8)
    check("constitution has authorized tools", len(constitution.get("authorized_tools", [])) >= 10)

if __name__ == "__main__":
    test_load_knowledge()
    test_load_constitution()
    test_normalize()
    test_levenshtein()
    test_ngram_jaccard()
    test_fuzzy_word()
    test_detect_tone()
    test_recall()
    test_classify_intent()
    test_extract_entities()
    test_tool_analyze_error()
    test_constitution()
    test_build_plan()
    test_persist_knowledge()
    test_tools()
    test_layer_report()
    test_end_to_end()

    total = PASS + FAIL
    print(f"\n{'='*40}")
    print(f"Results: {PASS}/{total} passed, {FAIL}/{total} failed")
    sys.exit(0 if FAIL == 0 else 1)
