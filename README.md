# Minervini SEPA Scanner

A professional-grade stock scanner that implements Mark Minervini's exact SEPA (Stock Exchange Price Action) methodology for European stocks. This scanner evaluates stocks against Minervini's complete checklist: Trend & Structure, Base Quality, Relative Strength, Volume Signature, and Breakout Rules.

## Features

1. **Complete Minervini SEPA Checklist**: Implements all 5 parts of Minervini's methodology
   - ✅ Trend & Structure (NON-NEGOTIABLE)
   - ✅ Base Quality (3-8 week bases, ≤25% depth)
   - ✅ Relative Strength (RS line, RSI > 60)
   - ✅ Volume Signature (dry volume in base, +40% on breakout)
   - ✅ Breakout Day Rules (pivot clearance, volume expansion)

2. **Automatic Grading**: Stocks receive A+, A, B, C, or F grades
   - **A+**: All criteria met → Full position
   - **A**: 1-2 minor flaws → Half position
   - **B/C/F**: More than 2 flaws → Walk away

3. **European Market Focus**: Optimized for SEPA stocks
   - Supports DAX (^GDAXI), CAC 40 (^FCHI), AEX (^AEX), Swiss (^SSMI), Nordics (^OMX), and others (e.g. ^GSPC). Use `--benchmark` on steps 01/02. Mixed watchlists can use per-ticker benchmarks via `benchmark_mapping.py`.
   - Relative strength calculated vs chosen benchmark

4. **Free Data Sources**: Uses Yahoo Finance (yfinance) as primary data source
   - No API key required for basic scanning
   - Alpha Vantage optional for additional data

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Optional: Get Alpha Vantage API Key (Optional)

For additional data coverage, get a free Alpha Vantage key:
1. Go to https://www.alphavantage.co/support/#api-key
2. Get your free API key
3. Add to `.env` file: `ALPHA_VANTAGE_API_KEY=your_key_here`

**Note**: The scanner works with just Yahoo Finance (yfinance) - no API key needed!

### 3. Configure (Optional)

Create a `.env` file in the project root (optional). Copy `config.example.env` and fill in as needed:
```
ALPHA_VANTAGE_API_KEY=your_key_here
# For position suggestions (step 05):
TRADING212_API_KEY=your_key_here
TRADING212_API_SECRET=your_secret_here
```

## Quick Start

Run the pipeline in order (see **PIPELINES.md** for details):

```powershell
python New1_fetch_yahoo_watchlist.py
python New2_fetch_positions_trading212.py
python New3_prepare_chatgpt_data.py
python New4_chatgpt_existing_positions.py
python New5_chatgpt_new_positions.py
```

- **New1** fetches OHLCV from Yahoo for your watchlist → `data/cached_stock_data_new_pipeline.json`
- **New2** fetches open positions from Trading 212 → `data/positions_new_pipeline.json` (optional if you only want new-position suggestions)
- **New3** runs the Minervini scan and prepares JSON for ChatGPT → `reports/new_pipeline/prepared_*.json`
- **New4** sends existing positions to ChatGPT for hold/add/trim/exit analysis
- **New5** sends A+/A new-position candidates to ChatGPT for entry evaluation

Optional 6-month OHLCV variant: run `New3_prepare_chatgpt_data_6mo.py` after New3, then `New4_chatgpt_existing_positions_6mo.py` and `New5_chatgpt_new_positions_6mo.py`. See `reports/new_pipeline/TOKEN_COMPARISON_ORIGINAL_VS_6MO.md`.

## Usage

Run in order: New1 → New2 → New3 → New4 → New5. Data paths: `data/cached_stock_data_new_pipeline.json`, `data/positions_new_pipeline.json`, `reports/new_pipeline/`. Full details: **PIPELINES.md**.

You can also run **02_generate_full_report.py** standalone for a Minervini report (it uses `data/cached_stock_data.json`; use `--refresh` to fetch into that cache, or run **New1** which writes to `data/cached_stock_data_new_pipeline.json` for the pipeline).

## Minervini SEPA Criteria Explained

### PART 1: Trend & Structure (NON-NEGOTIABLE)

**All of these must pass, or it's NOT SEPA:**
- ✅ Price above 50, 150, 200 SMA
- ✅ 50 SMA > 150 SMA > 200 SMA
- ✅ All three SMAs sloping UP
- ✅ Price ≥ 30% above 52-week low
- ✅ Price within 10–15% of 52-week high

### PART 2: Base Quality

**This is where amateurs fail:**
- ✅ Base length 3–8 weeks (daily chart)
- ✅ Depth ≤ 20–25% (≤15% is elite)
- ✅ No wide, sloppy candles
- ✅ Tight closes near highs
- ✅ Volume contracts inside base

### PART 3: Relative Strength (CRITICAL)

**Minervini buys strength, not value:**
- ✅ RS line near or at new highs
- ✅ Stock outperforms index (DAX / STOXX / FTSE)
- ✅ RSI(14) > 60 before breakout

### PART 4: Volume Signature

- ✅ Dry volume in base
- ✅ Breakout volume +40% or more
- ✅ No heavy sell volume before breakout

### PART 5: Breakout Day Rules

- ✅ Clears pivot decisively
- ✅ Closes in top 25–30% of range
- ✅ Volume expansion present

## Output Format

The scanner provides detailed results for each stock:

```
================================================================================
[STOCK] AAPL - Grade: A+ | Meets Criteria: True | Position Size: Full
================================================================================

[PRICE] Price Information:
   Current Price: $175.50
   52-Week High: $198.23
   52-Week Low: $124.17
   From 52W High: 11.5%
   From 52W Low: 41.3%

[PART 1] Trend & Structure (NON-NEGOTIABLE):
   Status: ✅ PASSED
   Price above 50 SMA: True
   Price above 150 SMA: True
   Price above 200 SMA: True
   SMA Order (50>150>200): True
   50 SMA: $165.20
   150 SMA: $155.80
   200 SMA: $150.30

[PART 2] Base Quality:
   Status: ✅ PASSED
   Base Length: 5.2 weeks (need 3-8)
   Base Depth: 12.3% (need ≤25%, ≤15% elite)
   Volume Contraction: 0.75x
   Avg Close Position: 68.5% of range

... (and so on for all 5 parts)
```

## Position Sizing Rules

Based on Minervini's methodology:

- **A+ Grade**: All boxes checked → **Full position**
- **A Grade**: 1–2 minor flaws → **Half position**
- **B/C/F Grade**: More than 2 flaws → **WALK AWAY**

## Project Structure

Key files:

```
.
├── PIPELINES.md                # Pipeline run order and data paths
├── New1_fetch_yahoo_watchlist.py       # Fetch Yahoo → new_pipeline cache
├── New2_fetch_positions_trading212.py  # T212 positions
├── New3_prepare_chatgpt_data.py        # Prepare JSON for ChatGPT (existing + A+/A)
├── New3_prepare_chatgpt_data_6mo.py    # Same, 6 months OHLCV only
├── New4_chatgpt_existing_positions.py  # ChatGPT existing positions
├── New4_chatgpt_existing_positions_6mo.py
├── New5_chatgpt_new_positions.py       # ChatGPT new position candidates
├── New5_chatgpt_new_positions_6mo.py
├── fetch_utils.py              # Shared fetch logic (load_watchlist, fetch_stock_data, fetch_all_data)
├── 02_generate_full_report.py  # Minervini scan (used by New3; can run standalone, --refresh uses fetch_utils)
├── bot.py                      # Main bot interface
├── minervini_scanner.py        # Core Minervini SEPA scanner logic
├── data_provider.py            # Data fetching (yfinance, Alpha Vantage)
├── trading212_client.py        # Trading 212 API client
├── config.py                   # Configuration and paths
├── cache_utils.py              # Cache load/save
├── benchmark_mapping.py        # Per-ticker benchmark for mixed watchlists
├── openai_utils.py             # OpenAI API helpers (New4, New5)
├── config.example.env          # Example .env (copy to .env)
├── requirements.txt            # Python dependencies
├── watchlist.txt               # Ticker list for scanning
├── data/                       # cached_stock_data_new_pipeline.json, positions_new_pipeline.json
├── reports/new_pipeline/       # Prepared JSON and ChatGPT reports
└── tests/                      # Unit tests
```

## Data Sources

- **Yahoo Finance (yfinance)**: Primary data source (free, no API key needed)
  - Historical price/volume data
  - Moving averages
  - RSI calculations
  - 52-week highs/lows

- **Alpha Vantage** (optional): Additional data coverage
  - Free tier: 25 requests/day
  - Premium: Higher limits

- **Trading 212 API** (optional): For stock search functionality

## Important Notes

⚠️ **This scanner is for educational purposes. Always:**
- Test thoroughly before using with real money
- Start with small positions
- Never risk more than you can afford to lose
- Review all recommendations manually
- Understand that past performance doesn't guarantee future results
- This implements Minervini's methodology but is not financial advice

✅ **What This Scanner Does:**
- ✅ Real technical analysis (SMAs, RSI, volume patterns)
- ✅ Real base identification and quality assessment
- ✅ Real relative strength calculations vs benchmarks
- ✅ Real breakout pattern detection
- ✅ Complete Minervini checklist evaluation

## Example Workflow

1. **Screen stocks** using TradingView or your preferred screener with basic filters:
   - Close > SMA50
   - SMA50 > SMA150
   - SMA150 > SMA200
   - RSI(14) > 60
   - Close within 15% of 52W high
   - Average Volume > 300k

2. **Export ticker list** from your screener

3. **Run the pipeline** (after adding tickers to `watchlist.txt`):
   ```powershell
   python New1_fetch_yahoo_watchlist.py
   python New2_fetch_positions_trading212.py
   python New3_prepare_chatgpt_data.py
   python New4_chatgpt_existing_positions.py
   python New5_chatgpt_new_positions.py
   ```

4. **Review A+ and A graded stocks** for potential entries

5. **Apply pyramiding rules** (not automated - manual execution):
   - First Entry: Buy pivot breakout (0.5-1% risk per trade)
   - First Add: Add if stock moves +2-3% from entry with volume confirmation
   - Second Add: Add if price respects 10 SMA, no wide red candles

## Troubleshooting

### (Obsolete: .ps1 scripts removed; pipeline is Python only.)

PowerShell’s execution policy is blocking scripts. You can either:

- **Use the batch file** (no policy change): run `.\run_full_pipeline.cmd` instead of `.\run_full_pipeline.ps1`. It does the same thing.
- **Allow scripts for your user** (one-time): in PowerShell run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
  Then `.\run_full_pipeline.ps1` will work.

### "Unauthorized" (401) when running New2

**New2_fetch_positions_trading212.py** calls the **Trading 212 API** to fetch your open positions. If you see `401 Unauthorized` or "Failed to fetch positions", the API is rejecting your credentials.

**Common causes:**

1. **Wrong or expired API key/secret**  
   In Trading 212: **Invest** → **Settings** → **API** → create or regenerate your API key and secret. Copy both into `.env`:
   ```
   TRADING212_API_KEY=your_key_here
   TRADING212_API_SECRET=your_secret_here
   ```

2. **Demo vs Live**  
   This app uses the **Live** API (`live.trading212.com`). If your account or keys are for the **Demo** environment, the Live API will return 401. Use keys from your **Live** account.

3. **`.env` not loaded**  
   Run the script from the project root so that the `.env` file in that folder is found. The scripts load it automatically via `python-dotenv`.

**To run the rest of the pipeline without Trading 212:**  
Skip New2 and run New1 → New3 → New4 → New5. New4 will have no existing positions; New5 will still analyze A+/A new-position candidates.

## License

This project is provided as-is for educational purposes.

## Disclaimer

This software is for educational purposes only. Trading involves risk of loss. Always do your own research and consult with a financial advisor before making investment decisions. The authors are not responsible for any financial losses incurred from using this software.
