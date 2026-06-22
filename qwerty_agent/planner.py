"""
Qwerty v2 — Planner Engine
Multi-step recipe execution. Chains tools together toward a goal.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES_DIR = os.path.join(BASE_DIR, "recipes")

TOOLS_CACHE = None

def _get_tools():
    global TOOLS_CACHE
    if TOOLS_CACHE is not None:
        return TOOLS_CACHE
    from qwerty_agent.agent import TOOLS
    TOOLS_CACHE = TOOLS
    return TOOLS_CACHE

# ─── Load Recipes ──────────────────────────────────────────────
def load_recipes():
    recipes = {}
    if not os.path.isdir(RECIPES_DIR):
        return recipes
    for fname in os.listdir(RECIPES_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(RECIPES_DIR, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for r in data:
                        if r.get("name"):
                            recipes[r["name"]] = r
                elif data.get("name"):
                    recipes[data["name"]] = data
            except Exception:
                pass
    return recipes

# ─── Match User Input to Recipe ────────────────────────────────
def match_recipe(text, recipes):
    text_lower = text.lower().strip()
    best = None
    best_score = 0

    for name, recipe in recipes.items():
        triggers = recipe.get("triggers", [])
        for trigger in triggers:
            t = trigger.lower()
            if t in text_lower:
                score = len(t) / max(len(text_lower), 1)
                if score > best_score:
                    best_score = score
                    best = recipe
            if text_lower.startswith(t):
                best_score = 1.0
                best = recipe
                break
    return best

# ─── Resolve params ────────────────────────────────────────────
def _resolve_params(params_spec, context):
    if params_spec is None:
        return {}
    if not isinstance(params_spec, dict):
        return {"value": params_spec}
    resolved = {}
    for key, val in params_spec.items():
        if isinstance(val, str) and "{" in val:
            val = val.format(**context)
        resolved[key] = val
    return resolved

# ─── Execute a single step ─────────────────────────────────────
def execute_step(step, context):
    tools = _get_tools()
    tool_name = step.get("tool", "")
    params_spec = step.get("params", {})
    params = _resolve_params(params_spec, context)

    step_result = {
        "description": step.get("description", tool_name),
        "tool": tool_name,
        "status": "pending",
        "output": "",
        "error": None,
    }

    if tool_name not in tools:
        step_result["status"] = "error"
        step_result["error"] = f"Unknown tool: {tool_name}"
        return step_result

    tool_fn = tools[tool_name]
    try:
        output = tool_fn(**params)
        output_str = str(output) if output is not None else "(no output)"
        step_result["output"] = output_str[:500]
        step_result["status"] = "ok"
        context["last_output"] = output_str
    except Exception as e:
        step_result["status"] = "error"
        step_result["error"] = str(e)[:200]

    return step_result

# ─── Full Recipe Execution ─────────────────────────────────────
def run_recipe(recipe, context=None):
    if context is None:
        context = {}
    context.setdefault("step_results", [])

    steps = recipe.get("steps", [])
    results = []
    all_ok = True

    for i, step in enumerate(steps):
        context["step_index"] = i
        context["step_count"] = len(steps)
        result = execute_step(step, context)
        results.append(result)

        if result["status"] == "error":
            all_ok = False
            if step.get("critical", False):
                break

    context["step_results"] = results
    context["all_ok"] = all_ok
    return _build_report(recipe, results, all_ok), context

def _build_report(recipe, results, all_ok):
    lines = []
    name = recipe.get("name", "plan")
    lines.append(f"Plan: {recipe.get('description', name)}")
    lines.append("")

    for i, r in enumerate(results, 1):
        icon = "✓" if r["status"] == "ok" else "✗"
        status_color = "ok" if r["status"] == "ok" else "fail"
        lines.append(f"  {i}. {icon} {r['description']}  [{status_color}]")
        if r["output"]:
            out = r["output"][:200]
            lines.append(f"     {out}")
        if r["error"]:
            lines.append(f"     Error: {r['error']}")

    lines.append("")
    if all_ok:
        lines.append("All steps completed.")
    else:
        fail_count = sum(1 for r in results if r["status"] == "error")
        lines.append(f"{fail_count} step(s) failed.")
    return "\n".join(lines)

# ─── Fallback Explorer ─────────────────────────────────────────
# When no recipe matches and no single intent is clear,
# try multiple approaches and report everything found.
def explore(text):
    from qwerty_agent.agent import recall, tool_web_search, tool_wikipedia

    touched = []
    output_parts = []

    # 1. Try local knowledge
    try:
        local = recall(text, top_k=2)
        if local and str(local[0]) not in ("No knowledge found.", ""):
            output_parts.append(f"[Knowledge] {str(local[0])[:300]}")
            touched.append("knowledge")
    except Exception:
        pass

    # 2. Try web search
    if len(touched) < 2:
        try:
            web = tool_web_search(text, max_results=2)
            if web and "No web results" not in web:
                output_parts.append(f"[Web] {web[:300]}")
                touched.append("web")
        except Exception:
            pass

    # 3. Try wikipedia
    if len(touched) < 2:
        try:
            wiki = tool_wikipedia(text, max_sentences=3)
            if wiki and "No Wikipedia" not in wiki:
                output_parts.append(f"[Wikipedia] {wiki[:300]}")
                touched.append("wikipedia")
        except Exception:
            pass

    if not output_parts:
        return "I looked everywhere — knowledge, web, wikipedia. Found nothing relevant."

    sources = ", ".join(touched)
    header = f"Explored: {sources}"
    return header + "\n\n" + "\n\n".join(output_parts)

# ─── Main planner entry point ──────────────────────────────────
def plan_and_execute(text):
    recipes = load_recipes()
    matched = match_recipe(text, recipes)

    if matched:
        result, context = run_recipe(matched, {"input": text})
        return result

    return None  # caller should fall back to single-step or explore
