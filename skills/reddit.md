# Reddit

How to browse and search Reddit using `web_fetch` with Reddit's JSON API.

## How it works

Append `.json` to any Reddit URL to get JSON data. Use `web_fetch` to retrieve it.

## Common patterns

### Search Reddit
```
web_fetch url="https://www.reddit.com/search.json?q=your+query&sort=relevance&limit=10"
```

### Browse a subreddit
```
web_fetch url="https://www.reddit.com/r/subreddit.json?limit=10"
web_fetch url="https://www.reddit.com/r/subreddit/hot.json?limit=10"
web_fetch url="https://www.reddit.com/r/subreddit/new.json?limit=10"
web_fetch url="https://www.reddit.com/r/subreddit/top.json?t=week&limit=10"
```

Sort options for top: `t=hour`, `t=day`, `t=week`, `t=month`, `t=year`, `t=all`

### Read a post and its comments
```
web_fetch url="https://www.reddit.com/r/subreddit/comments/POST_ID.json"
```

### Read a user's profile
```
web_fetch url="https://www.reddit.com/user/USERNAME.json"
```

## Parsing the JSON response

- Subreddit/search results: `data.children[]` — each child has `data.title`, `data.selftext`, `data.url`, `data.score`, `data.num_comments`, `data.author`, `data.permalink`
- Comments: response is an array of 2 listings — `[0]` is the post, `[1]` is comments tree. Each comment has `data.body`, `data.author`, `data.score`
- Use `data.permalink` to build full URLs: prepend `https://www.reddit.com`

## Tips

- Add `limit=5` or `limit=10` to avoid overly large responses
- Reddit rate-limits anonymous JSON access — avoid rapid repeated requests
- Set a User-Agent header if possible to reduce rate limiting
- For NSFW subreddits, JSON API may not return results without auth
- Summarize results for the user — don't dump raw JSON
