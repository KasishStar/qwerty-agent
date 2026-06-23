"""
Qwerty v3 — Test Suite
Tests: normalize, levenshtein, tools, constitution, brain (if available)
"""

import json
import os
import sys
import tempfile
from agent import (
    normalize, levenshtein, ngram_jaccard, fuzzy_word, char_ngrams,
    check_constitution, TOOLS,
)

PASS = 0
FAIL = 0

def test(name, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")

suite = ""

# ─── normalize() ───────────────────────────────────────────────
suite = "normalize"
print(f"\n=== {suite} ===")

n, o = normalize("hello")
test("identity", n == "hello")

n, o = normalize("wht is a kernul")
test("shorthand expansion", "what" in n)

n, o = normalize("idk the answer")
test("common shorthand", "i do not know" in n)

n, o = normalize("Im gonna build it")
test("contraction expansion", "i am" in n and "going to" in n)

n, o = normalize("")
test("empty string", n == "" and o == "")

n, o = normalize("Hello!!!")
test("excess punctuation collapsed", n == "hello?")

# ─── levenshtein() ─────────────────────────────────────────────
suite = "levenshtein"
print(f"\n=== {suite} ===")

test("identical", levenshtein("kernel", "kernel") == 0)
test("one subst", levenshtein("kernul", "kernel") == 1)
test("one insert", levenshtein("kernl", "kernel") == 1)
test("completely different", levenshtein("abc", "xyz") == 3)
test("empty vs non-empty", levenshtein("", "abc") == 3)
test("both empty", levenshtein("", "") == 0)

# ─── ngram_jaccard() ───────────────────────────────────────────
suite = "ngram_jaccard"
print(f"\n=== {suite} ===")

test("identical", ngram_jaccard("kernel", "kernel") > 0.9)
test("similar", ngram_jaccard("kernul", "kernel") > 0.3)
test("different", ngram_jaccard("abc", "xyz") < 0.3)
test("both empty", ngram_jaccard("", "") == 0.0)

# ─── fuzzy_word() ──────────────────────────────────────────────
suite = "fuzzy_word"
print(f"\n=== {suite} ===")

vocab = ["kernel", "memory", "process", "file", "system"]
w, d = fuzzy_word("kernul", vocab)
test("fuzzy match", w == "kernel")
w, d = fuzzy_word("memory", vocab)
test("exact match", w == "memory" and d == 0)
w, d = fuzzy_word("xyzzz", vocab)
test("no match", w == "xyzzz")

# ─── char_ngrams() ─────────────────────────────────────────────
suite = "char_ngrams"
print(f"\n=== {suite} ===")

ng = char_ngrams("abc", 2)
test("2-grams length", len(ng) == 2)
test("2-grams content", "ab" in ng and "bc" in ng)
test("empty", len(char_ngrams("", 3)) == 0)

# ─── check_constitution() ──────────────────────────────────────
suite = "check_constitution"
print(f"\n=== {suite} ===")

ok, _ = check_constitution("run_command", {"command": "ls -la"})
test("allowed command", ok)

ok, _ = check_constitution("run_command", {"command": "rm -rf /"})
test("blocks rm -rf /", not ok)

ok, _ = check_constitution("list_files", {})
test("allowed tool", ok)

ok, _ = check_constitution("nonexistent_tool", {})
test("blocks unknown tool", not ok)

# ─── Tools ─────────────────────────────────────────────────────
suite = "tools"
print(f"\n=== {suite} ===")

test("read_file in TOOLS", "read_file" in TOOLS)
test("write_file in TOOLS", "write_file" in TOOLS)
test("run_command in TOOLS", "run_command" in TOOLS)
test("web_search in TOOLS", "web_search" in TOOLS)
test("wikipedia in TOOLS", "wikipedia" in TOOLS)
test("learn in TOOLS", "learn" in TOOLS)
test("list_files in TOOLS", "list_files" in TOOLS)
test("search_files in TOOLS", "search_files" in TOOLS)
test("find_files in TOOLS", "find_files" in TOOLS)
test("edit_line in TOOLS", "edit_line" in TOOLS)
test("replace_text in TOOLS", "replace_text" in TOOLS)
test("append_file in TOOLS", "append_file" in TOOLS)

# Tool execution tests
result = TOOLS["list_files"]()
test("list_files returns string", isinstance(result, str))

with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write("hello world")
    tmpname = f.name

result = TOOLS["read_file"](tmpname)
test("read_file reads content", "hello" in result)

result = TOOLS["find_files"]("*.txt", path=os.path.dirname(tmpname))
test("find_files finds test file", os.path.basename(tmpname) in result)

os.unlink(tmpname)

test("read_file nonexistent returns error", "Error" in TOOLS["read_file"]("/nonexistent/path"))

# ─── process() ─────────────────────────────────────────────────
suite = "process()"
print(f"\n=== {suite} ===")

from agent import process

result = process("")
test("empty input handled", result is not None)
result = process("   ")
test("whitespace input handled", result is not None)

# Direct tool commands
result = process("/list")
test("/list returns output", result is not None)

result = process("/web test")
test("/web command accepted", result is not None)

# ─── Summary ───────────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {PASS}/{PASS+FAIL} passed, {FAIL}/{PASS+FAIL} failed")
