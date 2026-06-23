#!/usr/bin/env python3
"""
Qwerty v3 — Protocol Layer
JSON-RPC, MCP server, and CLI modes.
"""

import json
import sys
import os

from qwerty_agent.agent import process, TOOLS

# ─── JSON-RPC ──────────────────────────────────────────────────
def handle_json_rpc(request):
    try:
        req = json.loads(request) if isinstance(request, str) else request
    except json.JSONDecodeError as e:
        return _rpc_error(f"Invalid JSON: {e}", None)

    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id", None)

    if method == "process":
        text = params.get("text", "")
        result = process(text)
        return _rpc_response({"response": result}, req_id)
    elif method == "tools":
        schemas = {name: {"description": fn.__doc__ or ""} for name, fn in TOOLS.items()}
        return _rpc_response(schemas, req_id)
    elif method == "schema":
        return _rpc_response({
            "protocol": "qwerty-json-rpc-3.0",
            "methods": {
                "process": {"params": {"text": "string"}, "result": {"response": "string"}},
                "tools": {"result": "object"},
            }
        }, req_id)
    else:
        return _rpc_error(f"Unknown method: {method}", req_id)

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

# ─── MCP Server ────────────────────────────────────────────────
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

# ─── CLI Entry Point ───────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  qwerty-json --process <query>  Process query, output text")
        print("  qwerty-json --schema           Show JSON-RPC schema")
        print("  qwerty-json --mcp              Run MCP stdio server")
        print("  qwerty-json --tools            List available tools")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "--process":
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
