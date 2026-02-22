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
| **Legislative** | What the agent *can* do | Skill approval registry (`skills` table), laws from `~/.lawclaw/laws/` |
| **Executive** | Does the work | Agent loop, tool calls, sub-agents, cron scheduler |
| **Judicial** | What the agent *should* do | Dangerous pattern blocking, workspace sandbox, audit trail |

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/nghiahsgs/LawClaw.git
cd LawClaw
pip install -e .

# 2. Set up secrets
cp .env.example .env
# Edit .env with your API keys

# 3. Start (auto-creates DB, tables, config, constitution)
lawclaw gateway
```

That's it. No migration needed — `lawclaw gateway` automatically:
- Creates `~/.lawclaw/` directory + `config.json` + `constitution.md`
- Creates SQLite DB with all 5 tables (`CREATE TABLE IF NOT EXISTS`)
- Auto-approves all built-in tools

## Configuration

### Secrets (`.env`)

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
TELEGRAM_TOKEN=123456:ABC-your-bot-token-here
MODEL=anthropic/claude-sonnet-4-6
BRAVE_API_KEY=your-brave-api-key-here
```

Priority: `ENV vars` > `CWD/.env` > `~/.lawclaw/.env`

Supported models (via OpenRouter):
- `anthropic/claude-sonnet-4-6` — recommended, best tool calling
- `anthropic/claude-opus-4-6` — most capable, expensive
- `google/gemini-2.5-flash` — cheap, fast, but overly cautious
- `x-ai/grok-3` — good alternative
- Any OpenRouter model with tool calling support

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

## CLI Commands

```bash
lawclaw gateway    # Start Telegram bot + Cron scheduler
lawclaw chat MSG   # Send a single message via CLI
lawclaw init       # Initialize config files only
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
| `web_search` | Search the web via Brave Search API | `BRAVE_API_KEY` |
| `web_fetch` | Fetch & extract readable text from any URL | - |
| `exec_cmd` | Execute shell commands (sandboxed to workspace) | - |
| `spawn_subagent` | Delegate complex tasks to sub-agents | - |
| `manage_cron` | Create/remove/list recurring scheduled jobs | - |
| `manage_memory` | Persist key-value state across sessions & cron runs | - |

## How It Works

### Main Agent Flow

```
User (Telegram)
  │
  ▼
Agent.process(message, session_key)
  │
  ├── 1. Load history from `messages` table (last 40)
  ├── 2. Build system prompt: Time + Constitution + Laws + Tools + Capabilities
  ├── 3. Send to LLM via OpenRouter
  │
  ▼
LLM response: text OR tool_calls
  │
  ├── [tool_calls] → Judicial.pre_check()
  │     ├── Skill approved? (Legislative)
  │     ├── Dangerous pattern? (regex: rm -rf, DROP TABLE, curl|bash, etc.)
  │     └── Path within workspace? (exec_cmd only)
  │          │
  │          ├── Allowed → execute → log audit → return result → loop
  │          └── Blocked → "[BLOCKED] reason" → log audit → loop
  │
  └── [text] → save to `messages` → send to Telegram
```

### Cron Jobs

Each cron run gets a fresh session (no history pollution). State persisted via `manage_memory`:

```
CronService (checks every 10s)
  │
  ├── Find jobs WHERE next_run_at <= now
  │
  ▼
on_cron_job(job_id, message, chat_id)
  ├── Read job's memory from DB (namespace: "job:{job_id}")
  ├── Inject memory into prompt
  ├── Agent.process() with fresh session key
  ├── LLM executes tools + saves state via manage_memory
  ├── Send result to Telegram chat
  └── Schedule next_run_at = now + interval
```

### Sub-agents

Main agent can spawn sub-agents for parallel task delegation:
- Sub-agents get base tools only (`web_search`, `web_fetch`, `exec_cmd`)
- No `spawn_subagent` tool (prevents infinite recursion)
- Share the same constitution, judicial checks, and LLM
- Max 5 iterations per sub-agent (vs 15 for main)
- Stateless — no message persistence

## Database

SQLite with WAL mode. All tables auto-created on startup via `CREATE TABLE IF NOT EXISTS`:

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `messages` | Chat history per session | `session_key`, `role`, `content` |
| `memory` | Key-value store, scoped by namespace | `key` (format: `{namespace}:{name}`), `value` |
| `audit_log` | Every tool call (allowed/blocked) | `tool_name`, `arguments`, `result`, `verdict` |
| `cron_jobs` | Scheduled tasks | `name`, `message`, `interval`, `chat_id` |
| `skills` | Tool approval registry | `name`, `status` (approved/pending/banned) |

Memory namespaces:
- `user:{chat_id}` — Telegram user's persistent memory (survives `/new`)
- `job:{job_id}` — Cron job's state (auto-injected into prompt each run)

## Project Structure

```
LawClaw/
├── .env.example           # Secrets template
├── .gitignore
├── constitution.md        # Immutable governance rules
├── pyproject.toml         # Build config + dependencies
└── lawclaw/
    ├── config.py          # Config + .env loader (ENV > .env > config.json)
    ├── db.py              # SQLite schema + helpers (5 tables)
    ├── main.py            # Entry point, dependency wiring
    ├── telegram.py        # Telegram bot + commands
    ├── core/
    │   ├── agent.py       # Executive: agent loop + system prompt
    │   ├── legislative.py # Legislative: skill approval + laws loader
    │   ├── judicial.py    # Judicial: pre-check veto + audit logger
    │   ├── llm.py         # OpenRouter API client
    │   ├── tools.py       # Tool registry + base class
    │   ├── subagent.py    # Ephemeral sub-agent spawner
    │   └── cron.py        # Cron scheduler (SQLite-backed)
    └── tools/
        ├── web_search.py     # Brave Search API
        ├── web_fetch.py      # HTTP GET + HTML-to-text extraction
        ├── exec_cmd.py       # Shell execution (workspace sandbox)
        ├── spawn_subagent.py # Sub-agent delegation tool
        ├── manage_cron.py    # Cron job CRUD (add/remove by name or ID/list)
        └── manage_memory.py  # Persistent key-value store (namespaced)
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
main_tools.register(MyTool())
```

If `auto_approve_builtin_skills = true`, tool is auto-approved. Otherwise owner must `/approve my_tool`.

## Constitution

The constitution (`constitution.md`) defines immutable rules that the agent cannot override:

1. **Owner's rights** — Agent cannot deceive or withhold info from owner
2. **Boundaries** — No unapproved tools, no files outside workspace, no unauthorized messages
3. **Resource limits** — Tool exec < 120s, agent loop < 15 iterations, cron interval >= 60s
4. **Transparency** — Every tool call audited, owner can review via `/audit`
5. **Skill governance** — New skills require approval, owner can `/ban` any skill
6. **Safety** — Dangerous patterns always blocked (rm -rf, DROP TABLE, curl|bash, etc.)

## Tech Stack

- **Python** 3.11+ (~2000 lines, no frameworks)
- **LLM**: OpenRouter (any model with tool calling)
- **Database**: SQLite (WAL mode, auto-migration)
- **Telegram**: python-telegram-bot
- **HTTP**: httpx (async)
- **Search**: Brave Search API
- **Logging**: loguru

## License

MIT
