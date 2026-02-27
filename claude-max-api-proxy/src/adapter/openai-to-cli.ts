/**
 * Converts OpenAI chat request format to Claude CLI input
 */

import type { OpenAIChatRequest, OpenAITool } from "../types/openai.js";

export type ClaudeModel = "opus" | "sonnet" | "haiku";

export interface CliInput {
  prompt: string;
  model: ClaudeModel;
  sessionId?: string;
  allowedTools?: string[];
}

const MODEL_MAP: Record<string, ClaudeModel> = {
  // Direct model names
  "claude-opus-4": "opus",
  "claude-sonnet-4": "sonnet",
  "claude-haiku-4": "haiku",
  // With provider prefix
  "claude-code-cli/claude-opus-4": "opus",
  "claude-code-cli/claude-sonnet-4": "sonnet",
  "claude-code-cli/claude-haiku-4": "haiku",
  // Aliases
  "opus": "opus",
  "sonnet": "sonnet",
  "haiku": "haiku",
};

/**
 * Extract Claude model alias from request model string
 */
export function extractModel(model: string): ClaudeModel {
  // Try direct lookup
  if (MODEL_MAP[model]) {
    return MODEL_MAP[model];
  }

  // Try stripping provider prefix
  const stripped = model.replace(/^claude-code-cli\//, "");
  if (MODEL_MAP[stripped]) {
    return MODEL_MAP[stripped];
  }

  // Default to opus (Claude Max subscription)
  return "opus";
}

/**
 * Build a tool injection prompt that instructs Claude to use structured JSON
 * for tool calls instead of plain text responses.
 */
function buildToolInjection(tools: OpenAITool[]): string {
  const toolDescriptions = tools.map((t) => {
    const params = t.function.parameters
      ? JSON.stringify(t.function.parameters)
      : "{}";
    return `- ${t.function.name}: ${t.function.description || "No description"}\n  Parameters: ${params}`;
  }).join("\n");

  return (
    `<tools>\n` +
    `You have access to the following tools:\n\n` +
    `${toolDescriptions}\n\n` +
    `IMPORTANT: When you need to use a tool, you MUST respond with ONLY a JSON block in this exact format (no other text before or after):\n` +
    `\`\`\`json\n` +
    `{"tool_calls": [{"name": "tool_name", "arguments": {"param1": "value1"}}]}\n` +
    `\`\`\`\n\n` +
    `Rules:\n` +
    `- Respond with the JSON tool_calls block ONLY when you need to call a tool\n` +
    `- You can call multiple tools at once by adding multiple entries to the array\n` +
    `- When you have the final answer (after tool results), respond with plain text (no JSON)\n` +
    `- NEVER fabricate tool results — wait for actual results before answering\n` +
    `</tools>`
  );
}

/**
 * Convert OpenAI messages array to a single prompt string for Claude CLI
 *
 * Claude Code CLI in --print mode expects a single prompt, not a conversation.
 * We format the messages into a readable format that preserves context.
 */
export function messagesToPrompt(
  messages: OpenAIChatRequest["messages"],
  tools?: OpenAITool[]
): string {
  const parts: string[] = [];

  // Inject tool definitions at the top if provided
  if (tools && tools.length > 0) {
    parts.push(buildToolInjection(tools));
  }

  for (const msg of messages) {
    switch (msg.role) {
      case "system":
        // System messages become context instructions
        parts.push(`<system>\n${msg.content}\n</system>\n`);
        break;

      case "user":
        // User messages are the main prompt
        parts.push(msg.content);
        break;

      case "assistant": {
        // Previous assistant responses for context
        // Include tool_calls info if present
        if (msg.tool_calls && msg.tool_calls.length > 0) {
          const callsDesc = msg.tool_calls
            .map((tc) => `Called ${tc.function.name}(${tc.function.arguments})`)
            .join("\n");
          parts.push(
            `<previous_response>\n[Tool calls made]\n${callsDesc}\n</previous_response>\n`
          );
        } else {
          parts.push(
            `<previous_response>\n${msg.content}\n</previous_response>\n`
          );
        }
        break;
      }

      case "tool":
        // Tool result messages — show as tool output context
        parts.push(
          `<tool_result>\n${msg.content}\n</tool_result>\n`
        );
        break;
    }
  }

  return parts.join("\n").trim();
}

/**
 * Convert OpenAI chat request to CLI input format
 */
export function openaiToCli(request: OpenAIChatRequest): CliInput {
  return {
    prompt: messagesToPrompt(request.messages, request.tools),
    model: extractModel(request.model),
    sessionId: request.user, // Use OpenAI's user field for session mapping
    allowedTools: request.allowed_tools,
  };
}
