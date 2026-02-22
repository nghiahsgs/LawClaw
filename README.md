# LawClaw

**The Governed AI Agent Framework — AI with Rule of Law**

LawClaw is an autonomous AI agent on Telegram, governed by separation of powers. Three governance layers: Constitution + Legislative define the rules (injected into system prompt — LLM self-regulates), and Pre-Judicial enforces them automatically before tool execution — like traffic cameras, no police needed.

## Architecture

```
    ┌───────────────────────────────────────────┐
    │            BEFORE LLM CALL                │
    │                                           │
    │  ┌──────────────┐    ┌──────────────┐     │
    │  │ CONSTITUTION  │    │ LEGISLATIVE   │    │
    │  │ constitution  │    │ laws/*.md     │    │
    │  │ .md (broad     │    │ (detailed      │    │
    │  │ rules)        │    │ laws)          │    │
    │  └──────┬────────┘    └──────┬────────┘    │
    │         └────────┬───────────┘             │
    │                  ▼                         │
    │        System Prompt → LLM                 │
    └───────────────────────────────────────────┘
                       │
                  LLM Output (tool_calls)
                       │
    ┌──────────────────▼────────────────────────┐
    │          BEFORE TOOL EXECUTION            │
    │                                           │
    │  ┌──────────────────────────────────┐     │
    │  │       PRE-JUDICIAL                │     │
    │  │       judicial.md                 │     │
    │  │       (automated enforcement)      │     │
    │  │                                   │     │
    │  │  • Blocked tools?                 │     │
    │  │  • Dangerous patterns?            │     │
    │  │  • Path in workspace?             │     │
    │  └──────────────┬────────────────────┘     │
    │          allowed │ blocked                 │
    └─────────────────┼─────────────────────────┘
                      ▼
               ┌──────────────┐
               │  AGENT LOOP   │  (just code)
               │  Execute Tool │
               │  → Loop       │
               └──────────────┘
```

### How Three-Layer Governance Works

| Layer | When | What | How | Analogy |
|-------|------|------|-----|---------|
| **Constitution** | Before LLM call | Broad immutable rules | Injected into system prompt | National constitution |
| **Legislative** | Before LLM call | Detailed laws | `laws/*.md` injected into prompt → LLM self-regulates | Traffic laws |
| **Pre-Judicial** | Before tool execution | Enforcement | Checks LLM output → auto-blocks violations | Traffic cameras |
| **Agent Loop** | Runtime | Execution | LLM calls tools, loop until done | Citizen going about their day |

**The key insight:** Constitution + Laws guide the LLM's behavior BEFORE it acts (citizen consciousness). Pre-Judicial checks the LLM's OUTPUT before actual execution. No "Executive branch" or police needed — just automated enforcement like traffic cameras.

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
MODEL=claude-opus-4-local                  # See model options below
BRAVE_API_KEY=your-brave-key
```

Provider auto-detected from model name:

| Model | Provider | Cost |
|-------|----------|------|
| `claude-opus-4-local` | Claude Max proxy (localhost:3456) | Free (Max subscription) |
| `claude-sonnet-4-local` | Claude Max proxy (localhost:3456) | Free (Max subscription) |
| `glm-4.7` | Z.AI | Cheap |
| `anthropic/claude-sonnet-4-6` | OpenRouter | Pay per token |
| `google/gemini-2.5-flash` | OpenRouter | Cheap |

**Suffix `-local`** routes to a local Claude Max proxy. See [Claude Max Proxy](#claude-max-proxy) for setup.

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
├── constitution.md    # Immutable broad rules (→ system prompt)
├── judicial.md        # Pre-Judicial — blocked tools + dangerous patterns (→ pre-check)
├── laws/              # Detailed laws (→ system prompt)
│   ├── safety.md
│   ├── privacy.md
│   └── conduct.md
└── skills/            # Skill playbooks — HOW to use tools (→ system prompt)
    ├── web-search.md
    ├── cron-jobs.md
    └── memory-management.md
```

### Constitution (`constitution.md`)

Broad, immutable rules: owner's rights, boundaries of power, resource limits, transparency, safety. The agent cannot modify this file.

### Laws (`laws/*.md`)

Detailed rules derived from the constitution. Add any `.md` file to `laws/` and it's automatically loaded into the system prompt. Examples: safety law, privacy law, conduct law.

### Pre-Judicial Rules (`judicial.md`)

Enforcement config read by the Pre-Judicial layer — checked AFTER LLM output, BEFORE tool execution:
- **Blocked Tools** — tools listed here are immediately blocked (via `/ban`)
- **Dangerous Patterns** — regex patterns matched against tool arguments (rm -rf, DROP TABLE, curl|bash, etc.)
- **Workspace Sandbox** — `exec_cmd` restricted to workspace directory

### Skills (`skills/`)

Directory of playbooks — describe HOW to use each tool effectively. Not governance. Loaded into system prompt so the LLM knows best practices for web search, cron jobs, memory, etc. Add any `.md` file to `skills/`.

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
  ├── 2. Build system prompt: Time + Constitution + Laws + Skills + Tools
  ├── 3. LLM call (OpenRouter or Z.AI)
  │
  ▼
LLM response: text OR tool_calls
  │
  ├── [tool_calls] → PreJudicial.pre_check()
  │     ├── Tool blocked? (judicial.md Blocked Tools)
  │     ├── Dangerous pattern? (judicial.md regex)
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
|

Memory namespaces: `user:{chat_id}` for Telegram, `job:{job_id}` for cron.

## Project Structure

```
LawClaw/
├── constitution.md        # Broad rules (immutable)
├── judicial.md            # Pre-Judicial enforcement rules
├── skills/                # Skill playbooks (how to use tools)
├── laws/                  # Legislative — detailed laws
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
    │   ├── judicial.py    # Pre-Judicial enforcement + audit
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

## Claude Max Proxy

If you have a Claude Max subscription ($200/month), you can run Claude Opus/Sonnet for free via a local proxy:

```bash
# 1. Install Claude Code CLI and authenticate
npm install -g @anthropic-ai/claude-code
claude auth login

# 2. Clone and start the proxy
git clone https://github.com/atalovesyou/claude-max-api-proxy.git
cd claude-max-api-proxy
npm install && npm run build
npm start
# Proxy runs at http://localhost:3456

# 3. Set MODEL in .env
MODEL=claude-opus-4-local
```

The proxy wraps Claude Code CLI as an OpenAI-compatible API server. LawClaw auto-detects the `-local` suffix and routes requests to `localhost:3456`.

## Tech Stack

- **Python** 3.11+ (~2000 lines, no frameworks)
- **LLM**: OpenRouter, Z.AI, or Claude Max proxy (auto-detected from model name)
- **Database**: SQLite (WAL mode, auto-migration)
- **Telegram**: python-telegram-bot
- **HTTP**: httpx (async)
- **Search**: Brave Search API

## License

MIT
