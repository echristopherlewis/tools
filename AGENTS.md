# AGENTS.md

Small standalone CLI tools; see [README.md](README.md).

- Run `python3 tests/test_ai_sessions.py` after changing `ai-sessions`. A single
  test: `python3 tests/test_ai_sessions.py ClaudeParsing.test_full_session`.
- Keep tools single-file, stdlib-only, Python 3.6+ (`typing`, no builtin generics/`|` unions,
  no `from __future__ import annotations`), portable across macOS and Linux (BSD/GNU-compatible flags).
- Always use type hints on Python function parameters and return values (and on
  variables where the type isn't obvious).
- Members (methods and instance variables) used only inside their own class (or its subclasses) get a
  leading `_`; everything used from outside the class stays public.
- Write code that is easy for humans to understand: clear names, straightforward control
  flow, and comments where the intent isn't obvious.
- Give every non-trivial function a docstring that says what it does, describes each
  argument and what is returned (if anything), and gives an example input and the output
  it produces.
- Keep all `.md` files (README, AGENTS.md, etc.) consistent with the project whenever
  behavior, structure, or conventions change. In particular, keep README in sync with
  behavior and environment variables (the `ai-sessions` module docstring lists them too).

## ai-sessions architecture

One executable script (no `.py` suffix), in layers:

1. **Parsing**: everything specific to one tool lives in a `Source` subclass
   (`ClaudeSource`, `CodexSource`), registered in `SOURCE_LIST` (order matters: claude first)
   and looked up by key in `SOURCES`. A source has display attributes (`tag`, `label`,
   `assistant_name`), resume settings (`default_cmd`, `resume_args`, `cmd_override`),
   `session_env_var`, and methods `_root`, `scan_root`, `discover`, `parse`,
   `title_overrides`, `_resume_template` and `resume_argv`. `Source.parse` turns a JSONL
   transcript into a `Summary` (index entry) and a list of `Msg` dicts; the type comments
   near the top of the script define both. Injected harness messages are dropped via each
   source's `NOISE`. Shared helpers (`_iter_json`, `_make_summary`, ...) are static/instance
   methods on `Source`.
   Adding a tool means adding a `Source` subclass and putting an instance in `SOURCE_LIST`.
2. **Index**: `SessionIndex` (singleton `INDEX`) caches summaries in
   `$XDG_CACHE_HOME/ai-sessions/index.json` (`INDEX.load()`), keyed by path and invalidated
   by mtime and size, and keeps a small LRU of parsed transcripts (`INDEX.transcript()`).
   **Bump `INDEX_VERSION` whenever `Summary` keys or meaning change.** Titles from
   `Source.title_overrides` (Codex's `session_index.jsonl`) are applied after the cache and
   never stored in it. Stars are user data in `$XDG_DATA_HOME/ai-sessions/stars.json`
   (`StarStore`, singleton `STARS`: `STARS.read()` / `STARS.set()`, which re-reads before
   writing); they are applied in `INDEX.load` as `Session.starred`, not cached. The
   `skills/star-session` skill (Claude Code and Codex) calls `ai-sessions --star` /
   `--unstar` / `--star-status`, which find the current session via `CODEX_THREAD_ID` /
   `CLAUDE_CODE_SESSION_ID`. `SessionFilter` (query, source, project, starred-only, sort) says
   which sessions the list shows and in what order; `App.filter` and `cmd_list` both use it.
3. **Output**: `cmd_list` / `cmd_show` for plain text; `render` builds the transcript
   lines that `--show` and the TUI both use. A `Line` is `(text, kind, spans)`, where `spans`
   are `(start, end, style)` character offsets for inline styles (`Screen.text` draws them).
   Assistant replies go through `MarkdownRenderer` (`lines`, `_blocks`, `_table_lines`, plus the
   static `_parse_inline` and `_wrap_segments`), which strips the markup and emits the `heading`,
   `code`, `quote` and `table` kinds; user prompts, tool rows and results are not parsed.
4. **TUI**: `Screen` wraps the curses window and its attribute table (drawing, key input,
   the footer prompt, the help screen); `App` (session list plus preview) and `Viewer`
   (full-screen transcript) share one. Resuming goes through `App.choose_resume` and
   `Source.resume_argv`, configured by `AI_SESSIONS_*_CMD`. `Theme` owns every color
   decision (terminal background detection, row stripe, palette) and builds the curses
   attribute table (`curses_attrs`) that `App` hands to its `Screen`.
   `KEY_BINDINGS` is the single table behind both keymaps and the help screen
   (`build_keymap`, `help_lines`), so adding a key means adding one row.

Tests import the script with `SourceFileLoader`. They point every directory env var at temp
dirs and drive the TUI with a `FakeScr` key script, so no real terminal is needed. The
fixtures in `tests/fixtures/ai-sessions/` are the reference for both transcript formats;
when a parser changes, add or extend a fixture there.
