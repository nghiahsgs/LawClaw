# Web Search

How to search the web effectively.

## Tool priority (highest → lowest)

1. **`web_search`** (Brave Search API) — primary search tool
2. **`web_fetch`** — for extracting content from a known URL

## When to use
- User asks for current/real-time info (news, prices, weather)
- Need to look up documentation, guides, references

## Best practices
- For real-time data (crypto, stocks, weather), prefer `web_fetch` with reliable APIs:
  - BTC price: `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd`
  - Weather: use OpenWeatherMap API
- After finding URLs via search, use `web_fetch` to extract full content
- Always cite the source URL in responses
