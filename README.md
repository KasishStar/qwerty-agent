# Qwerty v2 — Zero-Dependency Symbolic AI Agent

**Pure Python stdlib. No numpy. No torch. No sklearn. 10MB total. Runs on a Raspberry Pi.**

Qwerty is an autonomous software agent that reads files, edits code, runs commands, searches the web, learns from every interaction, and composes multi-source answers — all with **zero external dependencies**. It's a symbolic AI: deterministic, constitution-bound, auditable, and completely offline-capable.

## Why Qwerty?

| Qwerty | Other AI Agents |
|---|---|
| `pip install` → runs | Requires Python ML stack (numpy, torch, transformers, 800MB+) |
| Offline by default | Cloud API or local LLM (8GB+ RAM) |
| 10MB on disk | 2-20GB for local models |
| Constitution hardcoded at engine level | Safety is a prompt (jailbreakable) |
| Deterministic — same input, same output | Non-deterministic (sampling) |
| Runs on ARM (Raspberry Pi Zero) | Needs x86 GPU or cloud |

## Features

- **14 tools**: read, write, edit, search, find, run, web search, wikipedia, learn, analyze errors, and more
- **Fuzzy NLP**: handles `"runn ls -la"`, `"plz tel me bout the kernul"`, `"idk wat uefi is"` — 50+ shorthand maps, Levenshtein, n-gram Jaccard, contraction expansion, character dedup
- **Knowledge base**: 8 curated domains + 127 Wikipedia articles covering programming, OS dev, networking, math, physics, chemistry, biology, technology, and general knowledge
- **Genius composition engine**: retrieves, scores, and assembles multi-sentence responses from 2500+ sentences across all knowledge files
- **On-demand learning**: `lookup <topic>` → Wikipedia API (free, caches for next time); web fallback → DuckDuckGo
- **Constitution safety**: 9 hardcoded rules block `rm -rf /`, credential leaks, file overwrites without confirmation, and other dangerous operations
- **Persistent memory**: every answer, every lookup, every fix is stored in `memory/learned.json` — learning compounds across sessions
- **Recursive solve loop**: react → think → explore → internet → report — 3 layers of fallback before giving up
- **Protocol**: JSON-RPC, MCP server, and CLI modes — plugs into any editor or toolchain
- **76 passing tests**, zero external dependencies

## Install

```bash
pip install qwerty-agent
```

Then run:

```bash
qwerty "what is a kernel"
```

Or clone from source:

```bash
git clone https://github.com/KasishStar/qwerty-agent
cd qwerty-agent
python agent.py "what is a kernel"
```

## Interactive Mode

```bash
python agent.py
```

```
qwerty> what is UEFI boot
qwerty> lookup quantum computing
qwerty> list files
qwerty> read file agent.py
qwerty> learn that the answer is 42
qwerty> exit
```

## Interface (with history and slash commands)

```bash
python interface.py
```

## JSON-RPC Protocol

```bash
python protocol.py --process "what is a kernel"
python protocol.py --json "what is a kernel"
python protocol.py --schema
python protocol.py --mcp
```

## Architecture

```
User Input → Normalize → Classify Intent → Constitution Check → Execute → Result
                              ↓
                    Genius Composition Engine
                    (2500+ sentences, 8+ domains)
                              ↓
                    Recursive Fallback Loop
                    react → routine → explore → internet → report
                              ↓
                    Persistent Memory (learned.json)
```

All layers are checked against the constitution before execution. No layer can run `rm -rf /`, overwrite user files without confirmation, or leak credentials.

## How It Works

Qwerty is not an LLM. It's a **symbolic AI** — every decision is deterministic if/then logic. Its "intelligence" comes from:

1. **Broad knowledge** (Wikipedia articles + curated domains)
2. **Fuzzy pattern matching** (Levenshtein, n-gram Jaccard, keyword overlap)
3. **Multi-source composition** (Genius scores and assembles sentences)
4. **On-demand learning** (fetches and stores new knowledge at runtime)
5. **Compounding memory** (every success is saved for next session)

## What Qwerty Can Do

| Task | Example |
|---|---|
| Answer knowledge questions | `"what is a microkernel"` |
| Read/write files | `"read file agent.py"` |
| Edit code | `"edit line 10 of test.py to say hello"` |
| Run commands | `"run cargo build"` |
| Search code | `"search for TODO in src/"` |
| Learn new facts | `"learn that X that Y"` |
| Wikipedia lookup | `"lookup TCP protocol"` |
| Web search | `"search web for rust uefi tutorial"` |
| Analyze errors | Automatic on command failure |
| Remember across sessions | All in `memory/learned.json` |

## Requirements

- Python 3.10+
- No pip packages needed
- Linux, macOS, or Windows
- ARM (Raspberry Pi) supported
- Internet optional (for web search and Wikipedia)

## Project Structure

```
qwerty-agent/
├── agent.py              # Main engine: constitution, tools, NLP, solve loop
├── genius.py             # Response composition engine
├── interface.py          # Interactive REPL with history
├── protocol.py           # JSON-RPC / MCP / CLI modes
├── constitution.json     # 9 safety rules
├── knowledge/            # 9 JSON knowledge files (8 curated + Wikipedia)
├── memory/               # Persistent learning (auto-generated)
├── workflows/            # Pre-defined multi-step workflows
├── knowledge_importer.py # Wikipedia article downloader
├── test_all.py           # 76 comprehensive tests
└── pyproject.toml        # Build configuration
```

## Tests

```bash
python test_all.py
```

## License

MIT — see [LICENSE](LICENSE).

---

**Created by KasishStar.** Pure symbolic AI. No ML dependencies. Runs anywhere.
