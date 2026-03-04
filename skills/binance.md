# Binance Market Data

Get real-time crypto prices, 24hr stats, and candlestick charts from Binance. No API key needed for public endpoints.

## When to Use

- User asks for price: "BTC bao nhiêu?", "ETH price", "giá DOGE"
- User asks for stats: "BTC tăng bao nhiêu hôm nay?", "volume 24h"
- User asks for chart: "vẽ chart BTC", "nến ETH 1h", "show me candles"

## Symbol Format

Always uppercase + USDT pair: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, etc.
If user says just "BTC" → use "BTCUSDT".

## Get Current Price

```
web_fetch url="https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
```

Returns JSON: `{"symbol":"BTCUSDT","price":"65000.12"}`

## Get 24hr Stats (price change, volume, high/low)

```
web_fetch url="https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
```

Key fields: `lastPrice`, `priceChangePercent`, `highPrice`, `lowPrice`, `volume`, `quoteVolume`

## Get Multiple Prices at Once

```
web_fetch url="https://api.binance.com/api/v3/ticker/price"
```

Returns all pairs. Filter from the JSON for the ones you need.

## Draw Candlestick Chart

Use the `binance_chart` tool — it fetches klines and generates a PNG chart.

```
binance_chart symbol="BTCUSDT" interval="1h" limit=100
```

Then use `send_file` to deliver the PNG to the user:
```
send_file path="binance_BTCUSDT_1h.png" caption="BTC/USDT — 1h chart"
```

### Intervals

| Code | Meaning |
|------|---------|
| `1m` | 1 minute |
| `5m` | 5 minutes |
| `15m` | 15 minutes |
| `1h` | 1 hour |
| `4h` | 4 hours |
| `1d` | 1 day |

Default: `1h`, limit: 100 candles.

## Tips

- For quick price check → use `web_fetch` with `/ticker/price`
- For "tăng bao nhiêu" / "pump chưa" → use `/ticker/24hr` for `priceChangePercent`
- For chart requests → use `binance_chart` then `send_file`
- Always format price with commas: `$65,432.10`
- Show % change with color hint: `+3.2% 🟢` or `-1.5% 🔴`
