# Clawdbot Plugin Architecture Analysis

Research findings for Task #2.

## Plugin Registration System

### Plugin Structure

Plugins export a default object with:

```typescript
interface Plugin {
  id: string;           // Unique plugin ID
  name: string;         // Display name
  description: string;  // Plugin description
  configSchema: Schema; // Configuration schema (use emptyPluginConfigSchema())
  register(api: PluginApi): void;  // Registration function
}
```

### Plugin API Methods

From `plugins/registry.js`, the API provides:

```typescript
interface PluginApi {
  id: string;
  name: string;
  version: string;
  config: Config;
  runtime: Runtime;
  logger: Logger;

  // Registration methods
  registerTool(tool, opts?): void;
  registerHook(events, handler, opts?): void;
  registerHttpHandler(handler): void;
  registerChannel(registration): void;
  registerProvider(provider): void;       // For model providers
  registerGatewayMethod(method, handler): void;
  registerCli(registrar, opts?): void;
  registerService(service): void;
  registerCommand(command): void;

  // Utilities
  resolvePath(input): string;
  on(hookName, handler, opts?): void;
}
```

## Provider Registration

From `copilot-proxy` and `google-gemini-cli-auth` examples:

```typescript
interface Provider {
  id: string;           // Provider ID (e.g., "claude-code-cli")
  label: string;        // Display name
  docsPath?: string;    // Documentation path
  aliases?: string[];   // Alternative names
  envVars?: string[];   // Related environment variables

  auth: AuthMethod[];   // Authentication methods
}

interface AuthMethod {
  id: string;           // Method ID (e.g., "oauth", "local")
  label: string;        // Display label
  hint: string;         // Help text
  kind: "oauth" | "custom" | "api_key";

  run: async (ctx: AuthContext) => AuthResult;
}

interface AuthResult {
  profiles: AuthProfile[];
  configPatch?: ConfigPatch;    // Config to merge
  defaultModel?: string;
  notes?: string[];
}

interface AuthProfile {
  profileId: string;    // e.g., "claude-code-cli:max"
  credential: {
    type: "oauth" | "token" | "api_key";
    provider: string;
    // Type-specific fields (access, refresh, token, apiKey, etc.)
  };
}
```

## Key Insight: Providers vs Backends

**Important:** The Clawdbot provider system handles **authentication**, not **API execution**.

- Providers register auth methods and credentials
- The actual API calls use the credentials against standard APIs (OpenAI, Anthropic, etc.)
- There's no built-in "subprocess backend" concept

## For Claude Code CLI Integration

We have two options:

### Option A: Custom Backend (Complex)

1. Create a new execution path that uses Claude CLI subprocess
2. Would require modifying Clawdbot core
3. More comprehensive but significant work

### Option B: Provider + Custom API Endpoint (Simpler)

1. Run a local HTTP server that wraps Claude CLI
2. Register as a standard OpenAI-compatible provider
3. Messages → Local Server → Claude CLI → Response

```
Clawdbot → HTTP POST → Local Wrapper Server → Claude CLI subprocess
                                    ↓
Clawdbot ← HTTP Response ← Local Wrapper Server ← Claude CLI stdout
```

### Option C: Hook-Based (Most Practical)

1. Register hooks that intercept model calls
2. When Anthropic model is requested, redirect to Claude CLI
3. Return response via hook system

## Recommended Approach

**Option B** seems most practical:

1. Create a small HTTP server (Express/Fastify) that:
   - Exposes OpenAI-compatible `/v1/chat/completions` endpoint
   - Spawns Claude CLI subprocess
   - Translates request/response formats

2. Register as a provider with `api: "openai-completions"` type

3. Configure Clawdbot to use this local endpoint

## Files to Study Further

- `/dist/providers/dock.js` - Provider docking/loading
- `/dist/agents/model-call.js` - How model calls are made (if exists)
- `/dist/ai/` - AI/LLM integration code

## Next Steps

1. Verify if hook-based interception is possible
2. Check if there's an existing "local proxy" pattern
3. Design the local HTTP wrapper approach
