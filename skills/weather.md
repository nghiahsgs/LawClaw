# Weather

Get current weather and forecasts. No API key needed.

## When to Use

- User asks about weather, temperature, or forecasts
- "Will it rain today?"
- "Temperature in Hanoi"
- Cron jobs for daily weather alerts

## How to Get Weather

Use `web_fetch` with wttr.in (free, no API key):

### Current weather (one-liner)

```
web_fetch url="https://wttr.in/Hanoi?format=3"
```

### Detailed forecast

```
web_fetch url="https://wttr.in/Hanoi?format=j1"
```

Returns JSON with current conditions + 3-day forecast.

### Custom format

```
web_fetch url="https://wttr.in/Hanoi?format=%l:+%c+%t+(feels+like+%f),+%w+wind,+%h+humidity"
```

Format codes: `%c` condition, `%t` temp, `%f` feels like, `%w` wind, `%h` humidity, `%p` precipitation.

## Tips

- Always include city name in the URL
- Use `format=j1` for structured JSON (best for cron jobs)
- Supports airport codes: `wttr.in/SGN` (Ho Chi Minh City)
- For cron jobs, save last weather to memory and compare changes
