module.exports = {
  apps: [
    {
      name: "lawclaw",
      script: "/Users/andie/Desktop/LawClaw/venv/bin/lawclaw",
      args: "gateway",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "claude-max-api-proxy",
      script: "dist/server/standalone.js",
      cwd: "/Users/andie/Desktop/LawClaw/claude-max-api-proxy",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      filter_env: ["CLAUDE_CODE", "CLAUDECODE"],
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
