# MCP Skill Invocation Issue: `skill-react-game-enhancer`

## Symptoms
- Invoking `startd8_use_skill` for `skill-react-game-enhancer` fails with:  
  `Can't instantiate abstract class ClaudeSkillAgent without an implementation for abstract method 'agenerate'`.
- At one point, calling `startd8_use_skill` for `html5-game-designer-pro` hit an Anthropic logging error:  
  `"Attempt to overwrite 'name' in LogRecord"`.
- Server logs show startup info but no per-call `[mcp-debug]` lines for the failing calls, suggesting the client may not be hitting the intended server process or the call is failing before debug prints.

## Current server startup (working env)
Command (runs in venv, loads SDK and skills correctly):
```
cd /Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder && \
PYTHONPATH=/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src \
STARTD8_SDK_PATH=/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src \
STARTD8_SKILL_PATH=/Users/neilyashinsky/Documents/FMLs/dev/version2 \
ALLOWED_AGENTS=mock DEFAULT_AGENT=mock \
.venv/bin/python startd8_mcp.py
```
Startup banner shows:
- `SkillAgent` and `ClaudeSkillAgent` loaded from `startd8.skills.agent`
- `Resolved agent class: <class 'startd8.skills.agent.SkillAgent'>`
- SDK path points to the local SDK source

## What we tried
1) Ensured SDK path on `PYTHONPATH`/`STARTD8_SDK_PATH`; confirmed `SkillAgent` and `ClaudeSkillAgent` instantiate in this env.
2) Added debug logs in `startd8_use_skill` to print agent class and failures (agent instantiation/generate). No per-call logs appeared during failing calls, implying the client may be pointing to a different/stale server invocation or failing before debug.
3) Set `STARTD8_SKILL_PATH` to `/Users/neilyashinsky/Documents/FMLs/dev/version2`; skills discovered: `html5-game-designer-pro` and `skill-react-game-enhancer`.
4) Retried `startd8_use_skill`:
   - For `skill-react-game-enhancer`: still get abstract-class error.
   - For `html5-game-designer-pro`: hit Anthropic logging error `"Attempt to overwrite 'name' in LogRecord"`.
5) Restarted server multiple times; ensured banner reflects correct SDK/skill paths; no per-call debug lines on failure.

## Suspected issues
- MCP client may be invoking a different command (e.g., `python3 startd8_mcp.py` without PYTHONPATH), so requests hit a stale server that doesn’t resolve the concrete agent.
- The SDK agent path might still be abstract in the code path the client hits; or the logging error from Anthropic may be throwing before debug prints.
- Debug logs in `startd8_use_skill` aren’t appearing, reinforcing that the running server receiving calls is not the one started with the debug-enabled binary.

## Quick repro / verification steps for fresh eyes
1) Start the server with the command above; keep terminal open; verify banner shows `SkillAgent` loaded and `Resolved agent class: <class 'startd8.skills.agent.SkillAgent'>`.
2) Ensure MCP client config points to this exact command (e.g., `/bin/sh -lc "<command above>"`).
3) Set `ANTHROPIC_API_KEY` in the same env.
4) Invoke `startd8_use_skill` for `skill-react-game-enhancer` and watch terminal for `[mcp-debug]` lines:
   - Expect: `[mcp-debug] startd8_use_skill ... agent_cls=<class ...>`; if failure, see `agent instantiation failed` or `agent.generate failed`.
5) If still abstract-class error and no debug lines, the request isn’t reaching this server process. Check client command and any cached MCP server configs.

## Potential short-term workaround
- Force `startd8_use_skill` to always use the Anthropic fallback (skip SDK agent) and suppress logging metadata collisions. This would bypass the abstract-class issue while we align the SDK agent.

## Files/paths of interest
- Server code: `startd8_mcp.py` (debug prints added in `startd8_use_skill`)
- SDK source: `/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src/startd8/skills/agent.py`
- Skills path: `/Users/neilyashinsky/Documents/FMLs/dev/version2/skill-react-game-enhancer`
- MCP config (if needed): `cursor-mcp-config.json` (ensure command matches startup above)
