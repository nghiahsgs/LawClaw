# LawClaw

**The Governed AI Agent Framework — AI with Rule of Law**

LawClaw applies the separation of powers principle to AI agent governance. Every action is checked, logged, and auditable.

## Architecture

```
                     ┌──────────────┐
                     │  CONSTITUTION │  (immutable rules)
                     └──────┬───────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │ LEGISLATIVE  │   │  EXECUTIVE   │   │  JUDICIAL    │
  │              │   │              │   │              │
  │ Skill        │   │ Agent Loop   │   │ Pre-check    │
  │ Approval     │   │ Tool Exec    │   │ Audit Log    │
  │ Laws         │   │ Sub-agents   │   │ Veto Engine  │
  └──────────────┘   └──────────────┘   └──────────────┘
```

**Three Branches:**

| Branch | Role | Examples |
|--------|------|----------|
| **Legislative** | Decides what the agent *can* do | Approve/ban skills, load laws |
| **Executive** | Does the work | Agent loop, tool calls, sub-agents |
| **Judicial** | Decides what the agent *should* do | Block dangerous commands, audit trail |

## Quick Start

```bash
# Install
pip install -e .

# Initialize config
lawclaw init

# Edit config with your keys
vim ~/.lawclaw/config.json

# Start Telegram bot
lawclaw gateway

# Or send a single message
lawclaw chat "What is the weather in Hanoi?"
```

## Configuration

Edit `~/.lawclaw/config.json`:

```json
{
  "openrouter_api_key": "sk-or-...",
  "model": "anthropic/claude-sonnet-4",
  "telegram_token": "123456:ABC...",
  "telegram_allow_from": ["your_user_id"],
  "auto_approve_builtin_skills": true
}
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/new` | Start new session |
| `/audit` | View recent audit log |
| `/skills` | List skill statuses |
| `/approve name` | Approve a pending skill |
| `/ban name` | Ban a skill |
| `/jobs` | List cron jobs |
| `/help` | Show commands |

## Built-in Tools

- **web_search** — Brave Search API
- **web_fetch** — Fetch and extract webpage content
- **exec_cmd** — Execute shell commands (sandboxed to workspace)

## Constitution

The constitution (`~/.lawclaw/constitution.md`) defines immutable rules the agent cannot override:

- Agent cannot modify its own constitution
- Every tool call is audited
- Dangerous commands (rm -rf, DROP TABLE, etc.) are always blocked
- New skills require owner approval
- The agent must never deceive the owner

## How It Works

1. User sends message via Telegram (or CLI)
2. **Legislative** branch loads approved skills and laws into system prompt
3. **Executive** branch (agent loop) calls LLM with tools
4. When LLM requests a tool call, **Judicial** branch runs pre-check:
   - Is the skill approved? (Legislative check)
   - Does it match dangerous patterns? (Safety check)
   - Is the path within workspace? (Boundary check)
5. If approved → execute tool, log result
6. If blocked → return `[BLOCKED]` reason to LLM
7. Loop until LLM produces final response
8. All actions logged to audit trail

## Project Structure

```
lawclaw/
├── config.py          # Config loader (~/.lawclaw/config.json)
├── db.py              # SQLite schema + helpers
├── main.py            # CLI entry point
├── telegram.py        # Telegram bot integration
├── core/
│   ├── agent.py       # Executive: agent loop
│   ├── legislative.py # Legislative: skill approval + laws
│   ├── judicial.py    # Judicial: pre-check + audit
│   ├── llm.py         # OpenRouter LLM client
│   ├── tools.py       # Tool registry + ABC
│   ├── subagent.py    # Ephemeral sub-agent spawner
│   └── cron.py        # Cron scheduler
└── tools/
    ├── web_search.py  # Brave Search tool
    ├── web_fetch.py   # URL fetch tool
    └── exec_cmd.py    # Shell execution tool
```

## Adding Custom Tools

```python
from lawclaw.core.tools import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input value"}
        },
        "required": ["input"],
    }

    async def execute(self, input: str) -> str:
        return f"Result: {input}"
```

Register in `main.py`:
```python
tools.register(MyTool())
```

New tools start as "pending" and require owner approval via `/approve my_tool`.

## Tech Stack

- **LLM**: OpenRouter (any model with tool calling)
- **Database**: SQLite (WAL mode)
- **Telegram**: python-telegram-bot
- **HTTP**: httpx (async)
- **Logging**: loguru

~1700 lines of Python. No frameworks. No magic.

## License

MIT
