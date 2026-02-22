# Judicial Rules

Enforcement rules for the Judicial branch. These are checked automatically
before every tool execution. If a rule is violated, the tool call is BLOCKED.

## Blocked Tools

Tools listed here are immediately blocked regardless of laws or constitution.
Use /ban <tool> to add, /approve <tool> to remove.

## Dangerous Patterns

Regex patterns matched against tool arguments. If any match, the call is blocked.

- `rm\s+-[rf]+\s+/` — rm -rf /
- `rm\s+-[rf]+\s+~` — rm -rf ~
- `rm\s+--no-preserve-root` — rm --no-preserve-root
- `mkfs\.` — format disk
- `dd\s+if=` — dd disk copy
- `:\(\)\s*\{.*:\|:&\s*\}` — fork bomb
- `DROP\s+TABLE` — SQL drop table
- `DROP\s+DATABASE` — SQL drop database
- `TRUNCATE\s+TABLE` — SQL truncate
- `shutdown\s+-[hH]` — system shutdown
- `halt\b` — halt system
- `poweroff\b` — power off
- `reboot\b` — reboot
- `format\s+[A-Za-z]:` — Windows format drive
- `del\s+/[Ss]\s+/[Qq]` — Windows delete all
- `chmod\s+-R\s+777\s+/` — chmod 777 root
- `chown\s+-R\s+.*\s+/` — chown root
- `>\s*/dev/sd[a-z]` — write to raw disk
- `curl.*\|\s*bash` — curl pipe to bash
- `wget.*\|\s*bash` — wget pipe to bash
- `base64\s+-d.*\|\s*bash` — base64 decode pipe to bash

## Workspace Sandbox

The `exec_cmd` tool is restricted to the workspace directory.
Any file path outside the workspace is blocked.
URLs (http://, https://) are excluded from path checking.
