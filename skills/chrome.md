# Chrome Browser Control

How to control a Chrome browser using the `chrome` tool via CDP.

## Prerequisites

Chrome must be running with remote debugging enabled:

```
google-chrome --remote-debugging-port=9222
```

On macOS:
```
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## When to use
- User asks to open a website and interact with it
- Need to fill forms, click buttons, or scrape dynamic content
- Testing or automating web applications

## Common workflows

### Browse and read a page
```
chrome action="navigate" url="https://example.com"
chrome action="get_content"
```

### Fill a form and submit
```
chrome action="type" selector="#username" text="myuser"
chrome action="type" selector="#password" text="mypass"
chrome action="click" selector="button[type=submit]"
chrome action="wait_for" selector=".dashboard"
```

### Take a screenshot
```
chrome action="screenshot"
```

### Run custom JavaScript
```
chrome action="evaluate" expression="document.querySelectorAll('a').length"
```

## Tips

- Use `get_content` to read page text before deciding what to click
- Use `wait_for` after navigation or clicks that trigger page loads
- Use `evaluate` for complex DOM interactions that click/type can't handle
- Selectors use standard CSS syntax: `#id`, `.class`, `tag`, `[attr=val]`
- For SPAs, use `wait_for` instead of assuming content loads after navigate
- Use `page_info` to check current URL and title
- Use `list_tabs` to see all open tabs, `new_tab`/`close_tab` to manage them
