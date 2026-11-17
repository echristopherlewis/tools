# AGENTS.md

Small standalone CLI tools; see [README.md](README.md).

- Run `python3 tests/test_ai_sessions.py` after changing `ai-sessions`. A single
  test: `python3 tests/test_ai_sessions.py ClaudeParsing.test_full_session`.
- Keep tools single-file, stdlib-only, Python 3.6+ (`typing`, no builtin generics/`|` unions,
  no `from __future__ import annotations`), portable across macOS and Linux (BSD/GNU-compatible flags).
- Always use type hints on Python function parameters and return values (and on
  variables where the type isn't obvious).
- Give every non-trivial function a docstring that says what it does, with an example
  input and the output it produces.
- Keep all `.md` files (README, AGENTS.md, etc.) consistent with the project whenever
  behavior, structure, or conventions change. In particular, keep README in sync with
  behavior and environment variables (the `ai-sessions` module docstring lists them too).

## ai-sessions architecture

One executable script (no `.py` suffix), in layers:

1. **Parsing**: `parse_claude` / `parse_codex` turn a JSONL transcript into a `Summary`
   (index entry) and a list of `Msg` dicts. The type comments near the top of the script
   define both. Injected harness messages are dropped via `CLAUDE_NOISE` / `CODEX_NOISE`.
2. **Index**: `load_sessions` caches summaries in `$XDG_CACHE_HOME/ai-sessions/index.json`,
   keyed by path and invalidated by mtime and size. **Bump `INDEX_VERSION` whenever
   `Summary` keys or meaning change.** Codex titles from `session_index.jsonl` are applied
   after the cache and never stored in it.
3. **Output**: `cmd_list` / `cmd_show` for plain text; `render` builds the transcript
   lines that `--show` and the TUI both use.
4. **TUI**: `App` (session list plus preview) and `Viewer` (full-screen transcript) share
   one curses window. Resuming goes through `build_resume_argv`, configured by
   `AI_SESSIONS_*_CMD`.

Tests import the script with `SourceFileLoader`. They point every directory env var at temp
dirs and drive the TUI with a `FakeScr` key script, so no real terminal is needed. The
fixtures in `tests/fixtures/ai-sessions/` are the reference for both transcript formats;
when a parser changes, add or extend a fixture there.
