# Memory Management

How to persist and retrieve state using `manage_memory`.

## Namespaces
- `user:{chat_id}` — Telegram user memory (persists across /new)
- `job:{job_id}` — Cron job memory (auto-scoped per job)

## Actions
- `set` — Save a key-value pair
- `get` — Retrieve a value by key
- `list` — List all keys in current namespace
- `delete` — Remove a key

## Best practices
- Use JSON strings for complex state (portfolios, configs)
- Keep keys descriptive: "btc_portfolio", "last_check_time"
- For cron jobs: always save state at end of run, read at start
- Don't store large data — memory is for small state, not logs
