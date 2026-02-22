# LawClaw

**The Governed AI Agent Framework — AI with Rule of Law**

LawClaw is an autonomous AI agent that runs on Telegram, governed by a "Separation of Powers" architecture. Every action is checked, logged, and auditable.

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

| Branch | Role | Implementation |
|--------|------|----------------|
| **Legislative** | What the agent *can* do | Skill approval registry, laws |
| **Executive** | Does the work | Agent loop, tool calls, sub-agents, cron |
| **Judicial** | What the agent *should* do | Dangerous pattern blocking, path sandbox, audit trail |

## Quick Start

```bash
# Clone & install
git clone https://github.com/nghiahsgs/LawClaw.git
cd LawClaw
pip install -e .

# Initialize config
lawclaw init

# Set up secrets in .env (at repo root or ~/.lawclaw/.env)
cp .env.example .env
# Edit .env with your keys

# Start Telegram bot + Cron
lawclaw gateway

# Or send a single message via CLI
lawclaw chat "What is the weather in Hanoi?"
```

## Configuration

### Secrets (`.env`)

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
TELEGRAM_TOKEN=123456:ABC-your-bot-token-here
MODEL=anthropic/claude-sonnet-4-6
BRAVE_API_KEY=your-brave-api-key-here
```

Priority: `ENV vars` > `CWD/.env` > `~/.lawclaw/.env`

### Non-secret settings (`~/.lawclaw/config.json`)

```json
{
  "temperature": 0.7,
  "max_tokens": 4096,
  "max_iterations": 15,
  "memory_window": 40,
  "auto_approve_builtin_skills": true
}
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/new` | Start new session (old messages kept in DB) |
| `/audit` | View recent audit log |
| `/skills` | List skill approval statuses |
| `/approve name` | Approve a pending skill |
| `/ban name` | Ban a skill |
| `/jobs` | List cron jobs |
| `/help` | Show all commands |

## Built-in Tools

| Tool | Description | Requires |
|------|-------------|----------|
| `web_search` | Brave Search API | `BRAVE_API_KEY` |
| `web_fetch` | Fetch & extract webpage text | - |
| `exec_cmd` | Shell commands (sandboxed to workspace) | - |
| `spawn_subagent` | Delegate tasks to sub-agents | - |
| `manage_cron` | Create/remove/list scheduled jobs | - |
| `manage_memory` | Persist key-value state across runs | - |

## How It Works

### Main Agent Flow

```
User (Telegram) → Agent.process()
  1. Load chat history from DB (last 40 messages)
  2. Build system prompt: Constitution + Laws + Tools + Time
  3. Send to LLM via OpenRouter
  4. LLM returns tool_calls → Judicial pre-check:
     - Skill approved? (Legislative)
     - Dangerous pattern? (regex blocklist)
     - Path within workspace? (sandbox)
  5. Allowed → execute tool → log audit → loop
     Blocked → "[BLOCKED] reason" → log audit → loop
  6. LLM final text → save to DB → send to Telegram
```

### Cron Jobs

Each cron run gets a fresh session (no history pollution). Memory is persisted via `manage_memory` tool:

```
CronService (tick every 10s)
  → Load job's persisted memory from DB
  → Inject memory into prompt
  → Agent.process() with fresh session
  → LLM uses tools + saves state via manage_memory
  → Send result to Telegram chat
```

### Sub-agents

Main agent can spawn sub-agents for parallel tasks. Sub-agents get base tools only (no `spawn_subagent` — prevents recursion). They share the same constitution and judicial checks.

## Database (SQLite)

| Table | Purpose |
|-------|---------|
| `messages` | Chat history per session |
| `memory` | Key-value store, scoped by namespace (`user:{id}`, `job:{id}`) |
| `audit_log` | Every tool call — allowed or blocked, with args + result |
| `cron_jobs` | Scheduled tasks with interval, status, chat_id |
| `skills` | Tool approval registry (approved/pending/banned) |

## Project Structure

```
LawClaw/
├── .env.example           # Secrets template
├── constitution.md        # Immutable governance rules
├── pyproject.toml         # Build config
├── plans/                 # Implementation plans
└── lawclaw/
    ├── config.py          # Config + .env loader
    ├── db.py              # SQLite schema + helpers
    ├── main.py            # Entry point, wiring
    ├── telegram.py        # Telegram bot
    ├── core/
    │   ├── agent.py       # Executive: agent loop
    │   ├── legislative.py # Legislative: skill approval + laws
    │   ├── judicial.py    # Judicial: pre-check + audit
    │   ├── llm.py         # OpenRouter LLM client
    │   ├── tools.py       # Tool registry + base class
    │   ├── subagent.py    # Ephemeral sub-agent spawner
    │   └── cron.py        # Cron scheduler
    └── tools/
        ├── web_search.py     # Brave Search
        ├── web_fetch.py      # URL content fetcher
        ├── exec_cmd.py       # Shell execution (sandboxed)
        ├── spawn_subagent.py # Sub-agent delegation
        ├── manage_cron.py    # Cron job CRUD
        └── manage_memory.py  # Persistent key-value store
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

Register in `main.py` → new tools start as "pending" → owner approves via `/approve my_tool`.

## Constitution

The constitution (`constitution.md`) defines immutable rules:

- Agent cannot modify its own constitution
- Every tool call is audited
- Dangerous commands (rm -rf, DROP TABLE, etc.) are always blocked
- New skills require owner approval
- Agent must never deceive the owner
- No tool execution > 120s, no agent loop > 15 iterations, no cron < 60s interval

## Tech Stack

- **LLM**: OpenRouter (any model — Claude, Gemini, Grok, etc.)
- **Database**: SQLite with WAL mode
- **Telegram**: python-telegram-bot
- **HTTP**: httpx (async)
- **Search**: Brave Search API
- **Logging**: loguru

~2000 lines of Python. No frameworks. No magic.

## License

MIT
