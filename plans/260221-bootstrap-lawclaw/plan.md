# LawClaw Bootstrap Plan

> The Governed AI Agent Framework — AI with Rule of Law

## Overview
Build a minimalist AI agent framework (~1500 lines) with "Separation of Powers" governance model. Only Telegram + OpenRouter. SQLite for persistence.

## Architecture
```
User ←→ Telegram ←→ Executive (Agent Loop) ←→ LLM (OpenRouter)
                         ↕                        ↕
                    Legislative              Judicial
                  (Skills/Laws)           (Audit/Veto)
                         ↕                        ↕
                       SQLite ←────────────────────┘
```

## Phases

| # | Phase | Status | Files |
|---|-------|--------|-------|
| 1 | Project scaffold & config | pending | [phase-01](phase-01-scaffold.md) |
| 2 | Core: LLM provider + tools | pending | [phase-02](phase-02-core.md) |
| 3 | Governance: Legislative + Judicial | pending | [phase-03](phase-03-governance.md) |
| 4 | Agent loop (Executive) | pending | [phase-04](phase-04-executive.md) |
| 5 | Telegram integration | pending | [phase-05](phase-05-telegram.md) |
| 6 | Cron scheduler | pending | [phase-06](phase-06-cron.md) |
| 7 | Testing & polish | pending | [phase-07](phase-07-testing.md) |

## Target Structure
```
lawclaw/
├── constitution.md          # Immutable rules
├── config.json              # API keys, settings
├── laws/                    # User-defined laws
├── skills/
│   ├── approved/            # Approved skills
│   ├── pending/             # Awaiting approval
│   └── banned/              # Banned skills
├── core/
│   ├── llm.py               # OpenRouter LLM client
│   ├── tools.py             # Tool registry + base
│   ├── agent.py             # Agent loop (Executive)
│   ├── legislative.py       # Skills/laws management
│   ├── judicial.py          # Pre-check + audit
│   ├── memory.py            # SQLite memory
│   ├── cron.py              # Scheduled tasks
│   └── subagent.py          # Sub-agent spawner
├── tools/                   # Built-in tools
│   ├── web_search.py
│   ├── web_fetch.py
│   └── exec_cmd.py
├── telegram.py              # Telegram bot
├── db.py                    # SQLite schema + helpers
└── main.py                  # Entry point
```

## Principles
- YAGNI: Only build what's needed for working demo
- KISS: ~1500 lines total, no over-engineering
- DRY: Reuse patterns, single source of truth
