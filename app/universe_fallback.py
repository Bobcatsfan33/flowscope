"""Bundled offline fallback universe.

Used when Wikipedia membership scraping fails (network down / layout change).
This is a curated large-cap set (Nasdaq-100 + major S&P 500 names) — enough to
keep the dashboard fully functional without any network membership lookup.
The live scraper in `universe.py` supersedes this with the full ~600 names.
"""
from __future__ import annotations

# Nasdaq-100 (heavy options-flow names) + large-cap S&P 500 staples.
FALLBACK_TICKERS: tuple[str, ...] = (
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "ADBE", "CRM", "AMD", "INTC", "CSCO", "QCOM", "TXN", "INTU", "AMAT", "MU",
    "ADI", "LRCX", "KLAC", "SNPS", "CDNS", "MRVL", "NXPI", "MCHP", "ON", "PANW",
    "CRWD", "FTNT", "ANET", "SMCI", "PLTR", "NOW", "WDAY", "TEAM", "DDOG",
    # Internet / media / consumer
    "NFLX", "CMCSA", "TMUS", "CHTR", "WBD", "EA", "TTWO", "ABNB", "BKNG",
    "MELI", "PYPL", "PDD", "SHOP", "UBER", "LYFT", "DASH", "ROKU", "PINS",
    "SNAP", "SPOT", "COIN", "HOOD", "SQ", "AFRM",
    # Consumer staples / discretionary
    "COST", "PEP", "KO", "PG", "WMT", "TGT", "HD", "LOW", "MCD", "SBUX", "NKE",
    "MDLZ", "MNST", "KDP", "KHC", "CL", "PM", "MO", "DIS", "CMG", "ORLY", "AZO",
    "LULU", "ROST", "MAR", "DPZ",
    # Healthcare / biotech / pharma
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "VRTX", "REGN", "ISRG", "MRNA", "BIIB", "IDXX", "CVS",
    "HUM", "CI", "ZTS", "ELV", "MDT", "SYK",
    # Financials
    "BRK-B", "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP", "SPGI",
    "BX", "KKR", "CB", "PGR", "USB", "PNC", "TFC", "COF", "MET", "AIG", "V", "MA",
    "FI", "FIS", "PYPL",
    # Industrials / energy / materials
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "WMB", "KMI",
    "CAT", "DE", "BA", "GE", "HON", "RTX", "LMT", "GD", "NOC", "UPS", "FDX",
    "UNP", "CSX", "EMR", "ETN", "PH", "ITW", "MMM", "LIN", "APD", "SHW", "FCX",
    "NEM", "NUE",
    # Comms / utilities / real estate
    "VZ", "T", "NEE", "DUK", "SO", "D", "AEP", "EXC", "PLD", "AMT", "EQIX",
    "CCI", "PSA", "O", "SPG",
    # High-flyers / momentum (frequent unusual flow)
    "MSTR", "SOFI", "RIVN", "LCID", "NIO", "DKNG", "CVNA", "GME", "AMC", "RBLX",
    "U", "NET", "SNOW", "ZS", "OKTA", "MDB", "TWLO", "DOCU", "ZM", "CART",
    "ARM", "DELL", "HPQ", "WDC", "STX", "GLW", "ORCL", "IBM", "ACN", "SAP",
)
