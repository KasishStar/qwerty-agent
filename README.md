# Qwerty v3 — Tool Agent with Optional LLM Brain

**Pure Python stdlib. Zero dependencies. Optional AI via Ollama.**

`pip install qwerty-agent` → `qwerty`

## How It Works

```
You → Qwerty TUI
       │
       ├── LLM Brain (Ollama) ← if installed
       │     └── understands you, calls tools, generates response
       │
       └── Direct tools ← fallback
             ├── /web, /wiki, /run, /read, /write
             ├── /search, /find, /list
             └── text normalization + fuzzy matching
```

Without Ollama: Qwerty works as a direct tool agent (commands like `/web`, `/run`, `/read`).
With Ollama: Qwerty becomes an AI agent that understands natural language and decides when to use tools.

## Quick Start

```bash
pip install qwerty-agent
qwerty "explain what a kernel is"
```

For AI mode:
```bash
# Install Ollama: https://ollama.com
ollama pull qwen2.5:7b
qwerty
```

## Features

- **12 tools**: read, write, edit, replace, append, list, search, find, run, web search, wikipedia, learn
- **LLM Brain**: optional Ollama integration — understands natural language, calls tools autonomously
- **Text normalization**: shorthand expansion, contraction handling, character dedup, fuzzy matching
- **Constitution safety**: blocks dangerous commands, secrets leaks, unauthorized file overwrites
- **Persistent memory**: learned facts survive across sessions
- **Beautiful TUI**: colors, dividers, timestamps, tab completion, command history
- **No dependencies**: pure Python stdlib — runs on any system with Python 3.10+

## Commands

| Command | Description |
|---------|-------------|
| `/web <query>` | Search the web |
| `/wiki <topic>` | Look up Wikipedia |
| `/run <cmd>` | Run shell command |
| `/read <path>` | Read a file |
| `/write <path>` | Write a file |
| `/search <text>` | Search files for text |
| `/find <pattern>` | Find files by name |
| `/brain` | Check LLM connection |
| `/status` | Agent status |
| `/help` | Show help |

## Architecture

```
qwerty-agent/
├── qwerty_agent/
│   ├── agent.py        # Tool implementations + process()
│   ├── brain.py        # Ollama LLM connector
│   ├── interface.py    # TUI (colors, history, tab completion)
│   ├── protocol.py     # JSON-RPC / MCP server
│   └── constitution.json  # Safety rules
├── test_all.py         # 46 tests
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.10+
- No pip packages needed
- Ollama (optional) for AI mode

## Tests

```bash
python test_all.py
```
