# tools

Small standalone command-line tools. Each is a single file, stdlib-only, and
works on macOS and Linux.

## ai-sessions

NOTE: This code was produced and review by AI.

A curses browser and search for Claude Code and Codex CLI session transcripts.
Python 3.6+, no dependencies.

```sh
ai-sessions                      # interactive browser (press ? for keys; click a row to select it)
ai-sessions --list [terms...]    # tab-separated: date, source, id, project, title
ai-sessions --list --search QUERY --source claude
ai-sessions --show ID [--tools] [--mine]   # print a transcript (id or unique prefix)
```

Install by symlinking it onto your `PATH`:

```sh
ln -s "$PWD/ai-sessions" ~/bin/ai-sessions
```

Environment:

| Variable | Purpose |
| --- | --- |
| `AI_SESSIONS_CLAUDE_DIR` / `AI_SESSIONS_CODEX_DIR` | Transcript roots (defaults: `~/.claude/projects`, `~/.codex`) |
| `AI_SESSIONS_CLAUDE_CMD` / `AI_SESSIONS_CODEX_CMD` | Resume command; `{id}` is replaced by the session id |
| `AI_SESSIONS_STRIPE` | Background color (0-255) of every other session-list row, or `off` (default: 235, or 255 when `COLORFGBG` reports a light background; 256-color terminals only) |
| `XDG_CACHE_HOME` | Location of the index cache (`ai-sessions/index.json`) |

## Development

```sh
python3 tests/test_ai_sessions.py
```

Tests are offline and use temporary directories. The fixtures in
`tests/fixtures/ai-sessions/` double as documentation of the Claude and Codex
transcript formats.

Keep tools portable: BSD/GNU-compatible flags, stdlib-only Python 3.6+ with
`typing` (no builtin generics, `|` unions or `__future__` annotations).

## License

MIT, see [LICENSE](LICENSE).
