# Git Operations

How to run git commands using `exec_cmd`.

## URL Priority

Always prefer **SSH** over HTTPS when interacting with GitHub:

- SSH: `git@github.com:owner/repo.git`
- HTTPS (fallback): `https://github.com/owner/repo.git`

If the user provides an HTTPS URL like `https://github.com/owner/repo`, convert it to SSH:
`git@github.com:owner/repo.git`

## Clone

Always clone into the workspace directory:

```
exec_cmd command="git clone git@github.com:owner/repo.git"
```

This will clone into `~/.lawclaw/workspace/repo/`.

## Push / Pull

```
exec_cmd command="cd repo-name && git pull"
exec_cmd command="cd repo-name && git push"
```

## Tips

- If SSH fails with "Permission denied (publickey)", fall back to HTTPS URL
- All git commands run inside the workspace directory automatically
- Use `git status` to check repo state before making changes
