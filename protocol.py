#!/usr/bin/env python3
"""
Qwerty v2 — Protocol Layer
JSON-RPC, MCP server, and CLI modes.
Pure Python stdlib. Runs anywhere.
"""

import json
import sys
import os

from agent import process, classify_intent, extract_entities, build_plan, execute_tool, TOOLS, load_knowledge, recall

# ─── JSON-RPC ──────────────────────────────────────────────────────────

def handle_json_rpc(request):
    try:
        req = json.loads(request) if isinstance(request, str) else request
    except json.JSONDecodeError as e:
        return _rpc_error(f"Invalid JSON: {e}", None)
        method = req.get("method", "")
        params = req.get("params", {})
        req_id = req.get("id", None)

        if method == "query":
            text = params.get("text", "")
            result = process_query_json(text)
            return _rpc_response(result, req_id)
        elif method == "process":
            text = params.get("text", "")
            result = process(text)
            return _rpc_response({"response": result}, req_id)
        elif method == "tools":
            schemas = {name: {"description": fn.__doc__ or ""} for name, fn in TOOLS.items()}
            return _rpc_response(schemas, req_id)
        elif method == "knowledge":
            return _rpc_response(load_knowledge(), req_id)
        elif method == "know":
            query = params.get("query", "")
            result = recall(query)
            if isinstance(result, list):
                result = str(result[0]) if result else "No knowledge found."
            return _rpc_response({"result": str(result)}, req_id)
        elif method == "schema":
            return _rpc_response({
                "protocol": "qwerty-json-rpc-2.0",
                "methods": {
                    "query": {"params": {"text": "string"}, "result": "object"},
                    "process": {"params": {"text": "string"}, "result": {"response": "string"}},
                    "tools": {"result": "object"},
                    "knowledge": {"result": "object"},
                    "know": {"params": {"query": "string"}, "result": "object"},
                }
            }, req_id)
        else:
            return _rpc_error(f"Unknown method: {method}", req_id)
    except Exception as e:
        return _rpc_error(str(e), None)

def _rpc_response(result, req_id=None):
    resp = {"jsonrpc": "2.0", "result": result}
    if req_id is not None:
        resp["id"] = req_id
    return resp

def _rpc_error(message, req_id=None):
    resp = {"jsonrpc": "2.0", "error": {"code": -1, "message": str(message)}}
    if req_id is not None:
        resp["id"] = req_id
    return resp

def process_query_json(text):
    intent, confidence = classify_intent(text)
    entities = extract_entities(text, intent)
    steps = build_plan(intent, entities, text)
    results = []
    for step in steps:
        results.append(execute_tool(step["tool"], step["params"]))
    response_text = "\n".join(
        r.get("result", r.get("reason", "")) for r in results
    )
    return {
        "intent": intent,
        "confidence": confidence,
        "entities": entities,
        "plan": steps,
        "results": results,
        "response": response_text,
    }

# ─── MCP Server ────────────────────────────────────────────────────────

def run_mcp_server():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            response = handle_json_rpc(line)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except EOFError:
            break
        except Exception as e:
            err = _rpc_error(str(e))
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

# ─── CLI Entry Point ───────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  qwerty --json <query>     Process query, output JSON")
        print("  qwerty --process <query>  Process query, output text")
        print("  qwerty --schema           Show JSON-RPC schema")
        print("  qwerty --mcp              Run MCP stdio server")
        print("  qwerty --tools            List available tools")
        print("  qwerty                     Run interactive REPL")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "--json":
        text = " ".join(sys.argv[2:])
        print(json.dumps(process_query_json(text), indent=2))
    elif mode == "--process":
        text = " ".join(sys.argv[2:])
        print(process(text) or "No response.")
    elif mode == "--schema":
        schema = handle_json_rpc({"method": "schema", "id": 1})
        print(json.dumps(schema, indent=2))
    elif mode == "--mcp":
        run_mcp_server()
    elif mode == "--tools":
        for name in TOOLS:
            desc = TOOLS[name].__doc__ or ""
            print(f"  {name}: {desc}")
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
