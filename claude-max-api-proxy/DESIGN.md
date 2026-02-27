# Claude Code CLI Provider - Technical Design

## Overview

This plugin enables Clawdbot to use Claude Max subscription through the Claude Code CLI, bypassing the OAuth token scope restrictions that block direct API access.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLAWDBOT                                │
│  ┌───────────────────┐    ┌──────────────────────────────────┐ │
│  │ claude-code-cli   │    │     Model Provider System        │ │
│  │ Provider Plugin   │───▶│  (registers as openai-completions)│ │
│  └───────────────────┘    └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                       │
                                       │ HTTP POST /v1/chat/completions
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL WRAPPER SERVER                         │
│                    (Express.js on port 3456)                    │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │ Request Parser │─▶│ Format Adapter │─▶│ Subprocess Mgr   │  │
│  │ (OpenAI → JSON)│  │ (OpenAI ↔ CLI) │  │ (spawn Claude)   │  │
│  └────────────────┘  └────────────────┘  └──────────────────┘  │
│                                                    │            │
│  ┌────────────────┐  ┌────────────────┐           │            │
│  │ Response Stream│◀─│ JSON Parser    │◀──────────┘            │
│  │ (SSE format)   │  │ (stream-json)  │        stdout          │
│  └────────────────┘  └────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
                                       │
                                       │ subprocess
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CLAUDE CODE CLI                            │
│  claude --print --output-format stream-json --verbose           │
│         --input-format stream-json --model <model>              │
│         --session-id <uuid>                                     │
│                                                                 │
│  Uses: ~/.claude/credentials.json (OAuth from Claude Max)       │
└─────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. Plugin Structure

```
claude-code-cli-provider/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # Plugin entry point
│   ├── server/
│   │   ├── index.ts          # Express server setup
│   │   ├── routes.ts         # API route handlers
│   │   └── middleware.ts     # Request validation, logging
│   ├── subprocess/
│   │   ├── manager.ts        # Subprocess lifecycle
│   │   ├── pool.ts           # Process pool for concurrent requests
│   │   └── health.ts         # Health monitoring
│   ├── adapter/
│   │   ├── openai-to-cli.ts  # OpenAI request → CLI input
│   │   ├── cli-to-openai.ts  # CLI output → OpenAI response
│   │   └── stream.ts         # Streaming response handler
│   ├── session/
│   │   ├── manager.ts        # Session mapping & persistence
│   │   └── store.ts          # Session storage
│   └── types/
│       ├── openai.ts         # OpenAI API types
│       ├── claude-cli.ts     # Claude CLI message types
│       └── config.ts         # Plugin configuration
├── tests/
│   ├── adapter.test.ts
│   ├── subprocess.test.ts
│   └── integration.test.ts
└── README.md
```

### 2. Plugin Registration (index.ts)

```typescript
import { emptyPluginConfigSchema } from "clawdbot/plugin-sdk";
import { startServer, stopServer } from "./server/index.js";

const PROVIDER_ID = "claude-code-cli";
const DEFAULT_PORT = 3456;
const DEFAULT_MODEL = "claude-code-cli/claude-sonnet-4";

const AVAILABLE_MODELS = [
  { id: "claude-opus-4", name: "Claude Opus 4.5", alias: "opus" },
  { id: "claude-sonnet-4", name: "Claude Sonnet 4", alias: "sonnet" },
  { id: "claude-haiku-4", name: "Claude Haiku 4", alias: "haiku" },
];

const plugin = {
  id: "claude-code-cli",
  name: "Claude Code CLI Provider",
  description: "Use Claude Max subscription via Claude Code CLI",
  configSchema: emptyPluginConfigSchema(),

  register(api) {
    // Start the local HTTP server when plugin loads
    let serverInstance = null;

    api.registerProvider({
      id: PROVIDER_ID,
      label: "Claude Code CLI",
      docsPath: "/providers/claude-code-cli",
      aliases: ["claude-cli", "claude-max"],

      auth: [{
        id: "local",
        label: "Local Claude CLI",
        hint: "Uses your existing Claude Code CLI authentication",
        kind: "custom",

        run: async (ctx) => {
          const spin = ctx.prompter.progress("Checking Claude CLI...");

          // 1. Verify claude CLI is installed and authenticated
          const cliCheck = await verifyClaude();
          if (!cliCheck.ok) {
            spin.stop("Claude CLI not found");
            throw new Error(cliCheck.error);
          }

          // 2. Start local server if not running
          const port = await ctx.prompter.text({
            message: "Local server port",
            initialValue: String(DEFAULT_PORT),
            validate: (v) => isNaN(parseInt(v)) ? "Enter a valid port" : undefined,
          });

          serverInstance = await startServer(parseInt(port));
          spin.stop("Claude CLI provider ready");

          const baseUrl = `http://localhost:${port}/v1`;

          return {
            profiles: [{
              profileId: `${PROVIDER_ID}:local`,
              credential: {
                type: "token",
                provider: PROVIDER_ID,
                token: "local", // Dummy token, CLI handles auth
              },
            }],
            configPatch: {
              models: {
                providers: {
                  [PROVIDER_ID]: {
                    baseUrl,
                    apiKey: "local",
                    api: "openai-completions",
                    authHeader: false,
                    models: AVAILABLE_MODELS.map(m => ({
                      id: m.id,
                      name: m.name,
                      api: "openai-completions",
                      reasoning: m.id.includes("opus"),
                      input: ["text"],
                      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
                      contextWindow: 200000,
                      maxTokens: 8192,
                    })),
                  },
                },
              },
              agents: {
                defaults: {
                  models: Object.fromEntries(
                    AVAILABLE_MODELS.map(m => [`${PROVIDER_ID}/${m.id}`, {}])
                  ),
                },
              },
            },
            defaultModel: DEFAULT_MODEL,
            notes: [
              "This uses your Claude Max subscription via Claude Code CLI.",
              "Make sure you're logged into Claude Code (`claude auth login`).",
              `Local server running at http://localhost:${port}`,
            ],
          };
        },
      }],
    });

    // Cleanup on plugin unload
    api.on("plugin:unload", async () => {
      if (serverInstance) {
        await stopServer(serverInstance);
      }
    });
  },
};

export default plugin;
```

### 3. Subprocess Manager (subprocess/manager.ts)

**Security Note**: Uses `spawn()` instead of `exec()` to prevent command injection.

```typescript
import { spawn, ChildProcess } from "child_process";
import { EventEmitter } from "events";
import { ClaudeCliMessage, ClaudeCliResult } from "../types/claude-cli.js";

interface SubprocessOptions {
  model: "opus" | "sonnet" | "haiku";
  sessionId?: string;
  cwd?: string;
}

export class ClaudeSubprocess extends EventEmitter {
  private process: ChildProcess | null = null;
  private buffer: string = "";

  async start(prompt: string, options: SubprocessOptions): Promise<void> {
    const args = [
      "--print",
      "--output-format", "stream-json",
      "--input-format", "stream-json",
      "--verbose",
      "--model", options.model,
    ];

    if (options.sessionId) {
      args.push("--session-id", options.sessionId);
    }

    // Don't persist sessions for stateless API usage
    args.push("--no-session-persistence");

    // Use spawn() for security - no shell interpretation
    this.process = spawn("claude", args, {
      cwd: options.cwd || process.cwd(),
      env: { ...process.env },
      stdio: ["pipe", "pipe", "pipe"],
    });

    // Send the prompt via stdin
    this.process.stdin?.write(JSON.stringify({
      type: "user_message",
      content: prompt,
    }) + "\n");
    this.process.stdin?.end();

    // Parse JSON stream from stdout
    this.process.stdout?.on("data", (chunk) => {
      this.buffer += chunk.toString();
      this.processBuffer();
    });

    this.process.stderr?.on("data", (chunk) => {
      this.emit("error", new Error(chunk.toString()));
    });

    this.process.on("close", (code) => {
      this.emit("close", code);
    });
  }

  private processBuffer(): void {
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() || ""; // Keep incomplete line

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const message: ClaudeCliMessage = JSON.parse(line);
        this.emit("message", message);

        if (message.type === "assistant") {
          this.emit("assistant", message);
        } else if (message.type === "result") {
          this.emit("result", message as ClaudeCliResult);
        }
      } catch (e) {
        // Non-JSON output, emit as raw
        this.emit("raw", line);
      }
    }
  }

  kill(): void {
    this.process?.kill();
  }
}
```

### 4. Format Adapters

#### OpenAI Request → CLI Input (adapter/openai-to-cli.ts)

```typescript
import { OpenAIChatRequest } from "../types/openai.js";

interface CliInput {
  prompt: string;
  model: "opus" | "sonnet" | "haiku";
  sessionId?: string;
}

export function openaiToCli(request: OpenAIChatRequest): CliInput {
  // Extract model alias from model name
  const modelMap: Record<string, "opus" | "sonnet" | "haiku"> = {
    "claude-opus-4": "opus",
    "claude-sonnet-4": "sonnet",
    "claude-haiku-4": "haiku",
  };

  const modelId = request.model.replace("claude-code-cli/", "");
  const model = modelMap[modelId] || "sonnet";

  // Convert messages to single prompt
  // Claude Code CLI expects a single user message in non-interactive mode
  const messages = request.messages;
  let prompt = "";

  for (const msg of messages) {
    if (msg.role === "system") {
      prompt += `[System]: ${msg.content}\n\n`;
    } else if (msg.role === "user") {
      prompt += `${msg.content}\n`;
    } else if (msg.role === "assistant") {
      // For context, include previous assistant responses
      prompt += `[Previous response]: ${msg.content}\n\n`;
    }
  }

  return {
    prompt: prompt.trim(),
    model,
    sessionId: request.user, // Use user field for session mapping
  };
}
```

#### CLI Output → OpenAI Response (adapter/cli-to-openai.ts)

```typescript
import { ClaudeCliAssistant, ClaudeCliResult } from "../types/claude-cli.js";
import { OpenAIChatResponse, OpenAIChatChunk } from "../types/openai.js";

let chunkIndex = 0;

export function cliToOpenaiChunk(
  message: ClaudeCliAssistant,
  requestId: string
): OpenAIChatChunk {
  const text = message.message.content
    .filter(c => c.type === "text")
    .map(c => c.text)
    .join("");

  return {
    id: `chatcmpl-${requestId}`,
    object: "chat.completion.chunk",
    created: Math.floor(Date.now() / 1000),
    model: message.message.model,
    choices: [{
      index: 0,
      delta: {
        role: chunkIndex === 0 ? "assistant" : undefined,
        content: text,
      },
      finish_reason: message.message.stop_reason ? "stop" : null,
    }],
  };
}

export function cliResultToOpenai(
  result: ClaudeCliResult,
  requestId: string
): OpenAIChatResponse {
  return {
    id: `chatcmpl-${requestId}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: result.modelUsage ? Object.keys(result.modelUsage)[0] : "claude-sonnet-4",
    choices: [{
      index: 0,
      message: {
        role: "assistant",
        content: result.result,
      },
      finish_reason: "stop",
    }],
    usage: {
      prompt_tokens: result.usage?.input_tokens || 0,
      completion_tokens: result.usage?.output_tokens || 0,
      total_tokens: (result.usage?.input_tokens || 0) + (result.usage?.output_tokens || 0),
    },
  };
}
```

### 5. HTTP Server (server/index.ts)

```typescript
import express from "express";
import { createServer, Server } from "http";
import { handleChatCompletions } from "./routes.js";

let server: Server | null = null;

export async function startServer(port: number): Promise<Server> {
  const app = express();

  app.use(express.json({ limit: "10mb" }));

  // Health check
  app.get("/health", (req, res) => {
    res.json({ status: "ok", provider: "claude-code-cli" });
  });

  // OpenAI-compatible endpoints
  app.post("/v1/chat/completions", handleChatCompletions);

  // Models list
  app.get("/v1/models", (req, res) => {
    res.json({
      object: "list",
      data: [
        { id: "claude-opus-4", object: "model", owned_by: "anthropic" },
        { id: "claude-sonnet-4", object: "model", owned_by: "anthropic" },
        { id: "claude-haiku-4", object: "model", owned_by: "anthropic" },
      ],
    });
  });

  return new Promise((resolve, reject) => {
    server = createServer(app);
    server.listen(port, "127.0.0.1", () => {
      console.log(`Claude Code CLI server running on port ${port}`);
      resolve(server);
    });
    server.on("error", reject);
  });
}

export async function stopServer(instance: Server): Promise<void> {
  return new Promise((resolve) => {
    instance.close(() => resolve());
  });
}
```

### 6. Route Handler (server/routes.ts)

```typescript
import { Request, Response } from "express";
import { ClaudeSubprocess } from "../subprocess/manager.js";
import { openaiToCli } from "../adapter/openai-to-cli.js";
import { cliToOpenaiChunk, cliResultToOpenai } from "../adapter/cli-to-openai.js";
import { v4 as uuidv4 } from "uuid";

export async function handleChatCompletions(req: Request, res: Response) {
  const requestId = uuidv4();
  const stream = req.body.stream === true;

  try {
    const cliInput = openaiToCli(req.body);
    const subprocess = new ClaudeSubprocess();

    if (stream) {
      // SSE streaming response
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");

      subprocess.on("assistant", (message) => {
        const chunk = cliToOpenaiChunk(message, requestId);
        res.write(`data: ${JSON.stringify(chunk)}\n\n`);
      });

      subprocess.on("result", (result) => {
        res.write(`data: [DONE]\n\n`);
        res.end();
      });

      subprocess.on("error", (error) => {
        res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
        res.end();
      });

    } else {
      // Non-streaming response
      let finalResult: any = null;

      subprocess.on("result", (result) => {
        finalResult = cliResultToOpenai(result, requestId);
      });

      subprocess.on("close", () => {
        if (finalResult) {
          res.json(finalResult);
        } else {
          res.status(500).json({ error: "No response from Claude CLI" });
        }
      });

      subprocess.on("error", (error) => {
        res.status(500).json({ error: error.message });
      });
    }

    await subprocess.start(cliInput.prompt, {
      model: cliInput.model,
      sessionId: cliInput.sessionId,
    });

  } catch (error) {
    res.status(500).json({ error: error.message });
  }
}
```

### 7. Session Management (session/manager.ts)

```typescript
import { v4 as uuidv4 } from "uuid";
import fs from "fs/promises";
import path from "path";

interface SessionMapping {
  clawdbotId: string;      // Clawdbot conversation ID
  claudeSessionId: string;  // Claude CLI session UUID
  createdAt: number;
  lastUsedAt: number;
}

const SESSION_FILE = path.join(process.env.HOME || "", ".claude-code-cli-sessions.json");

class SessionManager {
  private sessions: Map<string, SessionMapping> = new Map();

  async load(): Promise<void> {
    try {
      const data = await fs.readFile(SESSION_FILE, "utf-8");
      const parsed = JSON.parse(data);
      this.sessions = new Map(Object.entries(parsed));
    } catch {
      // File doesn't exist, start fresh
    }
  }

  async save(): Promise<void> {
    const data = Object.fromEntries(this.sessions);
    await fs.writeFile(SESSION_FILE, JSON.stringify(data, null, 2));
  }

  getOrCreate(clawdbotId: string): string {
    const existing = this.sessions.get(clawdbotId);
    if (existing) {
      existing.lastUsedAt = Date.now();
      return existing.claudeSessionId;
    }

    const claudeSessionId = uuidv4();
    this.sessions.set(clawdbotId, {
      clawdbotId,
      claudeSessionId,
      createdAt: Date.now(),
      lastUsedAt: Date.now(),
    });

    return claudeSessionId;
  }

  // Cleanup old sessions (older than 24 hours)
  cleanup(): void {
    const cutoff = Date.now() - (24 * 60 * 60 * 1000);
    for (const [key, session] of this.sessions) {
      if (session.lastUsedAt < cutoff) {
        this.sessions.delete(key);
      }
    }
  }
}

export const sessionManager = new SessionManager();
```

## Type Definitions

### Claude CLI Types (types/claude-cli.ts)

```typescript
export interface ClaudeCliInit {
  type: "system";
  subtype: "init";
  cwd: string;
  session_id: string;
  tools: string[];
  model: string;
  uuid: string;
}

export interface ClaudeCliAssistant {
  type: "assistant";
  message: {
    model: string;
    id: string;
    type: "message";
    role: "assistant";
    content: Array<{ type: "text"; text: string }>;
    stop_reason: string | null;
    usage: {
      input_tokens: number;
      output_tokens: number;
      cache_creation_input_tokens?: number;
    };
  };
  session_id: string;
  uuid: string;
}

export interface ClaudeCliResult {
  type: "result";
  subtype: "success" | "error";
  is_error: boolean;
  duration_ms: number;
  num_turns: number;
  result: string;
  session_id: string;
  total_cost_usd: number;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens?: number;
    cache_read_input_tokens?: number;
  };
  modelUsage: Record<string, {
    inputTokens: number;
    outputTokens: number;
    costUSD: number;
  }>;
}

export type ClaudeCliMessage = ClaudeCliInit | ClaudeCliAssistant | ClaudeCliResult | {
  type: "system";
  subtype: string;
  [key: string]: any;
};
```

### OpenAI Types (types/openai.ts)

```typescript
export interface OpenAIChatRequest {
  model: string;
  messages: Array<{
    role: "system" | "user" | "assistant";
    content: string;
  }>;
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
  user?: string; // Used for session mapping
}

export interface OpenAIChatResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: {
      role: "assistant";
      content: string;
    };
    finish_reason: "stop" | "length" | null;
  }>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface OpenAIChatChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: Array<{
    index: number;
    delta: {
      role?: "assistant";
      content?: string;
    };
    finish_reason: "stop" | "length" | null;
  }>;
}
```

## Edge Cases & Error Handling

### 1. Claude CLI Not Installed

Uses `spawn()` with proper error handling:

```typescript
import { spawn } from "child_process";

async function verifyClaude(): Promise<{ ok: boolean; error?: string }> {
  return new Promise((resolve) => {
    const proc = spawn("claude", ["--version"], { stdio: "pipe" });

    proc.on("error", (err) => {
      resolve({
        ok: false,
        error: "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
      });
    });

    proc.on("close", (code) => {
      resolve({ ok: code === 0 });
    });
  });
}
```

### 2. OAuth Token Expired
- Claude CLI handles token refresh automatically
- If auth fails, user needs to run `claude auth login` manually

### 3. Subprocess Timeout
```typescript
const TIMEOUT_MS = 300000; // 5 minutes

setTimeout(() => {
  subprocess.kill();
  reject(new Error("Request timed out"));
}, TIMEOUT_MS);
```

### 4. Concurrent Request Limits
- Claude Max may have rate limits
- Implement request queue with configurable concurrency

### 5. Tool Calls
- Claude Code CLI may invoke tools (Bash, Read, etc.)
- For Clawdbot integration, we should:
  - Filter out tool-related messages
  - Only return final text responses
  - Optionally: expose tool usage as metadata

## Configuration Options

```typescript
interface PluginConfig {
  port: number;              // Default: 3456
  timeout: number;           // Default: 300000 (5 min)
  maxConcurrent: number;     // Default: 3
  sessionPersistence: boolean; // Default: false
  debugMode: boolean;        // Default: false
  cwd: string;               // Default: process.cwd()
}
```

## Security Considerations

1. **Local Only**: Server binds to 127.0.0.1 only, not exposed externally
2. **No Auth Header**: Requests don't need API keys (uses local OAuth)
3. **Session Isolation**: Each Clawdbot conversation maps to separate Claude session
4. **No Credential Storage**: Plugin doesn't store or handle OAuth tokens directly
5. **No Shell Injection**: Uses `spawn()` instead of `exec()` to prevent command injection

## Testing Strategy

### Unit Tests
- Format adapters (OpenAI ↔ CLI conversion)
- Session manager
- Message parsing

### Integration Tests
- End-to-end request flow
- Streaming responses
- Error handling

### Manual Testing
- Telegram bot conversation
- WhatsApp message handling
- Multi-turn conversations

## Deployment

1. Build: `npm run build`
2. Package: `npm pack`
3. Install in Clawdbot: `clawdbot plugins install ./claude-code-cli-provider-1.0.0.tgz`
4. Configure: `clawdbot models auth login --provider claude-code-cli`
5. Set default model: Edit `~/.clawdbot/clawdbot.json`

## Future Enhancements

1. **Tool Bridging**: Expose Claude Code's tools (Bash, Read, etc.) to Clawdbot
2. **Cost Tracking**: Track subscription usage across Clawdbot conversations
3. **Model Routing**: Automatic model selection based on message complexity
4. **Caching**: Response caching for repeated queries
5. **Multi-User**: Support multiple Claude Max accounts
