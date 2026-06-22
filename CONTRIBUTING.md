# Contributing to Qwerty

Qwerty is pure Python stdlib with zero external dependencies. All contributions must maintain this constraint.

## Development

```bash
git clone https://github.com/KasishStar/qwerty-agent
cd qwerty-agent
python test_all.py
```

## Guidelines

1. **No external dependencies** — no `pip install`. Everything must be Python stdlib.
2. **All decisions are deterministic** — no randomness in core logic (except Genius generation temperature).
3. **Constitution first** — any new tool must pass `check_constitution()` and be added to `constitution.json`.
4. **Tests required** — every new feature needs tests in `test_all.py`.
5. **Knowledge is JSON** — new knowledge goes in `knowledge/*.json` following the existing format.
6. **Fuzzy tolerant** — all user-facing text processing must handle typos, shorthand, and informal speech.

## Code Style

- No comments unless absolutely necessary
- 4-space indentation
- Functions under 50 lines where possible
- Variables named for what they are, not how they're used
