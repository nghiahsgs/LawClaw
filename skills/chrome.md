# Chrome Browser Control

You can control a Chrome browser with persistent profiles using the `chrome` tool.

## Key Concepts

- **Profiles** persist at `~/.lawclaw/workspace/chrome/profiles/{name}/` — login once, reuse forever
- Uses Puppeteer's bundled Chromium (not system Chrome) — no Keychain issues
- One browser instance at a time; switching profiles auto-stops the current one
- Screenshots and files are auto-sent to the user's chat (no need to call send_file)

## Profile Selection (IMPORTANT — only on first Chrome use in a session)

When the user asks to use Chrome **for the first time in the conversation**:

1. Call `chrome(action="list_profiles")` to see available profiles and check if one is already active
2. **If a profile is already active** → skip start, just navigate/screenshot directly
3. **If no browser running + only 1 profile** → start it automatically
4. **If no browser running + multiple profiles** → ask the user which profile to use
5. **If no profiles at all** → create a new one with a sensible name (e.g. "default")

**After the browser is started, do NOT call list_profiles or start_profile again.**
Just use navigate, screenshot, click, fill, evaluate directly — the browser stays open.

Example: user says "go to google.com" then "now go to gmail.com"
- First request: list_profiles → start_profile → navigate google.com → screenshot
- Second request: navigate gmail.com → screenshot (browser already open, just navigate!)

## Workflows

### First-time Login (e.g., Google account)
Chrome opens as a **visible GUI window** on the user's macOS desktop. The user can see it and type directly.
1. `chrome(action="start_profile", name="google")` — opens visible browser on user's screen
2. `chrome(action="navigate", url="https://accounts.google.com")` — go to login page
3. Tell user: "Chrome is open on your screen. Please type your password in the browser window. Let me know when done."
4. After user confirms: `chrome(action="screenshot")` — verify login state
5. `chrome(action="stop_profile")` — saves session, profile preserved

IMPORTANT: The browser is NOT headless. It runs with a GUI. The user CAN interact with it directly.
Never say "this is a headless server" or "you need to open Chrome manually".

### Subsequent Use
1. `chrome(action="start_profile", name="google")` — reuses if already running
2. `chrome(action="navigate", url="https://example.com")` — navigate
3. `chrome(action="screenshot")` — verify page (auto-sent to chat)
4. Do work: navigate, click, fill, evaluate as needed
5. `chrome(action="stop_profile")` — only when completely done

### Common Actions
```
# Profile management (only needed once per session)
chrome(action="list_profiles")
chrome(action="start_profile", name="twitter")
chrome(action="stop_profile")
chrome(action="delete_profile", name="old-profile")

# Page interaction (use freely while browser is open)
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

- **Browser stays open** between messages — no need to restart for each request
- **Google/Material Web sites**: DOM `click()` may not work. Use `evaluate` with `mouse.click()` coordinates or find the inner `<input>` element
- **XPath selectors**: Start with `/` or `(//`. Example: `//button[text()="Save"]`
- **Login detection**: After starting a profile, take a screenshot or evaluate JS to check if session is active
- **Only stop_profile when fully done** — don't stop between consecutive requests
- Use `/ban chrome` to disable, `/approve chrome` to re-enable
