module.exports = {
  apps: [
    {
      name: "claude-max-proxy",
      script: "dist/server/standalone.js",
      cwd: "/root/LawClaw/claude-max-api-proxy",
      node_args: "--experimental-vm-modules",
      env: {
        NODE_ENV: "production",
        PORT: 3456,
        CLAUDECODE: "",
        CLAUDE_CODE_ENTRYPOINT: "",
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
    },
  ],
};
