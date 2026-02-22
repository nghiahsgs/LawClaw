# Web Search

How to search the web effectively using `web_search` and `web_fetch` tools.

## When to use
- User asks for current/real-time info (news, prices, weather)
- Need to look up documentation, guides, references

## Best practices
- Use `web_search` for discovery (finding relevant URLs)
- Use `web_fetch` for extraction (getting content from a specific URL)
- For real-time data (crypto, stocks, weather), prefer `web_fetch` with reliable APIs:
  - BTC price: `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd`
  - Weather: use OpenWeatherMap API
- Search snippets may be stale — always follow up with `web_fetch` for accuracy
- Always cite the source URL in responses
