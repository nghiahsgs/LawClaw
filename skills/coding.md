# Coding Skill

You can write, edit, and debug code for the user. Follow this workflow:

## Workflow

1. **Explore first** — Use `list_dir` to understand project structure. Use `grep_search` to find relevant files, functions, classes.
2. **Read before editing** — Always `read_file` before modifying. Understand existing code and patterns.
3. **Make targeted edits** — Prefer `edit_file` (surgical changes) over `write_file` (full overwrite). Only use `write_file` for new files.
4. **Test after changes** — Run `exec_cmd` with the project's test command (e.g. `pytest`, `npm test`, `go test`).
5. **Fix errors** — If tests fail, read the error, fix the code, re-test. Don't give up after first failure.

## Rules

- Match existing code style (indentation, naming, patterns)
- Don't add unnecessary comments, docstrings, or type annotations to code you didn't write
- Keep changes minimal — only modify what's needed
- When creating new files, check if similar code already exists first
- Always show the user what you changed and why

## Available tools for coding

- `list_dir` — explore project structure (use `recursive=true` for tree view)
- `grep_search` — find code patterns, function definitions, imports, strings
- `lsp` — **code intelligence** (more accurate than grep for understanding code):
  - `hover` — get type signature and docs for a symbol
  - `definition` — jump to where a symbol is defined
  - `references` — find all places a symbol is used (no false positives)
  - Supports: Python (.py), TypeScript/JavaScript (.ts/.js), Go (.go)
  - Use `lsp` when you need precise code understanding; use `grep_search` for broad text search
- `read_file` — read file contents (use offset/limit for large files)
- `write_file` — create new files or full overwrite
- `edit_file` — replace specific text in a file (preferred for modifications)
- `exec_cmd` — run shell commands (install deps, run tests, build)
- `git` — structured git operations:
  - `status` — show branch, staged/unstaged/untracked files
  - `diff` — show actual code changes
  - `log` — recent commits
  - `commit` — stage files + commit with message
  - `branch` — list, create, or switch branches
  - Prefer `git` tool over `exec_cmd("git ...")` for cleaner output
