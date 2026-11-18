---
name: star-session
description: Star, unstar, or check the star status of the current Claude Code / Codex session in ai-sessions so it is easy to find later. Use when the user asks to star, unstar, bookmark, favorite or pin this session/conversation, or asks whether it is starred.
argument-hint: "[off | --status]"
---

# Star the current session

Run exactly one of these with the shell tool (no session id needed; ai-sessions reads it from CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID):

- To star (no arguments, or arguments like "on"): `ai-sessions --star`
- To unstar (arguments like "off", "remove", "unstar", or the user asked to unstar): `ai-sessions --unstar`
- To check without changing anything (arguments like "--status", "status", "?", or the user asked whether it is starred): `ai-sessions --star-status`

Report the line it prints in one short sentence. If `ai-sessions` is not found on PATH, tell the user to install it (see the ai-sessions README). Do nothing else.
