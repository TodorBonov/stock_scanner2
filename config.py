"""
Configuration constants and settings
Centralizes hardcoded values for easier maintenance

This file contains all configuration variables for the Minervini SEPA Scanner.
All Minervini-specific thresholds, periods, and criteria are defined here,
making it easy to adjust parameters without modifying the scanner logic.
"""
from pathlib import Path

# ============================================================================
# API CONFIGURATION
# ============================================================================

# API Rate Limiting
DEFAULT_RATE_LIMIT_DELAY = 0.5  # seconds between API calls
# Purpose: Prevents overwhelming data providers with too many requests
# Used by: Trading212Client, StockDataProvider
# Why important: Avoids rate limiting errors and potential IP bans

POSITION_EVALUATION_DELAY = 0.5  # seconds between position evaluations
# Purpose: Delay between evaluating multiple positions
# Used by: Trading bot position management
# Why important: Prevents rapid-fire API calls that could trigger rate limits

MAX_API_RETRIES = 3
# Purpose: Maximum number of retry attempts for failed API calls
# Used by: All API clients
# Why important: Handles temporary network issues without infinite loops

# API Timeouts
TRADING212_API_TIMEOUT = 30  # seconds for Trading212 API calls
# Purpose: Maximum time to wait for Trading212 API response
# Used by: Trading212Client
# Why important: Prevents hanging on slow/unresponsive API calls

OPENAI_API_TIMEOUT = 60  # seconds for OpenAI API calls
# Purpose: Maximum time to wait for OpenAI API response
# Used by: AI analysis features (if enabled)
# Why important: AI calls can take longer, so timeout is more generous

# ChatGPT (06, 07) – model for existing-positions and new-positions analysis
# See https://platform.openai.com/docs/models (e.g. gpt-5.2, gpt-5.2-pro, gpt-5-mini)
OPENAI_CHATGPT_MODEL = "gpt-5.2"
OPENAI_CHATGPT_MAX_COMPLETION_TOKENS = 64000  # Allow long analysis for many stocks (increase if output is truncated)
OPENAI_CHATGPT_MAX_A_GRADE_STOCKS = 9999  # Max A+ and A stocks in one prompt (9999 = send all)
OPENAI_CHATGPT_MAX_PRE_BREAKOUT_STOCKS = 9999  # Max pre-breakout setups in one prompt (9999 = send all)
OPENAI_CHATGPT_INCLUDE_FULL_SCAN_DATA = False  # If False, report omits duplicate "ORIGINAL SCAN DATA" block (smaller file)
OPENAI_CHATGPT_RETRY_ATTEMPTS = 3  # Retries on rate limit / transient errors
OPENAI_CHATGPT_RETRY_BASE_SECONDS = 60  # First backoff wait (then 120, 180...)

DATA_PROVIDER_TIMEOUT = 30  # seconds for data provider API calls
# Purpose: Maximum time to wait for stock data API responses
# Used by: StockDataProvider (yfinance, Alpha Vantage)
# Why important: Prevents hanging when data providers are slow

# Yahoo Finance batch download (rate-limit mitigation)
YF_BATCH_CHUNK_SIZE = 150  # tickers per chunk; smaller = gentler on Yahoo, more chunks = longer run
YF_BATCH_CHUNK_DELAY_SEC = 45  # seconds to wait between chunks to avoid rate limits

# ============================================================================
# SCORING CONFIGURATION
# ============================================================================

# Score Calculation Weights
TECHNICAL_SCORE_WEIGHT = 0.6
# Purpose: Weight for technical analysis score (60%)
# Used by: Overall stock scoring algorithm
# Why important: Determines how much technical vs fundamental analysis matters

FUNDAMENTAL_SCORE_WEIGHT = 0.4
# Purpose: Weight for fundamental analysis score (40%)
# Used by: Overall stock scoring algorithm
# Why important: Balances technical and fundamental factors in final score

# ============================================================================
# FILE PATH CONFIGURATION
# ============================================================================

# Default File Paths
DEFAULT_RULESET_PATH = "ruleset.json"
# Purpose: Path to trading ruleset configuration file
# Used by: Trading bot rule engine
# Why important: Centralizes trading rules configuration

DEFAULT_ENV_PATH = ".env"
# Purpose: Path to environment variables file
# Used by: All modules that need API keys or secrets
# Why important: Keeps sensitive credentials out of code

DEFAULT_LOG_DIR = "logs"
# Purpose: Directory where log files are stored
# Used by: Logger configuration
# Why important: Centralizes log file location

DEFAULT_LOG_FILE = "trading212_bot.log"
# Purpose: Default log file name
# Used by: Logger configuration
# Why important: Standardizes log file naming

# Cache and report paths
CACHE_FILE = Path("data/cached_stock_data.json")
# Purpose: Legacy cache path (optional; pipeline uses cached_stock_data_new_pipeline.json)
# Used by: cache_utils

FAILED_FETCH_LIST = Path("data/failed_fetch.txt")
# Purpose: List of tickers that failed to fetch (one per line), updated after each fetch
# Used by: fetch_utils.py (when run standalone)

# Ticker mapping: file-based mapping (T212 symbol -> Yahoo/data symbol) for manual resolution
TICKER_MAPPING_FILE = Path("data/ticker_mapping.json")
# Purpose: JSON file of ticker mappings; edit to fix mapping errors (see reportsV2/ticker_mapping_errors.txt)
# Used by: ticker_utils.py

# Ticker mapping errors: written each run that fetches; lists tickers that failed (possible mapping issues)
TICKER_MAPPING_ERRORS_FILE = Path("reportsV2/ticker_mapping_errors.txt")
# Purpose: After each fetch, list tickers with no data/error so you can add them to data/ticker_mapping.json
# Used by: fetch_utils.py

REPORTS_DIR = Path("reportsV2")
# Purpose: Directory for all reports (Pipeline V2)
# Used by: 03, 04, 05, 06, 07, position_sizing

# Pipeline data (01→07)
PREPARED_FOR_MINERVINI = Path("data/prepared_for_minervini.json")
# Purpose: Output of step 03; input to step 04. Stored for testing.
# Used by: 03_prepare_for_minervini.py (write), 04_generate_full_report.py (read)

# Pipeline V2 cache inputs (steps 01, 02 write; step 03 reads)
NEW_PIPELINE_CACHE = Path("data/cached_stock_data_new_pipeline.json")
# Purpose: Yahoo OHLCV cache from step 01.
# Used by: 01_fetch_yahoo_watchlist_V2.py (write), 03_prepare_for_minervini_V2.py (read)
NEW_PIPELINE_POSITIONS = Path("data/positions_new_pipeline.json")
# Purpose: Trading212 positions from step 02.
# Used by: 02_fetch_positions_trading212_V2.py (write), 03_prepare_for_minervini_V2.py (read)

PROBLEMS_WITH_TICKERS = REPORTS_DIR / "problems_with_tickers.txt"
# Purpose: Report of ticker mismatches, unmapped symbols, missing data (step 03).
# Used by: 03_prepare_for_minervini.py

SCAN_RESULTS_LATEST = REPORTS_DIR / "scan_results_latest.json"
# Purpose: Scan results JSON (written by 04, read by 05)
# Used by: 04_generate_full_report.py, 05_prepare_chatgpt_data.py

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Logging Configuration
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# Purpose: Format string for log messages
# Used by: Python logging module
# Why important: Ensures consistent, readable log format with timestamps

LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# Purpose: Date/time format in log messages
# Used by: Python logging module
# Why important: Standardizes timestamp format in logs

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
# Purpose: Maximum size of a single log file before rotation
# Used by: RotatingFileHandler
# Why important: Prevents log files from growing indefinitely

LOG_BACKUP_COUNT = 5
# Purpose: Number of backup log files to keep
# Used by: RotatingFileHandler
# Why important: Maintains log history while limiting disk usage

# ============================================================================
# INPUT VALIDATION CONFIGURATION
# ============================================================================

# Input Validation
MAX_TICKER_LENGTH = 20
# Purpose: Maximum allowed length for stock ticker symbols
# Used by: Ticker validation functions
# Why important: Prevents invalid ticker formats and potential injection

MAX_PATH_LENGTH = 260  # Windows path limit
# Purpose: Maximum file path length (Windows limitation)
# Used by: Path validation functions
# Why important: Prevents errors on Windows systems with long paths

ALLOWED_TICKER_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
# Purpose: Valid characters allowed in ticker symbols
# Used by: Ticker validation and cleaning functions
# Why important: Ensures ticker symbols are safe and valid

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# Security
MASKED_CREDENTIAL_LENGTH = 4  # Show last 4 chars when masking
# Purpose: Number of characters to show when masking sensitive data
# Used by: Credential masking functions (for logging)
# Why important: Allows identification while protecting sensitive information

# ============================================================================
# MINERVINI SEPA SCANNER CONFIGURATION
# ============================================================================
# All Minervini-specific thresholds, periods, and criteria
# Centralized here for easy adjustment without modifying scanner logic
#
# These values are based on Mark Minervini's SEPA (Stock Exchange Price Action)
# methodology as described in his books and training materials.
# ============================================================================

# ----------------------------------------------------------------------------
# TREND & STRUCTURE Variables
# ----------------------------------------------------------------------------
# Part 1 of Minervini's 5-part checklist - NON-NEGOTIABLE
# Ensures stock is in a Stage 2 uptrend with proper structure

SMA_50_PERIOD = 50  # 50-day Simple Moving Average
# Purpose: Short-term trend indicator (approximately 2.5 months)
# Used by: Trend & Structure check to determine if price is above short-term trend
# Why important: Minervini requires price above 50 SMA for Stage 2 uptrend
# Minervini's rule: Price must be above 50 SMA

SMA_150_PERIOD = 150  # 150-day Simple Moving Average
# Purpose: Medium-term trend indicator (approximately 7.5 months)
# Used by: Trend & Structure check to confirm intermediate trend
# Why important: Confirms stock is in sustained uptrend, not just short-term bounce
# Minervini's rule: Price must be above 150 SMA

SMA_200_PERIOD = 200  # 200-day Simple Moving Average
# Purpose: Long-term trend indicator (approximately 10 months)
# Used by: Trend & Structure check to confirm long-term uptrend
# Why important: Ensures stock is in Stage 2 (uptrend), not Stage 1 (base) or Stage 3 (decline)
# Minervini's rule: Price must be above 200 SMA (defines Stage 2)

MIN_DATA_DAYS = 200  # Minimum days of data required for analysis
# Purpose: Ensures enough historical data for accurate 200 SMA calculation
# Used by: Trend & Structure validation
# Why important: 200 SMA needs at least 200 days of data to be meaningful
# Minervini's rule: Need sufficient history to establish trend

SMA_SLOPE_LOOKBACK_DAYS = 20  # Days to compare for SMA slope check
# Purpose: Period to check if moving averages are rising (sloping up)
# Used by: Trend & Structure check to ensure SMAs are trending upward
# Why important: Rising SMAs confirm uptrend is strengthening, not weakening
# Minervini's rule: SMAs should be rising, not flat or declining

SMA_SLOPE_LOOKBACK_SHORT = 10  # Shorter lookback if insufficient data
# Purpose: Fallback period when full 20-day lookback isn't available
# Used by: Trend & Structure check for stocks with limited history
# Why important: Allows analysis of newer stocks while maintaining trend check

PRICE_FROM_52W_LOW_MIN_PCT = 30  # Minimum % above 52-week low
# Purpose: Ensures stock has already advanced significantly from lows
# Used by: Trend & Structure check
# Why important: Stocks near 52W lows are in Stage 1 (base) or Stage 4 (decline), not Stage 2
# Minervini's rule: Stock should be at least 30% above 52-week low

PRICE_FROM_52W_HIGH_MAX_PCT = 15  # Maximum % below 52-week high (Minervini: within 15%)
# Purpose: Ensures stock is near recent highs (not too far extended)
# Used by: Trend & Structure check
# Why important: Stocks more than 15% below high may be in late Stage 2 or Stage 3
# Minervini's rule: Stock should be within 15% of 52-week high

PRICE_TOO_CLOSE_TO_HIGH_PCT = 10  # Warning if within 10% of 52W high (late stage)
# Purpose: Flags stocks that may be in late Stage 2 (extended)
# Used by: Trend & Structure check (warning, not failure)
# Why important: Stocks very close to highs may be near exhaustion, higher risk
# Minervini's rule: Very close to high may indicate late-stage advance

# ----------------------------------------------------------------------------
# BASE QUALITY Variables
# ----------------------------------------------------------------------------
# Part 2 of Minervini's checklist
# Ensures consolidation base is of high quality (tight, controlled)

BASE_LENGTH_MIN_WEEKS = 3  # Minimum base length in weeks
# Purpose: Minimum consolidation period to form a valid base
# Used by: Base Quality check
# Why important: Bases shorter than 3 weeks are typically corrections, not consolidations
# Minervini's rule: Bases should be 3-8 weeks on daily chart

BASE_LENGTH_MAX_WEEKS = 8  # Maximum base length in weeks
# Purpose: Maximum consolidation period before base becomes too long
# Used by: Base Quality check
# Why important: Bases longer than 8 weeks may indicate weakening momentum
# Minervini's rule: Bases should be 3-8 weeks (optimal: 4-6 weeks)

BASE_DEPTH_MAX_PCT = 25  # Maximum base depth % (acceptable)
# Purpose: Maximum price decline within base (25% = acceptable, 15% = elite)
# Used by: Base Quality check
# Why important: Deeper bases (>25%) show more volatility and weaker structure
# Minervini's rule: Base depth should be ≤25% (≤15% is elite, preferred)

BASE_DEPTH_WARNING_PCT = 20  # Warning threshold for base depth
# Purpose: Flags bases that are deeper than ideal but still acceptable
# Used by: Base Quality check (warning, not failure)
# Why important: Bases 20-25% deep are acceptable but not as strong as <15%

BASE_DEPTH_ELITE_PCT = 15  # Elite base depth % (preferred)
# Purpose: Preferred base depth for highest quality setups
# Used by: Base Quality check (for elite classification)
# Why important: Bases <15% deep show tight, controlled consolidation (best quality)
# Minervini's rule: Elite bases are ≤15% deep

BASE_VOLATILITY_MULTIPLIER = 1.5  # Base volatility vs avg volatility (reject if >1.5x)
# Purpose: Ensures base shows low volatility (tight consolidation)
# Used by: Base Quality check
# Why important: Bases with high volatility show "sloppy" price action, not tight consolidation
# Minervini's rule: Base should show lower volatility than average (tight candles)

CLOSE_POSITION_MIN_PCT = 50  # Minimum close position in daily range (was 60)
# Purpose: Ensures closes are in upper half of daily range (shows strength)
# Used by: Base Quality check
# Why important: Closes near highs show buyers in control, not sellers
# Minervini's rule: Closes should be in top 50% of daily range (prefer 60%+)

VOLUME_CONTRACTION_WARNING_BASE = 0.95  # Volume contraction warning threshold (was 0.90)
# Purpose: Flags bases where volume isn't contracting enough
# Used by: Base Quality check (warning, not failure)
# Why important: Volume should contract in base (dry up), showing lack of selling pressure
# Minervini's rule: Volume should contract in base (<95% of pre-base volume)

BASE_LOOKBACK_DAYS = 60  # Days to look back for base identification
# Purpose: Period to search for base patterns
# Used by: Base identification and quality checks
# Why important: 60 days covers typical base length (3-8 weeks = 15-40 trading days)

# ----------------------------------------------------------------------------
# BASE IDENTIFICATION Variables
# ----------------------------------------------------------------------------
# Used by the base identification algorithm to find consolidation patterns
# These are more lenient than Base Quality checks to catch potential bases

VOLATILITY_WINDOW = 10  # Rolling window for volatility calculation (~2 weeks)
# Purpose: Period for calculating rolling volatility to identify low-volatility periods
# Used by: Base identification algorithm
# Why important: Low volatility periods indicate consolidation (base formation)

LOW_VOL_THRESHOLD_MULTIPLIER = 0.85  # Volatility threshold multiplier (was 0.75)
# Purpose: Threshold for identifying low volatility (85% of average = low vol)
# Used by: Base identification algorithm
# Why important: More lenient threshold catches more potential bases
# Note: 0.85 means volatility must be <85% of average to be considered "low"

LOW_VOL_MIN_DAYS = 10  # Minimum consecutive low volatility days
# Purpose: Minimum days of low volatility to identify a potential base
# Used by: Base identification algorithm
# Why important: Ensures base is sustained, not just a few quiet days

LOW_VOL_PERCENTAGE_THRESHOLD = 0.55  # Percentage of days that must be low vol (was 0.60)
# Purpose: Alternative method - 55% of recent days must be low volatility
# Used by: Base identification algorithm (percentage-based approach)
# Why important: Catches bases even if not perfectly consecutive

LOW_VOL_MIN_DAYS_FOR_PCT = 15  # Minimum days required for percentage check
# Purpose: Minimum period needed to apply percentage-based base identification
# Used by: Base identification algorithm
# Why important: Ensures sufficient data for percentage calculation

BASE_LENGTH_MIN_WEEKS_IDENTIFY = 2  # Minimum weeks for base identification
# Purpose: More lenient minimum for base identification (vs 3 weeks for quality check)
# Used by: Base identification algorithm
# Why important: Catches shorter bases that might still be valid

BASE_LENGTH_MAX_WEEKS_IDENTIFY = 12  # Maximum weeks for base identification
# Purpose: More lenient maximum for base identification (vs 8 weeks for quality check)
# Used by: Base identification algorithm
# Why important: Catches longer bases that might still be valid

BASE_DEPTH_MAX_PCT_IDENTIFY = 35  # Maximum depth % for base identification
# Purpose: More lenient depth threshold for base identification (vs 25% for quality)
# Used by: Base identification algorithm
# Why important: Catches deeper bases that might still be valid

RANGE_30D_THRESHOLD_PCT = 15  # 30-day price range threshold
# Purpose: If 30-day price range is ≤15%, it may be a base
# Used by: Base identification algorithm (range-based method)
# Why important: Small price ranges indicate consolidation

RANGE_60D_THRESHOLD_PCT = 25  # 60-day price range threshold
# Purpose: If 60-day price range is ≤25%, it may be a base
# Used by: Base identification algorithm (range-based method)
# Why important: Alternative method for identifying consolidation periods

ADVANCE_DECLINE_THRESHOLD_PCT = 10  # Reject if price declined >10% (not a base)
# Purpose: Ensures base follows an advance (not a decline)
# Used by: Base identification algorithm
# Why important: Bases should form after advances, not during declines
# Minervini's rule: Base must follow an advance (advance-before-base pattern)

# ----------------------------------------------------------------------------
# RELATIVE STRENGTH Variables
# ----------------------------------------------------------------------------
# Part 3 of Minervini's checklist - CRITICAL
# Ensures stock is outperforming the market and showing strong momentum

RSI_PERIOD = 14  # RSI calculation period
# Purpose: Standard RSI period (14 days is industry standard)
# Used by: Relative Strength check
# Why important: RSI measures momentum; Minervini requires RSI >60 before breakout
# Minervini's rule: RSI(14) should be >60 before breakout

RSI_MIN_THRESHOLD = 60  # Minimum RSI value required
# Purpose: Minimum RSI to confirm strong momentum
# Used by: Relative Strength check
# Why important: RSI >60 shows strong buying pressure and momentum
# Minervini's rule: RSI must be >60 (preferably >70 for strongest stocks)

RS_LINE_DECLINE_WARNING_PCT = 5  # Warning if RS line >5% below recent high
# Purpose: Flags when relative strength line is declining
# Used by: Relative Strength check (warning, not failure)
# Why important: RS line decline may indicate weakening relative performance
# Minervini's rule: RS line should be near new highs

RS_LINE_DECLINE_FAIL_PCT = 10  # Fail if RS line >10% below recent high
# Purpose: Fails if relative strength line has declined significantly
# Used by: Relative Strength check
# Why important: RS line >10% below high shows significant relative weakness
# Minervini's rule: RS line should not decline >10% from recent high

RS_LOOKBACK_DAYS = 60  # Days to look back for RS line calculation
# Purpose: Period for calculating relative strength vs benchmark
# Used by: Relative Strength calculation
# Why important: 60 days provides meaningful comparison period (about 3 months)

RS_TREND_LOOKBACK_DAYS = 20  # Days to check RS line trend
# Purpose: Period to check if RS line is trending up
# Used by: Relative Strength check
# Why important: RS line should be trending up, not just at high level
# Minervini's rule: RS line should be trending upward

# ----------------------------------------------------------------------------
# VOLUME SIGNATURE Variables
# ----------------------------------------------------------------------------
# Part 4 of Minervini's checklist
# Ensures volume patterns confirm the setup (dry in base, expanding on breakout)

VOLUME_CONTRACTION_WARNING = 0.9  # Volume contraction warning (base volume vs pre-base)
# Purpose: Flags when base volume isn't contracting enough
# Used by: Volume Signature check (warning, not failure)
# Why important: Volume should contract in base (dry up), showing lack of selling
# Minervini's rule: Volume should be lower in base than before base

BREAKOUT_VOLUME_MULTIPLIER = 1.4  # Minimum volume increase for breakout (1.4x = 40%)
# Purpose: Minimum volume increase required on breakout day
# Used by: Volume Signature check
# Why important: Breakouts need volume confirmation (institutional buying)
# Minervini's rule: Breakout volume should be +40% or more above average

HEAVY_SELL_VOLUME_MULTIPLIER = 1.5  # Heavy sell volume threshold (1.5x base volume)
# Purpose: Flags heavy selling volume before breakout
# Used by: Volume Signature check
# Why important: Heavy sell volume before breakout is a red flag
# Minervini's rule: No heavy sell volume should occur before breakout

RECENT_DAYS_FOR_VOLUME = 5  # Days to check for recent volume
# Purpose: Period to check for breakout volume
# Used by: Volume Signature check
# Why important: Checks last 5 days for volume expansion on breakout

AVG_VOLUME_LOOKBACK_DAYS = 20  # Days for average volume calculation
# Purpose: Period for calculating average volume (baseline)
# Used by: Volume Signature and Breakout Rules checks
# Why important: 20-day average provides baseline for volume comparisons

# ----------------------------------------------------------------------------
# BREAKOUT RULES Variables
# ----------------------------------------------------------------------------
# Part 5 of Minervini's checklist
# Ensures breakout is valid and decisive (not a false breakout)

PIVOT_CLEARANCE_PCT = 2  # Minimum % above base high to clear pivot
# Purpose: Minimum price clearance above base high to confirm breakout
# Used by: Breakout Rules check
# Why important: 2% clearance ensures decisive breakout, not just touching high
# Minervini's rule: Price must clear pivot decisively (≥2% above base high)

BREAKOUT_LOOKBACK_DAYS = 5  # Days to check for breakout (try 10 for more names)
# Purpose: Period to check if breakout occurred
# Used by: Breakout Rules check
# Why important: Checks last 5 days, not just current day (catches recent breakouts)

BREAKOUT_LOOKBACK_DAYS_FOR_REPORT = 21  # Days to scan for "last close above pivot" (reporting only)
# Purpose: When reporting, find the most recent date price closed >= 2% above base high
# Used by: Breakout Rules details (last_above_pivot_date, days_since_breakout)

CLOSE_POSITION_MIN_PCT_BREAKOUT = 70  # Minimum close position in range (was 75%, top 30% vs 25%)
# Purpose: Ensures breakout day closes in top 30% of daily range
# Used by: Breakout Rules check
# Why important: Strong closes show buyers in control on breakout day
# Minervini's rule: Breakout day should close in top 25-30% of range

VOLUME_EXPANSION_MIN = 1.2  # Minimum volume expansion (1.2x = 20% increase)
# Purpose: Minimum volume increase on breakout day (or within volume confirmation window)
# Used by: Breakout Rules check
# Why important: Breakouts need volume confirmation (institutional participation)
# Minervini's rule: Breakout volume should be +20% minimum (prefer +40%+)

# Multi-day breakout / volume confirmation (trading improvement)
USE_MULTI_DAY_VOLUME_CONFIRMATION = True
# Purpose: When True, volume confirmation can occur on breakout day OR in the next N days
# Used by: Breakout Rules check
# Why important: In practice volume often spikes 1-2 days after pivot clearance; single-day requirement gave 0% pass rate

VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT = 2
# Purpose: Number of days after the breakout day to look for volume >= VOLUME_EXPANSION_MIN
# Used by: Breakout Rules when USE_MULTI_DAY_VOLUME_CONFIRMATION is True
# 0 = volume must be on breakout day only (strict); 1 or 2 = allow confirmation on next 1-2 days

# ----------------------------------------------------------------------------
# RELATIVE STRENGTH - Trading improvements (configurable)
# ----------------------------------------------------------------------------
# Benchmark is set per run via script args (e.g. 01/02 --benchmark ^GDAXI or ^GSPC)

RS_RELAX_LINE_DECLINE_IF_STRONG = True
# Purpose: When True, if stock outperforms benchmark AND RSI >= RSI_MIN_THRESHOLD, RS line decline from high is treated as warning only (no failure)
# Used by: Relative Strength check
# Why important: Single benchmark (e.g. DAX) can unfairly fail US names; strong RSI + outperformance still indicates strength

# ----------------------------------------------------------------------------
# BUY/SELL PRICE Variables
# ----------------------------------------------------------------------------
# Entry and exit price calculations based on Minervini's rules
# These determine where to buy, where to set stops, and profit targets

STOP_LOSS_PCT = 5.0  # Stop loss % below buy price (5% max loss)
# Purpose: Maximum loss per share before exiting position
# Used by: Buy/Sell price calculation
# Why important: Cut losses at 5% to preserve capital (R/R 2:1 with 10% target)

PROFIT_TARGET_1_PCT = 10.0  # First profit target % above entry (10% targeted win)
# Purpose: First profit-taking level (take partial profits)
# Used by: Buy/Sell price calculation
# Why important: Target 10% gain for 2:1 risk/reward vs 5% stop

PROFIT_TARGET_2_PCT = 45.0  # Second profit target % above entry (40-50% range)
# Purpose: Second profit-taking level (let winners run)
# Used by: Buy/Sell price calculation
# Why important: Let strong winners continue, trail stop after 40-50% gain
# Minervini's rule: Let winners run to 40-50%, then trail stop

BUY_PRICE_BUFFER_PCT = 2  # Buy when price is 2% above pivot (breakout confirmation)
# Purpose: Confirmation threshold for breakout (2% above pivot)
# Used by: Buy/Sell price calculation and Breakout Rules check
# Why important: 2% clearance confirms breakout is real, not false
# Minervini's rule: Buy when price clears pivot by 2% or more

# ----------------------------------------------------------------------------
# ATR STOP (optional volatility-based stop)
# ----------------------------------------------------------------------------
USE_ATR_STOP = False  # When True, report also shows ATR-based stop (in addition to fixed %)
ATR_PERIOD = 14  # Period for ATR calculation
ATR_STOP_MULTIPLIER = 1.5  # Stop = buy_price - ATR * this multiplier

# ----------------------------------------------------------------------------
# MARKET REGIME (optional)
# ----------------------------------------------------------------------------
REQUIRE_MARKET_ABOVE_200SMA = False  # When True, report shows market regime; optional filter
# Market benchmark for regime: use same as RS benchmark per run if None

# ----------------------------------------------------------------------------
# BASE RECENCY (optional filter)
# ----------------------------------------------------------------------------
BASE_MAX_DAYS_OLD = 0  # 0 = off. When >0, flag/exclude bases older than N days in pre-breakout

# ----------------------------------------------------------------------------
# GRADING Variables
# ----------------------------------------------------------------------------
# Determines overall grade (A+, A, B, C, F) based on checklist results
# Grades determine position sizing recommendations

MAX_FAILURES_FOR_A = 2  # Maximum failures for A grade
# Purpose: Maximum number of failed criteria to still get A grade
# Used by: Grade calculation
# Why important: A grade stocks can have 1-2 minor flaws but still be good setups
# Minervini's rule: 1-2 minor flaws = Half position (A grade)

MAX_FAILURES_FOR_B = 4  # Maximum failures for B grade
# Purpose: Maximum number of failed criteria to get B grade
# Used by: Grade calculation
# Why important: B grade stocks have more issues but may still be watchable
# Minervini's rule: More than 2 failures = Watch list (B grade) or avoid

CRITICAL_FAILURE_GRADE = "F"  # Grade if trend & structure fails
# Purpose: Automatic F grade if Trend & Structure fails (non-negotiable)
# Used by: Grade calculation
# Why important: Trend & Structure is NON-NEGOTIABLE - if it fails, stock is F grade
# Minervini's rule: Trend & Structure failure = WALK AWAY (F grade)

# ============================================================================
# MINERVINI V2 PIPELINE CONFIGURATION
# ============================================================================
# Scanner V2: structural eligibility, composite scoring, grade bands, report paths.
# Used by: minervini_scanner_v2, minervini_report_v2, steps 04–07.

# ----------------------------------------------------------------------------
# STRUCTURAL ELIGIBILITY (V2)
# ----------------------------------------------------------------------------
MIN_AVG_DOLLAR_VOLUME_20D = 1_000_000.0  # $1M minimum liquidity
MIN_PRICE_THRESHOLD = 5.0  # Avoid penny stocks

# ----------------------------------------------------------------------------
# PRIOR RUN (V2) – base must follow meaningful advance
# ----------------------------------------------------------------------------
MIN_PRIOR_RUN_PCT = 25.0  # prior_run_pct = (base_high - lowest_3m_before_base) / lowest_3m_before_base * 100
PRIOR_RUN_LOOKBACK_TRADING_DAYS = 63   # ~3 months before base
PRIOR_RUN_REQUIRED_FOR_ELIGIBILITY = True  # If True, prior_run < MIN_PRIOR_RUN_PCT → REJECT

# ----------------------------------------------------------------------------
# RS PERCENTILE (V2) – computed across universe after scan
# ----------------------------------------------------------------------------
RS_3M_LOOKBACK_DAYS = 63   # ~3 months for 3M return
RS_6M_LOOKBACK_DAYS = 126  # Optional 6M return

# ----------------------------------------------------------------------------
# BASE TYPE CLASSIFICATION (V2)
# ----------------------------------------------------------------------------
BASE_TYPE_FLAT_MAX_DEPTH_PCT = 15.0       # depth ≤ 15% → flat_base
BASE_TYPE_HIGH_TIGHT_PRIOR_RUN_PCT = 100.0  # prior_run ≥ 100%
BASE_TYPE_HIGH_TIGHT_MAX_DEPTH_PCT = 25.0   # depth ≤ 25%
BASE_TYPE_HIGH_TIGHT_MAX_WEEKS = 5.0        # base ≤ 5 weeks

# ----------------------------------------------------------------------------
# PIVOT BY BASE TYPE (V2)
# ----------------------------------------------------------------------------
PIVOT_SPIKE_FILTER_ENABLED = True
PIVOT_SPIKE_STD_MULTIPLIER = 2.0
PIVOT_IGNORE_SPIKE_WITHIN_LAST_N_DAYS = 5
PIVOT_HANDLE_DAYS = 7  # For cup: handle = last N trading days

# ----------------------------------------------------------------------------
# TREND SCORE – graded by % above 200 SMA (V2)
# ----------------------------------------------------------------------------
TREND_PCT_ABOVE_200_TIER1 = 30.0   # ≥30% above 200 SMA → 100
TREND_PCT_ABOVE_200_TIER2 = 15.0   # 15–30% → 70
TREND_PCT_ABOVE_200_TIER3 = 5.0    # 5–15% → 40
TREND_PCT_ABOVE_200_TIER4 = 0.0    # 0–5% → 15; below 0 → 0

# ----------------------------------------------------------------------------
# BASE QUALITY BONUSES (V2)
# ----------------------------------------------------------------------------
BASE_BONUS_RANGE_CONTRACTION_LAST_2W = 10
BASE_BONUS_WEEKLY_CLOSES_UPPER_40 = 10
BASE_RANGE_CONTRACTION_RATIO_MAX = 0.5

# ----------------------------------------------------------------------------
# POWER RANK
# ----------------------------------------------------------------------------
POWER_RANK_PRIOR_RUN_CAP = 100.0

# ----------------------------------------------------------------------------
# COMPOSITE SCORING WEIGHTS (V2)
# ----------------------------------------------------------------------------
WEIGHT_TREND_STRUCTURE = 0.20   # 20%
WEIGHT_BASE_QUALITY = 0.25      # 25%
WEIGHT_RELATIVE_STRENGTH = 0.25 # 25%
WEIGHT_VOLUME_SIGNATURE = 0.15  # 15%
WEIGHT_BREAKOUT_QUALITY = 0.15  # 15%

# ----------------------------------------------------------------------------
# COMPOSITE GRADE BANDS (V2)
# ----------------------------------------------------------------------------
GRADE_A_PLUS_MIN_SCORE = 85.0   # ≥85 → A+
GRADE_A_MIN_SCORE = 75.0        # 75–84 → A
GRADE_B_MIN_SCORE = 65.0        # 65–74 → B
GRADE_C_MIN_SCORE = 55.0        # 55–64 → C
MIN_RS_PERCENTILE_FOR_A_PLUS = 80.0
MIN_RS_PERCENTILE_FOR_A = 70.0

# ----------------------------------------------------------------------------
# ATR STOP (V2)
# ----------------------------------------------------------------------------
USE_ATR_STOP_V2 = True
ATR_PERIOD_V2 = 14
ATR_STOP_MULTIPLIER_V2 = 1.5
ATR_STOP_LOWEST_LOW_DAYS = 5

# ----------------------------------------------------------------------------
# EXTENDED / DISTANCE TO PIVOT (V2)
# ----------------------------------------------------------------------------
EXTENDED_DISTANCE_PCT = 8.0
EXTENDED_RISK_WARNING_PCT = 15.0

# ----------------------------------------------------------------------------
# BREAKOUT SCORE BANDS (V2)
# ----------------------------------------------------------------------------
BREAKOUT_SCORE_TIGHT_LOW_PCT = -3
BREAKOUT_SCORE_TIGHT_HIGH_PCT = 0
BREAKOUT_SCORE_NEAR_LOW_PCT = -5
BREAKOUT_SCORE_NEAR_HIGH_PCT = -3

# ----------------------------------------------------------------------------
# BASE QUALITY SCORE BANDS (V2)
# ----------------------------------------------------------------------------
BASE_SCORE_DEPTH_ELITE_PCT = 15
BASE_SCORE_DEPTH_GOOD_PCT = 20
BASE_SCORE_PRIOR_RUN_BONUS = 10
BASE_SCORE_PRIOR_RUN_PENALTY = -20
BASE_SCORE_LENGTH_IDEAL_MIN_WEEKS = 5.0
BASE_SCORE_LENGTH_IDEAL_MAX_WEEKS = 8.0
BASE_SCORE_LENGTH_SHORT_PENALTY_WEEKS = 4.0
BASE_SCORE_LENGTH_IDEAL_BONUS = 5
BASE_SCORE_LENGTH_SHORT_PENALTY = -5

# ----------------------------------------------------------------------------
# VOLUME SCORE BANDS (V2)
# ----------------------------------------------------------------------------
VOLUME_SCORE_STRONG_CONTRACTION = 0.8
VOLUME_SCORE_MODERATE_CONTRACTION = 0.95

# ----------------------------------------------------------------------------
# BASE RECENCY (V2)
# ----------------------------------------------------------------------------
BASE_LAST_N_DAYS_RANGE_CONTRACTION = 10

# ----------------------------------------------------------------------------
# EARLY CANDIDATES (report section only)
# ----------------------------------------------------------------------------
EARLY_TREND_SCORE_MIN = 40.0
EARLY_TREND_SCORE_MAX = 70.0
EARLY_RS_PERCENTILE_MIN = 50.0
EARLY_RS_PERCENTILE_MAX = 80.0
EARLY_DIST_TO_PIVOT_MIN_PCT = -5.0
EARLY_DIST_TO_PIVOT_MAX_PCT = 0.0
EARLY_MAX_ROWS = 40

# ----------------------------------------------------------------------------
# V2 OUTPUT PATHS
# ----------------------------------------------------------------------------
REPORTS_DIR_V2 = Path("reportsV2")
SCAN_RESULTS_V2_LATEST = REPORTS_DIR_V2 / "scan_results_v2_latest.json"
USER_REPORT_SUBDIR_V2 = ""
SEPA_USER_REPORT_PREFIX = "sepa_scan_user_report_"
SEPA_CSV_PREFIX = "sepa_scan_summary_"