# Cron Jobs

How to create and manage recurring scheduled tasks.

## When to use
- User asks "send me X every N minutes"
- User wants automated monitoring, alerts, or reports

## How it works
1. Use `manage_cron` with action="add" to create a job
2. Each run gets a fresh session (no history pollution)
3. Use `manage_memory` to persist state across runs (namespace: job:{id})
4. Previous memory is auto-injected into the prompt

## Best practices
- Keep cron job messages clear and self-contained
- Always save important state via `manage_memory` at end of each run
- Use `web_fetch` with APIs instead of `web_search` for real-time data in cron jobs
- Minimum interval: 60 seconds (constitution limit)
