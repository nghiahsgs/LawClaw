# Web Search

How to search the web effectively.

## Tool priority (highest → lowest)

1. **`chrome`** (Google Search via CDP) — **preferred**, most accurate results
2. **`web_search`** (Brave Search API) — fallback when Chrome is unavailable
3. **`web_fetch`** — for extracting content from a known URL

## When to use
- User asks for current/real-time info (news, prices, weather)
- Need to look up documentation, guides, references

## Search with Chrome (preferred)

Use Chrome to search Google directly for the most accurate, up-to-date results:

```
chrome action="navigate" url="https://www.google.com/search?q=your+query+here"
chrome action="get_content"
```

Then use `chrome action="navigate"` to visit promising results and `get_content` to read them.

### When to fallback to `web_search`
- Chrome connection fails (CDP not available / Chrome not running)
- Quick, simple lookups where speed matters more than accuracy

## Best practices
- For real-time data (crypto, stocks, weather), prefer `web_fetch` with reliable APIs:
  - BTC price: `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd`
  - Weather: use OpenWeatherMap API
- After finding URLs via search, use `web_fetch` or `chrome get_content` to extract full content
- Always cite the source URL in responses
