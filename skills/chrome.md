# Chrome Browser Control

You can control a Chrome browser with persistent profiles using the `chrome` tool.

## Key Concepts

- **Profiles** persist at `~/.lawclaw/chrome/profiles/{name}/` — login once, reuse forever
- Uses Puppeteer's bundled Chromium (not system Chrome) — no Keychain issues
- One browser instance at a time; stop current before starting another profile

## Workflows

### First-time Login (e.g., Google account)
1. `chrome(action="start_profile", name="google", headless=false)` — opens visible browser
2. Tell user: "Browser is open. Please log in to your Google account. Let me know when done."
3. After user confirms: `chrome(action="screenshot")` — verify login state
4. `chrome(action="stop_profile")` — saves session, profile preserved

### Subsequent Use (headless)
1. `chrome(action="start_profile", name="google")` — headless, already logged in
2. `chrome(action="navigate", url="https://play.google.com/console")` — navigate
3. `chrome(action="screenshot")` — verify page
4. Do work: navigate, click, fill, evaluate as needed
5. `chrome(action="stop_profile")` — done

### Common Actions
```
# Profile management
chrome(action="list_profiles")
chrome(action="start_profile", name="twitter", headless=false)
chrome(action="stop_profile")
chrome(action="delete_profile", name="old-profile")

# Page interaction
chrome(action="navigate", url="https://example.com")
chrome(action="click", selector="button.submit")
chrome(action="click", selector="//button[contains(text(),'Submit')]")  # XPath
chrome(action="fill", selector="#email", value="user@example.com")
chrome(action="screenshot")
chrome(action="screenshot", selector=".main-content")
chrome(action="evaluate", script="document.querySelectorAll('.item').length")
chrome(action="page_info")
```

## Tips

- **Google/Material Web sites**: DOM `click()` may not work. Use `evaluate` with `mouse.click()` coordinates or find the inner `<input>` element
- **XPath selectors**: Start with `/` or `(//`. Example: `//button[text()="Save"]`
- **Login detection**: After starting a profile, take a screenshot or evaluate JS to check if session is active
- **Always stop_profile** when done — this preserves the session for next use
- Use `/ban chrome` to disable, `/approve chrome` to re-enable
