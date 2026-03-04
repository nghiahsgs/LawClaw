"""Binance chart tool — fetch klines and render a candlestick chart PNG."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from lawclaw.core.tools import Tool

VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


class BinanceChartTool(Tool):
    """Fetch OHLCV data from Binance and generate a candlestick chart PNG."""

    name = "binance_chart"
    description = (
        "Fetch candlestick (kline) data from Binance and render a chart PNG. "
        "Saves the image to the workspace — use send_file afterwards to deliver it. "
        "Returns the saved file path."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Trading pair symbol, e.g. 'BTCUSDT', 'ETHUSDT'.",
            },
            "interval": {
                "type": "string",
                "description": "Candle interval: 1m, 5m, 15m, 1h, 4h, 1d, etc. Default: 1h.",
                "default": "1h",
            },
            "limit": {
                "type": "integer",
                "description": "Number of candles to fetch (max 500, default 100).",
                "default": 100,
            },
        },
        "required": ["symbol"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    async def execute(  # type: ignore[override]
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> str:
        symbol = symbol.upper().strip()
        interval = interval.lower().strip()
        limit = max(10, min(limit, 500))

        if interval not in VALID_INTERVALS:
            return f"Error: invalid interval '{interval}'. Valid: {', '.join(sorted(VALID_INTERVALS))}"

        # --- Fetch klines ---
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        logger.debug("binance_chart: fetching {} {} x{}", symbol, interval, limit)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(BINANCE_KLINES_URL, params=params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return f"Binance API error {exc.response.status_code}: {exc.response.text[:300]}"
        except httpx.RequestError as exc:
            return f"Request failed: {exc}"

        raw = resp.json()
        if not raw:
            return f"No kline data returned for {symbol} {interval}."

        # Each kline: [open_time, open, high, low, close, volume, ...]
        try:
            import pandas as pd
            import mplfinance as mpf
            import matplotlib
            matplotlib.use("Agg")  # headless

            df = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ])
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df.set_index("open_time", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df.index.name = "Date"

        except ImportError as exc:
            return f"Missing dependency: {exc}. Install with: pip install mplfinance pandas"

        # --- Render chart ---
        filename = f"binance_{symbol}_{interval}.png"
        out_path = self._workspace / filename

        style = mpf.make_mpf_style(
            base_mpf_style="nightclouds",
            gridcolor="#2a2a2a",
            facecolor="#1a1a2e",
            edgecolor="#444",
            figcolor="#1a1a2e",
            y_on_right=True,
        )

        buf = io.BytesIO()
        mpf.plot(
            df,
            type="candle",
            style=style,
            title=f"\n{symbol} — {interval} ({limit} candles)",
            volume=True,
            savefig=dict(fname=buf, dpi=150, bbox_inches="tight"),
            tight_layout=True,
            figratio=(16, 9),
            figscale=1.2,
        )

        buf.seek(0)
        out_path.write_bytes(buf.read())

        logger.info("binance_chart: saved {} ({} candles)", out_path.name, len(df))
        return f"Chart saved: {filename}  ({len(df)} candles, {interval})"
