/**
 * Converts Claude CLI output to OpenAI-compatible response format
 */

import type { ClaudeCliAssistant, ClaudeCliResult } from "../types/claude-cli.js";
import type { OpenAIChatResponse, OpenAIChatChunk, OpenAIToolCall } from "../types/openai.js";

/**
 * Extract text content from Claude CLI assistant message
 */
export function extractTextContent(message: ClaudeCliAssistant): string {
  return message.message.content
    .filter((c) => c.type === "text")
    .map((c) => c.text)
    .join("");
}

/**
 * Convert Claude CLI assistant message to OpenAI streaming chunk
 */
export function cliToOpenaiChunk(
  message: ClaudeCliAssistant,
  requestId: string,
  isFirst: boolean = false
): OpenAIChatChunk {
  const text = extractTextContent(message);

  return {
    id: `chatcmpl-${requestId}`,
    object: "chat.completion.chunk",
    created: Math.floor(Date.now() / 1000),
    model: normalizeModelName(message.message.model),
    choices: [
      {
        index: 0,
        delta: {
          role: isFirst ? "assistant" : undefined,
          content: text,
        },
        finish_reason: message.message.stop_reason ? "stop" : null,
      },
    ],
  };
}

/**
 * Create a final "done" chunk for streaming
 */
export function createDoneChunk(requestId: string, model: string): OpenAIChatChunk {
  return {
    id: `chatcmpl-${requestId}`,
    object: "chat.completion.chunk",
    created: Math.floor(Date.now() / 1000),
    model: normalizeModelName(model),
    choices: [
      {
        index: 0,
        delta: {},
        finish_reason: "stop",
      },
    ],
  };
}

/**
 * Parse tool_calls JSON from Claude's text response.
 * Looks for ```json blocks or raw JSON containing {"tool_calls": [...]}
 * Uses multiple strategies to handle various Claude output formats.
 */
export function parseToolCalls(text: string): {
  toolCalls: OpenAIToolCall[] | null;
  remainingText: string;
} {
  // Strategy 1: Extract from ```json code blocks (greedy to handle nested braces)
  const codeBlockMatch = text.match(/```json\s*\n?([\s\S]*?)\n?\s*```/);
  if (codeBlockMatch) {
    const result = tryParseToolCallsJson(codeBlockMatch[1].trim());
    if (result) {
      const remaining = text.replace(codeBlockMatch[0], "").trim();
      return { toolCalls: result, remainingText: remaining };
    }
  }

  // Strategy 2: Extract raw JSON object containing "tool_calls" (no code block)
  const rawJsonMatch = text.match(/(\{[\s\S]*"tool_calls"\s*:\s*\[[\s\S]*\][\s\S]*\})/);
  if (rawJsonMatch) {
    const result = tryParseToolCallsJson(rawJsonMatch[1].trim());
    if (result) {
      const remaining = text.replace(rawJsonMatch[0], "").trim();
      return { toolCalls: result, remainingText: remaining };
    }
  }

  // Strategy 3: Try parsing the entire text as JSON (original fallback)
  const result = tryParseToolCallsJson(text.trim());
  if (result) {
    return { toolCalls: result, remainingText: "" };
  }

  return { toolCalls: null, remainingText: text };
}

/**
 * Try to parse a JSON string as tool_calls. Returns parsed tool calls or null.
 */
function tryParseToolCallsJson(jsonStr: string): OpenAIToolCall[] | null {
  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed.tool_calls && Array.isArray(parsed.tool_calls)) {
      return parsed.tool_calls.map(
        (tc: { name: string; arguments: Record<string, unknown> }, i: number) => ({
          id: `call_${Date.now()}_${i}`,
          type: "function" as const,
          function: {
            name: tc.name,
            arguments: JSON.stringify(tc.arguments || {}),
          },
        })
      );
    }
  } catch {
    // Not valid JSON
  }
  return null;
}

/**
 * Convert Claude CLI result to OpenAI non-streaming response
 */
export function cliResultToOpenai(
  result: ClaudeCliResult,
  requestId: string
): OpenAIChatResponse {
  // Get model from modelUsage or default
  const modelName = result.modelUsage
    ? Object.keys(result.modelUsage)[0]
    : "claude-sonnet-4";

  // Check if response contains tool_calls JSON
  const { toolCalls, remainingText } = parseToolCalls(result.result);

  return {
    id: `chatcmpl-${requestId}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: normalizeModelName(modelName),
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content: remainingText || (toolCalls ? "" : result.result),
          ...(toolCalls ? { tool_calls: toolCalls } : {}),
        },
        finish_reason: toolCalls ? "tool_calls" : "stop",
      },
    ],
    usage: {
      prompt_tokens: result.usage?.input_tokens || 0,
      completion_tokens: result.usage?.output_tokens || 0,
      total_tokens:
        (result.usage?.input_tokens || 0) + (result.usage?.output_tokens || 0),
    },
  };
}

/**
 * Normalize Claude model names to a consistent format
 * e.g., "claude-sonnet-4-5-20250929" -> "claude-sonnet-4"
 */
function normalizeModelName(model: string): string {
  if (model.includes("opus")) return "claude-opus-4";
  if (model.includes("sonnet")) return "claude-sonnet-4";
  if (model.includes("haiku")) return "claude-haiku-4";
  return model;
}
