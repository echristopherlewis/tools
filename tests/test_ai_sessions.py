#!/usr/bin/env python3
"""Tests for ai-sessions (stdlib unittest, Python 3.6+).

Run from the repo root:  python3 tests/test_ai_sessions.py

Every test points AI_SESSIONS_CLAUDE_DIR / AI_SESSIONS_CODEX_DIR / XDG_CACHE_HOME at
temporary directories, so the real ~/.claude, ~/.codex and ~/.cache are never read or
written. The fixture transcripts under fixtures/ai-sessions/ double as format
documentation for both tools.
"""

import calendar
import curses
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional, Union
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "ai-sessions")
FIXTURES = os.path.join(HERE, "fixtures", "ai-sessions")


def _load_module() -> Any:
    """Import ai-sessions (no .py suffix) as a module."""
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("ai_sessions", SCRIPT)
    spec = importlib.util.spec_from_loader("ai_sessions", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_sessions"] = mod
    loader.exec_module(mod)
    return mod


ai = _load_module()


def pick(*names: str) -> Any:
    """First attribute of the module that exists (tolerates internal renames)."""
    for n in names:
        if hasattr(ai, n):
            return getattr(ai, n)
    raise AttributeError(names)


char_width = pick("char_width", "cw")
str_width = pick("str_width", "sw")


def role(m: Any) -> str:
    return m["role"] if isinstance(m, dict) else m.role


def mtext(m: Any) -> str:
    return m["text"] if isinstance(m, dict) else m.text


def ts_of(s: str) -> float:
    return float(calendar.timegm(
        tuple(int(x) for x in re.split(r"[-T: ]", s)) + (0, 0, 0)))  # type: ignore


def write_jsonl(path: str, records: List[Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


class Env(unittest.TestCase):
    """Base: copies the fixtures to a temp dir and isolates all environment."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ai-sessions-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.claude = os.path.join(self.tmp, "claude")
        self.codex = os.path.join(self.tmp, "codex")
        self.cache = os.path.join(self.tmp, "cache")
        shutil.copytree(os.path.join(FIXTURES, "claude"), self.claude)
        shutil.copytree(os.path.join(FIXTURES, "codex"), self.codex)
        env = {"AI_SESSIONS_CLAUDE_DIR": self.claude, "AI_SESSIONS_CODEX_DIR": self.codex,
               "XDG_CACHE_HOME": self.cache, "TZ": "UTC"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ("AI_SESSIONS_CLAUDE_CMD", "AI_SESSIONS_CODEX_CMD"):
            os.environ.pop(k, None)
        if hasattr(ai, "CMD_OVERRIDES"):
            ai.CMD_OVERRIDES.clear()
            self.addCleanup(ai.CMD_OVERRIDES.clear)

    def fx(self, *parts: str) -> str:
        return os.path.join(self.tmp, *parts)

    def sessions(self) -> Dict[str, Any]:
        return {s.id: s for s in ai.load_sessions()}


A_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
C_ID = "cccccccc-1111-4ccc-8ccc-cccccccccccc"
D_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
X_ID = "11111111-1111-4111-8111-111111111111"
Y_ID = "22222222-2222-4222-8222-222222222222"


# ------------------------------------------------------------ parsing

class ClaudeParsing(Env):
    def parse(self, *parts: str) -> Any:
        return ai.parse_claude(self.fx("claude", *parts))

    def test_full_session(self) -> None:
        summary, msgs = self.parse("-work-alpha", A_ID + ".jsonl")
        self.assertEqual(summary["source"], "claude")
        self.assertEqual(summary["id"], A_ID)
        self.assertEqual(summary["cwd"], "/work/alpha")
        # gitBranch "HEAD" (detached) is ignored; the sidechain's branch never counts.
        self.assertEqual(summary["branch"], "feature/x")
        self.assertEqual(summary["title"], "My custom title")
        self.assertEqual((summary["n_user"], summary["n_asst"]), (1, 2))
        self.assertEqual(summary["first_ts"], ts_of("2025-03-01T10:00:00"))
        self.assertEqual(summary["last_ts"], ts_of("2025-03-01T10:05:00"))
        # meta, sidechain, system-reminder and "Caveat:" records are all skipped.
        self.assertEqual([role(m) for m in msgs],
                         ["user", "cmd", "assistant", "tool", "result", "assistant"])
        self.assertEqual(mtext(msgs[0]), "Fix the frobnicator bug")
        self.assertEqual(mtext(msgs[1]), "/review src/foo.py --deep")
        self.assertEqual(mtext(msgs[2]), "I will look at the file.")
        self.assertEqual(mtext(msgs[3]), "Read: /work/alpha/foo.py")
        self.assertEqual(mtext(msgs[4]), "line one\nline two")
        self.assertEqual(mtext(msgs[5]), "Found it: the zebra widget.")
        joined = " ".join(mtext(m) for m in msgs)
        for bad in ("must not appear", "harness noise", "Caveat"):
            self.assertNotIn(bad, joined)
        # search text includes user/assistant text and tool names, lowercased
        self.assertIn("zebra widget", summary["blob"])
        self.assertIn("read", summary["blob"])
        self.assertEqual(summary["blob"], summary["blob"].lower())

    def test_title_priority(self) -> None:
        self.assertEqual(self.parse("-work-alpha", A_ID + ".jsonl")[0]["title"], "My custom title")
        self.assertEqual(self.parse("-work-alpha", B_ID + ".jsonl")[0]["title"],
                         "Only AI title wins over summary")
        self.assertEqual(self.parse("-work-beta", C_ID + ".jsonl")[0]["title"],
                         "Summary beats first prompt")
        self.assertEqual(self.parse("-work-beta", D_ID + ".jsonl")[0]["title"],
                         "First prompt becomes the title with a second paragraph")

    def test_first_prompt_title_truncated(self) -> None:
        p = self.fx("claude", "-x", "t.jsonl")
        write_jsonl(p, [{"type": "user", "message": {"content": "w" * 300}}])
        self.assertEqual(ai.parse_claude(p)[0]["title"], "w" * 100)

    def test_string_content_for_assistant(self) -> None:
        _, msgs = self.parse("-work-alpha", B_ID + ".jsonl")
        self.assertEqual([role(m) for m in msgs], ["user", "assistant"])
        self.assertEqual(mtext(msgs[1]), "plain string assistant reply")

    def test_head_branch_only(self) -> None:
        p = self.fx("claude", "-x", "h.jsonl")
        write_jsonl(p, [{"type": "user", "gitBranch": "HEAD", "cwd": "/w",
                         "message": {"content": "hi"}}])
        s = ai.parse_claude(p)[0]
        self.assertEqual(s["branch"], "")
        self.assertEqual(s["cwd"], "/w")

    def test_slash_command_without_args(self) -> None:
        p = self.fx("claude", "-x", "c.jsonl")
        write_jsonl(p, [{"type": "user", "message": {
            "content": "<command-name>/clear</command-name>\n<command-args></command-args>"}}])
        msgs = ai.parse_claude(p)[1]
        self.assertEqual([(role(m), mtext(m)) for m in msgs], [("cmd", "/clear")])

    def test_garbage_lines_are_skipped(self) -> None:
        p = self.fx("claude", "-x", "g.jsonl")
        write_jsonl(p, ["not json", "[1,2]", "{bad", "",
                        {"type": "user", "message": {"content": "ok"}}])
        self.assertEqual(ai.parse_claude(p)[0]["n_user"], 1)

    def test_tool_use_summaries(self) -> None:
        p = self.fx("claude", "-x", "tu.jsonl")
        write_jsonl(p, [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls -l\nmore", "description": "d"}},
            {"type": "tool_use", "name": "Odd", "input": {"zzz": "fallback value"}},
            {"type": "tool_use", "name": "NoInput"}]}}])
        msgs = ai.parse_claude(p)[1]
        self.assertEqual([mtext(m) for m in msgs],
                         ["Bash: ls -l", "Odd: fallback value", "NoInput"])


class CodexParsing(Env):
    X_PATH = os.path.join("sessions", "2025", "03", "02",
                          "rollout-2025-03-02T09-00-00-" + X_ID + ".jsonl")

    def test_full_session(self) -> None:
        summary, msgs = ai.parse_codex(self.fx("codex", self.X_PATH))
        self.assertEqual(summary["source"], "codex")
        self.assertEqual(summary["id"], X_ID)
        self.assertEqual(summary["cwd"], "/work/codex-proj")
        self.assertEqual(summary["branch"], "main")
        self.assertEqual(summary["title"], "Refactor the quokka parser")
        self.assertEqual((summary["n_user"], summary["n_asst"]), (1, 2))
        self.assertEqual(summary["first_ts"], ts_of("2025-03-02T09:00:00"))
        self.assertEqual(summary["last_ts"], ts_of("2025-03-02T09:30:00"))
        self.assertEqual([role(m) for m in msgs],
                         ["user", "assistant", "tool", "result", "tool", "result", "assistant"])
        self.assertEqual(mtext(msgs[2]), "shell: bash -lc ls -la")
        self.assertEqual(mtext(msgs[3]), "file1\nfile2")
        self.assertEqual(mtext(msgs[4]), "apply_patch: *** Begin Patch")
        self.assertEqual(mtext(msgs[5]), "Patch applied")
        joined = " ".join(mtext(m) for m in msgs)
        for bad in ("developer text", "AGENTS.md", "environment_context", "be nice"):
            self.assertNotIn(bad, joined)

    def test_sid_from_filename_when_no_meta(self) -> None:
        uuid = "99999999-9999-4999-8999-999999999999"
        p = self.fx("codex", "sessions", "rollout-2025-01-01T00-00-00-" + uuid + ".jsonl")
        write_jsonl(p, [{"timestamp": "2025-01-01T00:00:00Z", "type": "response_item",
                         "payload": {"type": "message", "role": "assistant",
                                     "content": [{"type": "output_text", "text": "hi"}]}}])
        s, msgs = ai.parse_codex(p)
        self.assertEqual(s["id"], uuid)
        # With no user prompt, the first assistant text titles the session.
        self.assertEqual(s["title"], "hi")
        self.assertEqual(len(msgs), 1)

    def test_turn_context_supplies_cwd(self) -> None:
        p = self.fx("codex", "sessions", "rollout-x-" + "0" * 36 + ".jsonl")
        write_jsonl(p, [{"type": "turn_context", "payload": {"cwd": "/tc"}},
                        {"type": "response_item", "payload": {
                            "type": "message", "role": "user", "content": "plain str"}}])
        s, msgs = ai.parse_codex(p)
        self.assertEqual(s["cwd"], "/tc")
        self.assertEqual(mtext(msgs[0]), "plain str")

    def test_user_noise_detection(self) -> None:
        noise = ai.codex_user_noise
        self.assertTrue(noise("# AGENTS.md instructions for /x"))
        self.assertTrue(noise("<environment_context>\n</environment_context>"))
        self.assertTrue(noise("<turn_aborted>\n</turn_aborted>"))
        self.assertFalse(noise("<b>hello</b> world"))
        self.assertFalse(noise("fix the bug"))


class LoadSessions(Env):
    def test_visible_sessions(self) -> None:
        ss = self.sessions()
        # empty sessions (eeee..., 3333...) and the claude "memory" dir are omitted
        self.assertEqual(sorted(ss), sorted([A_ID, B_ID, C_ID, D_ID, X_ID, Y_ID]))

    def test_codex_title_from_index(self) -> None:
        ss = self.sessions()
        self.assertEqual(ss[X_ID].title, "Quokka thread name")
        self.assertEqual(ss[Y_ID].title, "Second codex prompt about walruses")

    def test_session_fields(self) -> None:
        s = self.sessions()[A_ID]
        self.assertEqual(s.project, "alpha")
        self.assertEqual(s.cwd, "/work/alpha")
        s2 = ai.Session({"source": "claude", "id": "x", "path": "p", "cwd": "", "branch": "",
                         "title": "", "first_ts": 0, "last_ts": 0, "n_user": 1, "n_asst": 0,
                         "blob": ""})
        self.assertEqual((s2.project, s2.title), ("-", "(untitled)"))

    def cache_files(self) -> Dict[str, Any]:
        with open(os.path.join(self.cache, "ai-sessions", "index.json")) as f:
            return json.load(f)["files"]

    def test_first_load_parses_every_file_once(self) -> None:
        with mock.patch.object(ai, "parse_any", wraps=ai.parse_any) as pa:
            ai.load_sessions()
            # 5 claude files (memory/ is skipped) + 3 codex rollouts, empty ones included
            self.assertEqual(pa.call_count, 8)
        self.assertEqual(len(self.cache_files()), 8)

    def test_cache_second_load_does_not_parse(self) -> None:
        ai.load_sessions()
        with mock.patch.object(ai, "parse_any", wraps=ai.parse_any) as pa:
            self.assertEqual(len(ai.load_sessions()), 6)
            self.assertEqual(pa.call_count, 0)

    def test_modified_file_is_reparsed(self) -> None:
        ai.load_sessions()
        path = self.fx("claude", "-work-beta", D_ID + ".jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "another"}}) + "\n")
        st = os.stat(path)
        os.utime(path, (st.st_atime, st.st_mtime + 10))
        with mock.patch.object(ai, "parse_any", wraps=ai.parse_any) as pa:
            ss = self.sessions()
            self.assertEqual(pa.call_count, 1)
        self.assertEqual(ss[D_ID].n_user, 2)

    def test_deleted_file_is_pruned(self) -> None:
        ai.load_sessions()
        path = self.fx("claude", "-work-beta", D_ID + ".jsonl")
        os.remove(path)
        ss = self.sessions()
        self.assertNotIn(D_ID, ss)
        self.assertNotIn(path, self.cache_files())

    def test_prune_only_under_scanned_roots(self) -> None:
        ai.load_sessions()
        cp = os.path.join(self.cache, "ai-sessions", "index.json")
        with open(cp) as f:
            data = json.load(f)
        data["files"]["/elsewhere/x.jsonl"] = {"mtime": 1, "size": 1, "summary": {"source": "claude"}}
        with open(cp, "w") as f:
            json.dump(data, f)
        os.remove(self.fx("claude", "-work-beta", D_ID + ".jsonl"))  # forces a cache rewrite
        ai.load_sessions()
        self.assertIn("/elsewhere/x.jsonl", self.cache_files())

    def test_codex_index_change_applies_without_reparse(self) -> None:
        ai.load_sessions()
        write_jsonl(self.fx("codex", "session_index.jsonl"),
                    [{"id": X_ID, "thread_name": "Renamed thread"}])
        with mock.patch.object(ai, "parse_any", wraps=ai.parse_any) as pa:
            ss = self.sessions()
            self.assertEqual(pa.call_count, 0)
        self.assertEqual(ss[X_ID].title, "Renamed thread")

    def test_index_version_mismatch_reparses(self) -> None:
        ai.load_sessions()
        cp = os.path.join(self.cache, "ai-sessions", "index.json")
        with open(cp) as f:
            data = json.load(f)
        data["version"] = -1
        with open(cp, "w") as f:
            json.dump(data, f)
        with mock.patch.object(ai, "parse_any", wraps=ai.parse_any) as pa:
            ai.load_sessions()
            self.assertGreater(pa.call_count, 0)

    def test_corrupt_cache_is_ignored(self) -> None:
        os.makedirs(os.path.join(self.cache, "ai-sessions"))
        with open(os.path.join(self.cache, "ai-sessions", "index.json"), "w") as f:
            f.write("{not json")
        self.assertEqual(len(ai.load_sessions()), 6)

    def test_filter_and_sort(self) -> None:
        ss = list(self.sessions().values())
        ids = lambda xs: sorted(s.id for s in xs)  # noqa: E731
        self.assertEqual(ids(ai.filter_sessions(ss, "QUOKKA")), [X_ID])   # case-insensitive
        self.assertEqual(ids(ai.filter_sessions(ss, "beta charlie")), [C_ID])  # ANDed terms
        self.assertEqual(ids(ai.filter_sessions(ss, "", "codex")), sorted([X_ID, Y_ID]))
        self.assertEqual(ids(ai.filter_sessions(ss, "", "all", "/work/beta")), sorted([C_ID, D_ID]))
        self.assertEqual(ai.filter_sessions(ss, "zzzz-nothing"), [])
        self.assertEqual(ids(ai.filter_sessions(ss, "zebra")), [A_ID])  # transcript text
        self.assertEqual([s.id for s in ai.sort_sessions(ss)],
                         [D_ID, Y_ID, C_ID, X_ID, B_ID, A_ID])


# ------------------------------------------------------------ CLI

class Cli(Env):
    def run_cli(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        p = subprocess.run([sys.executable, SCRIPT] + list(args), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True,
                           stdin=subprocess.DEVNULL, env=dict(os.environ))
        self.assertEqual(p.returncode, expect, p.stderr)
        return p

    def rows(self, out: str) -> List[List[str]]:
        return [ln.split("\t") for ln in out.splitlines()]

    def test_list(self) -> None:
        rows = self.rows(self.run_cli("--list").stdout)
        self.assertEqual([r[2] for r in rows], [D_ID, Y_ID, C_ID, X_ID, B_ID, A_ID])
        self.assertEqual(rows[0], ["2025-03-04 08:01", "claude", D_ID, "beta",
                                   "First prompt becomes the title with a second paragraph"])
        self.assertEqual(rows[3][:4], ["2025-03-02 09:30", "codex", X_ID, "codex-proj"])
        self.assertEqual(rows[3][4], "Quokka thread name")

    def test_list_query_and_source(self) -> None:
        rows = self.rows(self.run_cli("--list", "quokka").stdout)
        self.assertEqual([r[2] for r in rows], [X_ID])
        rows = self.rows(self.run_cli("--list", "--search", "beta", "--source", "claude").stdout)
        self.assertEqual([r[2] for r in rows], [D_ID, C_ID])
        rows = self.rows(self.run_cli("--list", "--source", "codex").stdout)
        self.assertEqual([r[2] for r in rows], [Y_ID, X_ID])
        self.assertEqual(self.run_cli("--list", "nomatchatall").stdout, "")

    def test_show_exact_output(self) -> None:
        out = self.run_cli("--show", A_ID, "--tools").stdout
        expected = "\n".join([
            "My custom title",
            "Claude Code   " + A_ID,
            "Dir:     /work/alpha",
            "Branch:  feature/x",
            "Started: 2025-03-01 10:00   Updated: 2025-03-01 10:05",
            "Messages: 1 you, 2 claude",
            ai.rule_chars()[0] * 100,
            "",
            "You:  10:00",
            "  Fix the frobnicator bug",
            "  > /review src/foo.py --deep",
            "",
            "Claude:  10:00",
            "  I will look at the file.",
            "  → Read: /work/alpha/foo.py",
            "    ← line one",
            "    ← line two",
            "",
            "Claude:  10:05",
            "  Found it: the zebra widget.",
            ""])
        self.assertEqual(out, expected)

    def test_show_prefix_and_tools_flag(self) -> None:
        plain = self.run_cli("--show", "aaaaaaaa").stdout
        self.assertIn("→ Read: /work/alpha/foo.py", plain)  # calls always shown
        self.assertNotIn("←", plain)                         # results hidden
        self.assertIn("← line one", self.run_cli("--show", "aaaaaaaa", "--tools").stdout)

    def test_show_mine(self) -> None:
        out = self.run_cli("--show", A_ID, "--mine").stdout
        self.assertIn("Fix the frobnicator bug", out)
        self.assertIn("> /review src/foo.py --deep", out)
        self.assertNotIn("zebra", out)
        self.assertNotIn("Claude:", out)

    def test_show_codex(self) -> None:
        out = self.run_cli("--show", "1111", "--tools").stdout
        self.assertIn("Codex   " + X_ID, out)
        self.assertIn("→ apply_patch: *** Begin Patch", out)
        self.assertIn("← Patch applied", out)

    def test_show_missing_and_ambiguous(self) -> None:
        p = self.run_cli("--show", "zzz", expect=1)
        self.assertIn("no session matches", p.stderr)
        shutil.copy(self.fx("claude", "-work-alpha", A_ID + ".jsonl"),
                    self.fx("claude", "-work-alpha", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab.jsonl"))
        p = self.run_cli("--show", "aaaaaaaa", expect=1)
        self.assertIn("ambiguous", p.stderr)
        self.assertEqual(p.stdout, "")
        self.run_cli("--show", A_ID)  # an exact id is never ambiguous

    def test_tui_needs_terminal(self) -> None:
        p = self.run_cli(expect=2)
        self.assertIn("needs a terminal", p.stderr)


# ------------------------------------------------------------ units

class Units(unittest.TestCase):
    def test_parse_ts(self) -> None:
        base = ts_of("2025-03-01T10:00:00")
        p = ai.parse_ts
        self.assertEqual(p("2025-03-01T10:00:00Z"), base)
        self.assertEqual(p("2025-03-01 10:00:00"), base)
        self.assertAlmostEqual(p("2025-03-01T10:00:00.500Z"), base + 0.5)
        self.assertEqual(p("2025-03-01T10:00:00+02:00"), base - 7200)
        self.assertEqual(p("2025-03-01T10:00:00-0530"), base + 5.5 * 3600)
        self.assertEqual(p(1700000000), 1700000000.0)          # seconds
        self.assertEqual(p(1700000000000), 1700000000.0)       # milliseconds
        self.assertEqual(p(1700000000.5), 1700000000.5)
        for bad in ("garbage", "", None, [], {}, "2025-13-45T99:99:99Z"):
            self.assertIsNone(p(bad), bad)

    def test_widths_clip_pad(self) -> None:
        self.assertEqual(char_width("a"), 1)
        self.assertEqual(char_width("漢"), 2)
        self.assertEqual(char_width("́"), 0)
        self.assertEqual(str_width("漢a"), 3)
        self.assertEqual(ai.clip("漢字abc", 3), "漢")
        self.assertEqual(ai.clip("漢字abc", 4), "漢字")
        self.assertEqual(ai.clip("abc", 0), "")
        self.assertEqual(ai.pad("漢", 4), "漢  ")
        self.assertEqual(ai.pad("abcdef", 3), "abc")
        self.assertEqual(str_width(ai.pad("漢字字", 5)), 5)

    def test_clean(self) -> None:
        self.assertEqual(ai.clean("a\tb\r\nc\x00d\x7fe"), "a    b\nc d e")

    def test_wrap(self) -> None:
        self.assertEqual(ai.wrap("aaa bbb ccc", 7), ["aaa bbb", "ccc"])
        long_word = ai.wrap("a" * 25, 10)
        self.assertEqual(long_word, ["a" * 10, "a" * 10, "a" * 5])
        wide = ai.wrap("漢" * 10, 10)
        self.assertEqual(wide, ["漢" * 5, "漢" * 5])
        self.assertEqual(ai.wrap("a\n\n\n\nb", 20), ["a", "", "b"])
        self.assertEqual(ai.wrap("\n\na\n\n", 20), ["a"])
        ind = ai.wrap("    hello world foo bar", 14)
        self.assertEqual(ind, ["    hello", "    world foo", "    bar"])
        self.assertTrue(all(str_width(x) <= 14 for x in ind))
        self.assertEqual(ai.wrap("", 20), [])

    def test_summarize_tool_and_content_text(self) -> None:
        # TOOL_KEYS order decides which argument is shown ("path" before "pattern")
        self.assertEqual(ai.summarize_tool("Grep", {"pattern": "foo", "path": "/x"}), "Grep: /x")
        self.assertEqual(ai.summarize_tool("Bash", {"command": "echo hi"}), "Bash: echo hi")
        self.assertEqual(ai.summarize_tool("sh", '{"cmd": ["ls", "-l"]}'), "sh: ls -l")
        self.assertEqual(ai.summarize_tool("raw", "just text\nsecond"), "raw: just text")
        self.assertEqual(ai.summarize_tool(None, None), "tool")
        self.assertEqual(ai.content_text("s"), "s")
        self.assertEqual(ai.content_text([{"type": "text", "text": "a"}, "b", {"x": 1}]), "a\nb")
        self.assertEqual(ai.content_text(None), "")

    def test_shell_quote(self) -> None:
        self.assertEqual(ai.shell_quote("abc-1/x.y"), "abc-1/x.y")
        self.assertEqual(ai.shell_quote("a b"), "'a b'")
        self.assertEqual(ai.shell_quote("it's"), "'it'\\''s'")
        self.assertEqual(ai.shell_quote(""), "''")

    def test_render_and_hit_lines(self) -> None:
        s = ai.Session({"source": "claude", "id": "i", "path": "p", "cwd": "/w/proj", "branch": "",
                        "title": "T", "first_ts": 0, "last_ts": 0, "n_user": 1, "n_asst": 1,
                        "blob": ""})
        msgs = [{"role": "user", "text": "hello world", "ts": None},
                {"role": "tool", "name": "Read", "text": "Read: /x", "ts": None},
                {"role": "result", "text": "\n".join("r%d" % i for i in range(9)), "ts": None},
                {"role": "assistant", "text": "bye", "ts": None}]
        if not isinstance(ai.parse_claude, type(None)) and hasattr(ai, "Msg") and \
                not isinstance(getattr(ai, "Msg"), type(Dict)) and hasattr(ai.Msg, "_fields"):
            msgs = [ai.Msg(*[m.get(f) for f in ai.Msg._fields]) for m in msgs]  # type: ignore
        lines, start = ai.render(s, msgs, 40, True)
        texts = [t for t, _ in lines]
        self.assertEqual(texts[0], "T")
        self.assertTrue(start > 0 and texts[start - 1].startswith(ai.rule_chars()[0] * 3))
        self.assertIn("    ← r5", texts)
        self.assertIn("    ← ... (3 more lines)", texts)   # 6 result lines shown
        self.assertNotIn("    ← r6", texts)
        hidden = [t for t, _ in ai.render(s, msgs, 40, False)[0]]
        self.assertFalse(any("←" in t for t in hidden))
        self.assertEqual(ai.hit_lines(lines, start, ["world"]),
                         [i for i in range(start, len(lines)) if "world" in lines[i][0]])
        self.assertEqual(ai.hit_lines(lines, start, []), [])
        # header lines (meta) are never hits
        self.assertEqual(ai.hit_lines(lines, start, ["claude code"]), [])


class ResumeArgv(Env):
    def test_defaults(self) -> None:
        self.assertEqual(ai.build_resume_argv("claude", "S1"), (["claude", "--resume", "S1"], None))
        self.assertEqual(ai.build_resume_argv("codex", "S1"), (["codex", "resume", "S1"], None))

    def test_id_substitution(self) -> None:
        os.environ["AI_SESSIONS_CODEX_CMD"] = "codex resume {id} --yolo"
        self.assertEqual(ai.build_resume_argv("codex", "S1")[0], ["codex", "resume", "S1", "--yolo"])

    def test_args_appended(self) -> None:
        os.environ["AI_SESSIONS_CLAUDE_CMD"] = "claude --model opus"
        self.assertEqual(ai.build_resume_argv("claude", "S1")[0],
                         ["claude", "--model", "opus", "--resume", "S1"])

    def test_cli_override_beats_env(self) -> None:
        os.environ["AI_SESSIONS_CLAUDE_CMD"] = "fromenv"
        ai.CMD_OVERRIDES["claude"] = "fromcli {id}"
        self.assertEqual(ai.build_resume_argv("claude", "S1")[0], ["fromcli", "S1"])
        self.assertEqual(ai.build_resume_argv("codex", "S1")[0], ["codex", "resume", "S1"])

    def test_bad_and_empty_templates_warn(self) -> None:
        os.environ["AI_SESSIONS_CLAUDE_CMD"] = 'claude "unterminated'
        argv, warn = ai.build_resume_argv("claude", "S1")
        self.assertEqual(argv, ["claude", "--resume", "S1"])
        self.assertIn("bad claude command", warn or "")
        os.environ["AI_SESSIONS_CLAUDE_CMD"] = "  "
        argv, warn = ai.build_resume_argv("claude", "S1")
        self.assertEqual(argv, ["claude", "--resume", "S1"])
        self.assertIn("empty claude command", warn or "")

    def test_session_resume_cmd(self) -> None:
        s = self.sessions()[A_ID]
        self.assertEqual(s.resume_cmd(), "cd /work/alpha && claude --resume " + A_ID)
        s2 = self.sessions()[X_ID]
        self.assertEqual(s2.resume_cmd(), "cd /work/codex-proj && codex resume " + X_ID)

    def sessions(self) -> Dict[str, Any]:
        return {s.id: s for s in ai.load_sessions()}


# ------------------------------------------------------------ TUI

class KeysExhausted(Exception):
    pass


Key = Union[str, int]


class FakeScr(object):
    """Just enough of a curses window to drive App without a terminal."""

    def __init__(self, keys: List[Key], h: int = 30, w: int = 120) -> None:
        self.h, self.w = h, w
        self.keys = list(keys)
        self.frames = []  # type: List[str]
        self.erase()

    def getmaxyx(self) -> Any:
        return self.h, self.w

    def erase(self) -> None:
        self.cells = [[" "] * self.w for _ in range(self.h)]

    def keypad(self, flag: bool) -> None:
        pass

    def _put(self, y: int, x: int, s: str) -> None:
        if not (0 <= y < self.h) or x < 0:
            raise curses.error("out of range")
        for c in s:
            if x >= self.w:
                raise curses.error("out of range")
            self.cells[y][x] = c
            wd = char_width(c)
            if wd == 2 and x + 1 < self.w:
                self.cells[y][x + 1] = ""
            x += max(wd, 1)

    def addstr(self, y: int, x: int, s: str, attr: int = 0) -> None:
        # Like real curses, writing through the bottom-right cell raises.
        self._put(y, x, s)
        if y == self.h - 1 and x + str_width(s) >= self.w:
            raise curses.error("bottom-right")

    def addch(self, y: int, x: int, c: str, attr: int = 0) -> None:
        self._put(y, x, c)
        if y == self.h - 1 and x == self.w - 1:
            raise curses.error("bottom-right")

    def refresh(self) -> None:
        self.frames.append(self.screen())

    def screen(self) -> str:
        return "\n".join("".join(r).rstrip() for r in self.cells)

    def get_wch(self) -> Key:
        if not self.keys:
            raise KeysExhausted()
        return self.keys.pop(0)

    def any_frame(self, needle: str) -> bool:
        return any(needle in f for f in self.frames)


class Tui(Env):
    def make(self, keys: List[Key], query: str = "", source: str = "all",
             h: int = 30, w: int = 120) -> Any:
        self.scr = FakeScr(keys, h, w)
        return ai.App(self.scr, list(ai.load_sessions()), query, source)

    def run_keys(self, keys: List[Key], **kw: Any) -> Any:
        app = self.make(keys, **kw)
        app.run()
        self.assertEqual(self.scr.keys, [], "unconsumed keys")
        return app

    def test_init_colors_without_terminal(self) -> None:
        app = self.make([])
        self.assertIn("hl", getattr(app, "attrs", None) or app.A)  # swallowed curses.error

    def test_initial_view_and_draw(self) -> None:
        app = self.make(["q"])
        app.run()
        self.assertEqual([s.id for s in app.view], [D_ID, Y_ID, C_ID, X_ID, B_ID, A_ID])
        scr = self.scr.frames[0]
        self.assertIn("ai-sessions  6/6 sessions  filter: none  sort: last activity", scr)
        self.assertIn("First prompt becomes the title", scr)
        self.assertIn("2025-03-04 08:01", scr)
        self.assertIn("CC", scr)
        self.assertIn("CX", scr)
        self.assertIn(ai.rule_chars()[1], scr)  # side-by-side separator at 120 cols
        self.assertIn("Claude Code   " + D_ID, scr)  # preview pane

    def test_move_keys(self) -> None:
        app = self.run_keys(["j", "j", "q"])
        self.assertEqual(app.current().id, C_ID)
        app = self.run_keys(["j", "j", "j", "k", "q"])
        self.assertEqual(app.current().id, C_ID)
        app = self.run_keys([curses.KEY_DOWN, curses.KEY_UP, curses.KEY_UP, "q"])
        self.assertEqual(app.current().id, D_ID)
        app = self.run_keys(["G", "q"])
        self.assertEqual(app.current().id, A_ID)
        app = self.run_keys([curses.KEY_END, "g", "q"])
        self.assertEqual(app.current().id, D_ID)
        app = self.run_keys([curses.KEY_NPAGE, "q"])
        self.assertEqual(app.current().id, A_ID)  # page larger than the list
        app = self.run_keys([curses.KEY_NPAGE, curses.KEY_PPAGE, "q"])
        self.assertEqual(app.current().id, D_ID)

    def test_resize_ignored(self) -> None:
        app = self.run_keys([curses.KEY_RESIZE, "j", "q"])
        self.assertEqual(app.current().id, Y_ID)

    def test_key_names(self) -> None:
        app = self.make([curses.KEY_UP, curses.KEY_BACKSPACE, "\n", "\x1b", "\t", "\x15", "x", 99999])
        self.assertEqual([app.key() for _ in range(8)],
                         ["UP", "BS", "ENTER", "ESC", "TAB", "CU", "x", "UNKNOWN"])

    def test_unknown_special_key_is_ignored(self) -> None:
        # Regression: unmapped keys (e.g. F1) used to be named "?" and opened help.
        app = self.run_keys([curses.KEY_F1, "j", "q"])
        self.assertFalse(self.scr.any_frame("Press any key."))
        self.assertEqual(app.current().id, Y_ID)
        buf, ok = self.make([curses.KEY_F1, "a", "\n"]).prompt("/", "")
        self.assertEqual((buf, ok), ("a", True))

    def test_filter_enter_and_esc(self) -> None:
        app = self.run_keys(["/"] + list("quokka") + ["\n", "q"])
        self.assertEqual(app.query, "quokka")
        self.assertEqual([s.id for s in app.view], [X_ID])
        self.assertTrue(self.scr.any_frame("filter: /quokka"))
        app = self.run_keys(["/"] + list("quokka") + ["\n", "\x1b", "q"])
        self.assertEqual(app.query, "")
        self.assertEqual(len(app.view), 6)

    def test_filter_live_and_edit_keys(self) -> None:
        app = self.make(["/", "w", "a", "l", "x", "\x7f", "r", "\n", "q"])
        app.run()
        self.assertEqual(app.query, "walr")
        self.assertEqual([s.id for s in app.view], [Y_ID])
        app = self.run_keys(["/", "z", "z", "\x15", "b", "r", "a", "v", "o", "\n", "q"])
        self.assertEqual(app.query, "bravo")
        self.assertEqual([s.id for s in app.view], [B_ID])

    def test_filter_cancel_with_esc_clears(self) -> None:
        app = self.run_keys(["/"] + list("beta") + ["\x1b", "q"])
        self.assertEqual(app.query, "")
        self.assertEqual(len(app.view), 6)

    def test_filter_terms_anded(self) -> None:
        app = self.run_keys(["/"] + list("beta charlie") + ["\n", "q"])
        self.assertEqual([s.id for s in app.view], [C_ID])

    def test_tab_cycles_source(self) -> None:
        app = self.run_keys(["\t", "q"])
        self.assertEqual((app.source, len(app.view)), ("claude", 4))
        app = self.run_keys(["\t", "\t", "q"])
        self.assertEqual((app.source, len(app.view)), ("codex", 2))
        app = self.run_keys(["\t", "\t", "\t", "q"])
        self.assertEqual((app.source, len(app.view)), ("all", 6))
        self.assertTrue(self.scr.any_frame("filter: none"))

    def test_project_toggle(self) -> None:
        app = self.run_keys(["p", "q"])
        self.assertEqual(app.project, "/work/beta")
        self.assertEqual([s.id for s in app.view], [D_ID, C_ID])
        self.assertTrue(self.scr.any_frame("project=beta"))
        app = self.run_keys(["p", "p", "q"])
        self.assertIsNone(app.project)
        self.assertEqual(len(app.view), 6)

    def test_sort_toggle_keeps_selection(self) -> None:
        app = self.run_keys(["j", "j", "j", "s", "q"])
        self.assertEqual(app.sort, "start")
        self.assertEqual(app.current().id, X_ID)  # selection follows the session
        self.assertTrue(self.scr.any_frame("sort: start time"))
        app = self.run_keys(["s", "s", "q"])
        self.assertEqual(app.sort, "last")

    def test_toggles_show_in_header_and_status(self) -> None:
        app = self.run_keys(["t", "u", "q"])
        self.assertTrue(app.show_results and app.mine_only)
        self.assertTrue(self.scr.any_frame("tool results shown"))
        self.assertTrue(self.scr.any_frame("showing only your input"))
        self.assertTrue(self.scr.any_frame("[results]"))
        self.assertTrue(self.scr.any_frame("[mine]"))

    def test_resume(self) -> None:
        with mock.patch("os.path.isdir", return_value=True):
            app = self.run_keys(["j", "r"])
        self.assertEqual(app.resume.id, Y_ID)
        self.assertIsNone(app.resume_override)

    def test_resume_missing_cwd(self) -> None:
        app = self.run_keys(["r", "q"])
        self.assertIsNone(app.resume)
        self.assertTrue(self.scr.any_frame("cwd no longer exists: /work/beta"))

    def test_edit_resume(self) -> None:
        with mock.patch("os.path.isdir", return_value=True):
            app = self.run_keys(["e", "\n"])
            self.assertEqual(app.resume.id, D_ID)
            self.assertEqual(app.resume_override, ["claude", "--resume", D_ID])
            app = self.run_keys(["e", "\x15"] + list("mycmd --x {id}") + ["\n"])
            self.assertEqual(app.resume_override, ["mycmd", "--x", "{id}"])
        self.assertTrue(self.scr.any_frame("resume: mycmd --x {id}"))

    def test_edit_resume_cancel_and_bad_quote(self) -> None:
        with mock.patch("os.path.isdir", return_value=True):
            app = self.run_keys(["e", "\x1b", "q"])
            self.assertIsNone(app.resume)
            self.assertTrue(self.scr.any_frame("resume cancelled"))
            # a bad shlex line re-prompts with the text kept; then fix it
            app = self.run_keys(["e", "\x15", '"', "\n", "\x15", "x", "\n"])
            self.assertEqual(app.resume_override, ["x"])
            self.assertTrue(self.scr.any_frame("bad command"))
            # empty line cancels
            app = self.run_keys(["e", "\x15", "\n", "q"])
            self.assertIsNone(app.resume)

    def test_edit_missing_cwd(self) -> None:
        app = self.run_keys(["e", "q"])
        self.assertTrue(self.scr.any_frame("cwd no longer exists"))
        self.assertIsNone(app.resume)

    def test_copy(self) -> None:
        with mock.patch.object(ai, "copy_clipboard", return_value="fakeclip") as cc:
            self.run_keys(["y", "q"])
        cc.assert_called_once_with("cd /work/beta && claude --resume " + D_ID)
        self.assertTrue(self.scr.any_frame("copied via fakeclip"))
        with mock.patch.object(ai, "copy_clipboard", return_value=None):
            self.run_keys(["y", "q"])
        self.assertTrue(self.scr.any_frame("no clipboard tool found"))

    def test_rescan(self) -> None:
        app = self.make(["R", "q"])
        os.remove(self.fx("claude", "-work-beta", D_ID + ".jsonl"))
        app.run()
        self.assertEqual(len(app.view), 5)
        self.assertTrue(self.scr.any_frame("rescanned: 5 sessions"))

    def test_help(self) -> None:
        self.run_keys(["?", "x", "q"])
        self.assertTrue(self.scr.any_frame("ai-sessions - browse Claude Code and Codex transcripts"))
        self.assertTrue(self.scr.any_frame("Press any key to close."))
        self.assertTrue(self.scr.any_frame("Session list"))

    def test_help_scrolls_when_short(self) -> None:
        # On a short screen j scrolls the help instead of closing it; x then closes it.
        app = self.make(["?", "j", "x", "q"], h=12)
        app.run()
        self.assertTrue(self.scr.any_frame("j/k scroll"))
        helps = [f for f in self.scr.frames if "Press any key to close." in f]
        self.assertEqual(len(helps), 2)                 # before and after one j
        self.assertIn(ai.HELP_TITLE, helps[0])
        self.assertNotIn(ai.HELP_TITLE, helps[1])       # scrolled past the title

    def test_preview_scroll(self) -> None:
        # With a query the preview starts scrolled to the first hit (here: near the end),
        # so K scrolls up and J scrolls back down.
        app = self.make(["K", "q"], query="zebra", h=12)
        app.run()
        self.assertNotEqual(self.scr.frames[0], self.scr.frames[1])
        app = self.make(["K", "J", "q"], query="zebra", h=12)
        app.run()
        self.assertEqual(self.scr.frames[0], self.scr.frames[2])

    def test_viewer_open_and_back(self) -> None:
        app = self.run_keys(["\n", "q", "q"])
        self.assertTrue(self.scr.any_frame("q back"))
        app = self.run_keys(["v", "\x1b", "q"])
        self.assertTrue(self.scr.any_frame("q back"))

    def test_viewer_toggles_persist(self) -> None:
        app = self.run_keys(["\n", "t", "u", "q", "q"])
        self.assertTrue(app.show_results)
        self.assertTrue(app.mine_only)

    def test_viewer_scroll_keys(self) -> None:
        self.run_keys(["\n", "j", "k", " ", "b", "G", "g", curses.KEY_NPAGE, curses.KEY_PPAGE,
                       "q", "q"])
        self.run_keys(["\n"] + ["j"] * 30 + ["q", "q"], query="zebra")

    def test_viewer_search_and_hit_navigation(self) -> None:
        # "the" appears on three body lines of the alpha transcript
        self.run_keys(["\n", "/", "\x15"] + list("the") + ["\n", "n", "N", "N", "q", "q"],
                      query="zebra")
        frames = self.scr.frames
        want = ["hit 1/3", "hit 2/3", "hit 1/3", "hit 3/3"]  # after search, n, N, N (wraps)
        seen = [next(m for m in re.findall(r"hit \d/3", f) ) for f in frames
                if re.search(r"hit \d/3", f)]
        # collapse consecutive repeats (prompt redraws) and compare
        dedup = [x for i, x in enumerate(seen) if i == 0 or seen[i - 1] != x]
        self.assertEqual(dedup[:4], want)

    def test_viewer_initial_query_hits_and_no_hits(self) -> None:
        self.run_keys(["\n", "q", "q"], query="zebra")
        self.assertTrue(self.scr.any_frame("hit 1/1"))
        self.run_keys(["\n", "/", "\x15"] + list("nothingmatches") + ["\n", "q", "q"], query="zebra")
        self.assertTrue(self.scr.any_frame("no hits"))

    def test_viewer_search_cancel_keeps_query(self) -> None:
        self.run_keys(["\n", "/", "x", "\x1b", "q", "q"], query="zebra")
        self.assertTrue(self.scr.any_frame("hit 1/1"))
        self.assertFalse(self.scr.any_frame("no hits"))

    def test_viewer_resume(self) -> None:
        with mock.patch("os.path.isdir", return_value=True):
            app = self.run_keys(["j", "\n", "r"])
        self.assertEqual(app.resume.id, Y_ID)
        self.assertIsNone(app.resume_override)

    def test_viewer_resume_missing_cwd(self) -> None:
        app = self.run_keys(["\n", "r", "e", "q", "q"])
        self.assertIsNone(app.resume)
        self.assertTrue(self.scr.any_frame("cwd no longer exists: /work/beta"))

    def test_viewer_edit_resume(self) -> None:
        with mock.patch("os.path.isdir", return_value=True):
            app = self.run_keys(["\n", "e", "\x15"] + list("mycmd {id}") + ["\n"])
            self.assertEqual(app.resume.id, D_ID)
            self.assertEqual(app.resume_override, ["mycmd", "{id}"])
            self.assertTrue(self.scr.any_frame("resume: mycmd {id}"))
            app = self.run_keys(["\n", "e", "\x1b", "q", "q"])
            self.assertIsNone(app.resume)
            self.assertTrue(self.scr.any_frame("resume cancelled"))

    def test_viewer_copy(self) -> None:
        with mock.patch.object(ai, "copy_clipboard", return_value="fakeclip") as cc:
            self.run_keys(["\n", "y", "q", "q"])
        cc.assert_called_once_with("cd /work/beta && claude --resume " + D_ID)
        self.assertTrue(self.scr.any_frame("copied via fakeclip"))
        with mock.patch.object(ai, "copy_clipboard", return_value=None):
            self.run_keys(["\n", "y", "q", "q"])
        self.assertTrue(self.scr.any_frame("no clipboard tool found"))

    def test_viewer_help(self) -> None:
        app = self.run_keys(["\n", "?", "x", "q", "q"])
        self.assertTrue(self.scr.any_frame("Press any key to close."))
        self.assertIsNone(app.resume)

    def test_viewer_shows_results_when_toggled(self) -> None:
        self.run_keys(["\n", "t", "q", "q"], query="zebra")
        self.assertTrue(self.scr.any_frame("← line one"))

    def test_narrow_and_wide_layouts(self) -> None:
        app = self.run_keys(["j", "q"], w=80)
        frame = self.scr.frames[0]
        self.assertIn(ai.rule_chars()[0] * 20, frame)   # horizontal separator, stacked layout
        self.assertIn("ai-sessions", frame)
        self.run_keys(["j", "q"], w=99)
        self.run_keys(["j", "q"], w=100)
        self.assertIn(ai.rule_chars()[1], self.scr.frames[0])
        self.run_keys(["j", "\n", "q", "q"], w=60, h=14)

    def test_split_toggle(self) -> None:
        hz, vt = ai.rule_chars()
        app = self.run_keys(["l", "q"], w=80)  # auto-stacked at 80 cols -> list only
        self.assertEqual(app.split, "list")
        self.assertNotIn(vt, self.scr.frames[-1])
        self.assertNotIn(hz * 20, self.scr.frames[-1])
        self.assertTrue(self.scr.any_frame("layout: list only"))
        app = self.run_keys(["l", "l", "q"], w=80)  # list only -> side
        self.assertEqual(app.split, "side")
        self.assertIn(vt, self.scr.frames[-1])
        self.assertTrue(self.scr.any_frame("layout: list beside preview"))
        app = self.run_keys(["l", "q"], w=120)  # auto side at 120 cols -> stacked
        self.assertEqual(app.split, "stack")
        self.assertIn(hz * 20, self.scr.frames[-1])
        self.assertNotIn(vt, self.scr.frames[-1])
        app = self.run_keys(["l", "l", "l", "q"], w=120)  # full cycle back to side
        self.assertEqual(app.split, "side")

    def test_too_small_terminal(self) -> None:
        self.run_keys(["q"], h=5, w=20)
        self.assertTrue(self.scr.any_frame("terminal too small"))

    def test_empty_results(self) -> None:
        self.run_keys(["/"] + list("nomatchzzz") + ["\n", "\n", "r", "e", "y", "p", "q"])
        self.assertTrue(self.scr.any_frame("(no matching sessions)"))

    def test_ctrl_c_quits(self) -> None:
        self.run_keys(["\x03"])

    def test_last_column_fill_does_not_raise(self) -> None:
        # fill() paints the bottom-right cell with addch; FakeScr raises like curses would.
        self.run_keys(["q"], h=10, w=40)


if __name__ == "__main__":
    unittest.main()
