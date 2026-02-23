module.exports = {
  apps: [
    {
      name: "lawclaw",
      script: "/usr/local/bin/lawclaw",
      args: "gateway",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
