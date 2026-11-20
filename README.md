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
ai-sessions --star [ID]          # star a session (id or unique prefix; default: the current one)
ai-sessions --unstar [ID]        # unstar it
ai-sessions --star-status [ID]   # print "starred ..." or "not starred ..."
ai-sessions --list --starred     # only starred sessions
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
| `AI_SESSIONS_STRIPE` | Background color (0-255) of every other session-list row, or `off` (default: a grey just off the terminal's background as reported by the terminal (OSC 11), else 236, or 255 when `COLORFGBG` reports a light background; 256-color terminals only) |
| `XDG_CACHE_HOME` | Location of the index cache (`ai-sessions/index.json`) |
| `XDG_DATA_HOME` | Location of the stars (`ai-sessions/stars.json`; default `~/.local/share`) |
| `CODEX_THREAD_ID` | Set by Codex; the session `--star` / `--unstar` / `--star-status` act on without an ID (checked first) |
| `CLAUDE_CODE_SESSION_ID` | Set by Claude Code; same, checked second (`--source` restricts to one) |

## Starring

In the browser, `*` stars or unstars the selected session (or the open one in
the viewer) and `S` shows only starred sessions; starred rows show a `*` before
the `CC` / `CX` tag. From the command line use `--star ID` / `--unstar ID`; each
prints one line (`starred claude <id> <title>`) and exits 1 if the ID matches
nothing or the file cannot be written. `--star-status ID` prints
`starred ...` or `not starred ...` and changes nothing. Stars are stored as
`{"version": 1, "stars": {"<id>": <epoch seconds>}}` in `stars.json`; they are user
data, not cache, and are never part of the index.

### Starring from inside Claude Code / Codex

`skills/star-session` is a skill shared by both tools. It runs
`ai-sessions --star`, `--unstar` or `--star-status`, which find the current
session from `CODEX_THREAD_ID` / `CLAUDE_CODE_SESSION_ID`, so you can just say
"star this session" or "is this session starred?". With a slash command:
`/star-session` stars, `/star-session off` unstars, `/star-session --status`
reports (in Codex: `$star-session ...`). Install it by symlink (and make sure `ai-sessions` is on your `PATH`):

```sh
ln -s "$PWD/skills/star-session" ~/.claude/skills/star-session
ln -s "$PWD/skills/star-session" ~/.codex/skills/star-session
```

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
