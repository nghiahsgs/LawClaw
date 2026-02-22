# LawClaw

**The Governed AI Agent Framework — AI with Rule of Law**

LawClaw is an autonomous AI agent on Telegram, governed by "Song Quyền Phân Lập" (Two-Branch Separation of Powers). The AI self-regulates via Constitution + Laws, and a Judicial branch enforces rules automatically — like traffic cameras, no police needed.

## Architecture

```
                     ┌──────────────┐
                     │  CONSTITUTION │  (hiến pháp — broad rules)
                     │  constitution.md
                     └──────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              │                           │
       ┌──────▼──────┐            ┌──────▼──────┐
       │ LEGISLATIVE  │            │  JUDICIAL    │
       │              │            │              │
       │ laws/*.md    │            │ judicial.md  │
       │ (chi tiết    │            │ (enforcement │
       │  hoá hiến    │            │  + audit)    │
       │  pháp)       │            │              │
       └──────────────┘            └──────────────┘
              │                           │
              └───────────┬───────────────┘
                          │
                   ┌──────▼──────┐
                   │  AGENT LOOP  │  (just code, not a branch)
                   │  LLM → Tool  │
                   │  → Loop      │
                   └──────────────┘
```

### How Two-Branch Governance Works

| Layer | What | How | Analogy |
|-------|------|-----|---------|
| **Constitution** | Broad rules | Injected into system prompt → LLM follows them | National constitution |
| **Legislative** | Detailed laws | `laws/*.md` injected into prompt → LLM self-regulates | Traffic laws |
| **Judicial** | Enforcement | `judicial.md` defines blocked tools + dangerous patterns → auto-blocks | Traffic cameras (phạt nguội) |
| **Agent Loop** | Execution | LLM calls tools, loop until done | Citizen going about their day |

**The key insight:** Constitution + Laws guide the LLM's behavior (citizen consciousness). If the LLM still tries something dangerous, the Judicial branch blocks it automatically. No "Executive branch" needed — it's all automated enforcement.

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/nghiahsgs/LawClaw.git
cd LawClaw
pip install -e .

# 2. Set up secrets
cp .env.example .env
# Edit .env with your API keys

# 3. Start (auto-creates DB + config)
lawclaw gateway
```

## Configuration

### Secrets (`.env`)

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key     # OpenRouter models
ZAI_API_KEY=your-zai-key                   # Z.AI (Zhipu) models
TELEGRAM_TOKEN=123456:ABC-token
MODEL=glm-4.7                              # or anthropic/claude-sonnet-4-6
BRAVE_API_KEY=your-brave-key
```

Provider auto-detected from model name:
- `glm-*` → Z.AI (cheap, good for simple tasks)
- Everything else → OpenRouter (Sonnet, Gemini, Grok, etc.)

### Non-secret settings (`~/.lawclaw/config.json`)

```json
{
  "temperature": 0.7,
  "max_tokens": 4096,
  "max_iterations": 15,
  "memory_window": 40
}
```

## Governance Files

All governance lives in the repo root — version-controlled, easy to edit:

```
LawClaw/
├── constitution.md    # Hiến pháp — immutable broad rules
├── judicial.md        # Tư pháp — blocked tools + dangerous patterns
├── skills.md          # AI capabilities (not governance)
└── laws/              # Lập pháp — detailed laws
    ├── safety.md      # No destructive commands, no credential exposure
    ├── privacy.md     # No unauthorized data access
    └── conduct.md     # Behavior rules (language, confirmation, transparency)
```

### Constitution (`constitution.md`)

Broad, immutable rules: owner's rights, boundaries of power, resource limits, transparency, safety. The agent cannot modify this file.

### Laws (`laws/*.md`)

Detailed rules derived from the constitution. Add any `.md` file to `laws/` and it's automatically loaded into the system prompt. Examples: safety law, privacy law, conduct law.

### Judicial Rules (`judicial.md`)

Enforcement config read by the Judicial branch:
- **Blocked Tools** — tools listed here are immediately blocked (via `/ban`)
- **Dangerous Patterns** — regex patterns matched against tool arguments (rm -rf, DROP TABLE, curl|bash, etc.)
- **Workspace Sandbox** — `exec_cmd` restricted to workspace directory

### Skills (`skills.md`)

Just a capability listing — what the AI can do. Not governance. Skills are tools registered in code.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/new` | Start new session (old messages kept in DB) |
| `/audit` | View recent audit log (add `all` for all sessions) |
| `/skills` | List AI capabilities + blocked status |
| `/ban tool` | Block a tool via Judicial order |
| `/approve tool` | Unblock a tool |
| `/jobs` | List cron jobs |
| `/help` | Show all commands |

## How It Works

### Agent Flow

```
User (Telegram)
  │
  ▼
Agent.process(message)
  ├── 1. Load history from DB
  ├── 2. Build system prompt: Time + Constitution + Laws + Tools
  ├── 3. LLM call (OpenRouter or Z.AI)
  │
  ▼
LLM response: text OR tool_calls
  │
  ├── [tool_calls] → Judicial.pre_check()
  │     ├── Tool blocked? (judicial.md Blocked Tools)
  │     ├── Dangerous pattern? (judicial.md regex patterns)
  │     └── Path in workspace? (exec_cmd only)
  │          │
  │          ├── Allowed → execute → audit log → loop
  │          └── Blocked → "[BLOCKED]" → audit log → loop
  │
  └── [text] → save to DB → send to Telegram
```

### Cron Jobs

Each run gets a fresh session. State persisted via `manage_memory`:

```
CronService → on_cron_job(job_id, message, chat_id)
  ├── Load job memory (namespace: "job:{job_id}")
  ├── Inject memory into prompt
  ├── Agent.process() with unique session key
  ├── LLM uses tools + saves state via manage_memory
  └── Send result to Telegram
```

### Sub-agents

- Get base tools only (no `spawn_subagent` — prevents recursion)
- Share same constitution, judicial checks, LLM
- Max 5 iterations (vs 15 for main)

## Database

SQLite WAL mode. All tables auto-created on startup:

| Table | Purpose |
|-------|---------|
| `messages` | Chat history per session |
| `memory` | Key-value store, scoped by namespace |
| `audit_log` | Every tool call (allowed/blocked) |
| `cron_jobs` | Scheduled tasks |
| `skills` | _(deprecated — now in skills.md)_ |

Memory namespaces: `user:{chat_id}` for Telegram, `job:{job_id}` for cron.

## Project Structure

```
LawClaw/
├── constitution.md        # Hiến pháp
├── judicial.md            # Tư pháp enforcement rules
├── skills.md              # AI capabilities
├── laws/                  # Lập pháp detailed laws
│   ├── safety.md
│   ├── privacy.md
│   └── conduct.md
├── .env.example
├── pyproject.toml
└── lawclaw/
    ├── config.py          # Config + .env loader
    ├── db.py              # SQLite schema + helpers
    ├── main.py            # Entry point, wiring
    ├── telegram.py        # Telegram bot + commands
    ├── core/
    │   ├── agent.py       # Agent loop + system prompt
    │   ├── legislative.py # Load constitution + laws
    │   ├── judicial.py    # Pre-check veto + audit
    │   ├── llm.py         # Multi-provider LLM client
    │   ├── tools.py       # Tool registry + base class
    │   ├── subagent.py    # Sub-agent spawner
    │   └── cron.py        # Cron scheduler
    └── tools/
        ├── web_search.py
        ├── web_fetch.py
        ├── exec_cmd.py
        ├── spawn_subagent.py
        ├── manage_cron.py
        └── manage_memory.py
```

## Tech Stack

- **Python** 3.11+ (~2000 lines, no frameworks)
- **LLM**: OpenRouter + Z.AI (auto-detected from model name)
- **Database**: SQLite (WAL mode, auto-migration)
- **Telegram**: python-telegram-bot
- **HTTP**: httpx (async)
- **Search**: Brave Search API

## License

MIT
