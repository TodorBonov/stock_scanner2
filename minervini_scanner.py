"""
Minervini SEPA (Stock Exchange Price Action) Scanner
Implements Mark Minervini's exact screening criteria for European stocks
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from data_provider import StockDataProvider
from logger_config import get_logger
from config import (
    # Trend & Structure
    SMA_50_PERIOD, SMA_150_PERIOD, SMA_200_PERIOD, MIN_DATA_DAYS,
    SMA_SLOPE_LOOKBACK_DAYS, SMA_SLOPE_LOOKBACK_SHORT,
    PRICE_FROM_52W_LOW_MIN_PCT, PRICE_FROM_52W_HIGH_MAX_PCT, PRICE_TOO_CLOSE_TO_HIGH_PCT,
    # Base Quality
    BASE_LENGTH_MIN_WEEKS, BASE_LENGTH_MAX_WEEKS, BASE_DEPTH_MAX_PCT,
    BASE_DEPTH_WARNING_PCT, BASE_DEPTH_ELITE_PCT, BASE_VOLATILITY_MULTIPLIER,
    CLOSE_POSITION_MIN_PCT, VOLUME_CONTRACTION_WARNING_BASE, BASE_LOOKBACK_DAYS,
    # Base Identification
    VOLATILITY_WINDOW, LOW_VOL_THRESHOLD_MULTIPLIER, LOW_VOL_MIN_DAYS,
    LOW_VOL_PERCENTAGE_THRESHOLD, LOW_VOL_MIN_DAYS_FOR_PCT,
    BASE_LENGTH_MIN_WEEKS_IDENTIFY, BASE_LENGTH_MAX_WEEKS_IDENTIFY, BASE_DEPTH_MAX_PCT_IDENTIFY,
    RANGE_30D_THRESHOLD_PCT, RANGE_60D_THRESHOLD_PCT, ADVANCE_DECLINE_THRESHOLD_PCT,
    # Relative Strength
    RSI_PERIOD, RSI_MIN_THRESHOLD, RS_LINE_DECLINE_WARNING_PCT, RS_LINE_DECLINE_FAIL_PCT,
    RS_LOOKBACK_DAYS, RS_TREND_LOOKBACK_DAYS,
    # Volume Signature
    VOLUME_CONTRACTION_WARNING, BREAKOUT_VOLUME_MULTIPLIER, HEAVY_SELL_VOLUME_MULTIPLIER,
    RECENT_DAYS_FOR_VOLUME, AVG_VOLUME_LOOKBACK_DAYS,
    # Breakout Rules
    PIVOT_CLEARANCE_PCT, BREAKOUT_LOOKBACK_DAYS, BREAKOUT_LOOKBACK_DAYS_FOR_REPORT,
    CLOSE_POSITION_MIN_PCT_BREAKOUT, VOLUME_EXPANSION_MIN,
    USE_MULTI_DAY_VOLUME_CONFIRMATION, VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT,
    # RS trading improvement
    RS_RELAX_LINE_DECLINE_IF_STRONG,
    # Buy/Sell Prices
    STOP_LOSS_PCT, PROFIT_TARGET_1_PCT, PROFIT_TARGET_2_PCT, BUY_PRICE_BUFFER_PCT,
    USE_ATR_STOP, ATR_PERIOD, ATR_STOP_MULTIPLIER,
    # Market regime & base recency
    REQUIRE_MARKET_ABOVE_200SMA, BASE_MAX_DAYS_OLD,
    # Grading
    MAX_FAILURES_FOR_A, MAX_FAILURES_FOR_B, CRITICAL_FAILURE_GRADE
)

logger = get_logger(__name__)


class MinerviniScanner:
    """
    Scans stocks according to Mark Minervini's SEPA methodology
    Implements the complete checklist: Trend, Base Quality, Relative Strength, Volume, Breakout
    """
    
    def __init__(self, data_provider: StockDataProvider, benchmark: str = "^GDAXI"):
        """
        Initialize Minervini scanner
        
        Args:
            data_provider: StockDataProvider instance for fetching data
            benchmark: Benchmark index for relative strength (default: DAX for European stocks)
                       Options: ^GDAXI (DAX), ^FCHI (CAC 40), ^AEX (AEX), ^SSMI (Swiss), ^OMX (Nordics)
        """
        self.data_provider = data_provider
        self.benchmark = benchmark
        
    def scan_stock(self, ticker: str, benchmark_override: Optional[str] = None) -> Dict:
        """
        Scan a single stock against all Minervini SEPA criteria
        
        Args:
            ticker: Stock ticker symbol
            benchmark_override: If set, use this benchmark for RS (e.g. per-region: ^GSPC for US, ^GDAXI for EU)
            
        Returns:
            Dictionary with complete scan results including:
            - overall_grade: "A+", "A", "B", "C", or "F"
            - meets_criteria: Boolean
            - checklist: Detailed pass/fail for each criterion
            - position_size: "Full", "Half", or "None"
            - detailed_analysis: All calculated metrics
        """
        try:
            benchmark = benchmark_override if benchmark_override else self.benchmark
            logger.info(f"Scanning {ticker} for Minervini SEPA criteria (benchmark={benchmark})...")
            
            # Get historical data (need at least 1 year for 52-week calculations)
            hist = self.data_provider.get_historical_data(ticker, period="1y", interval="1d")
            if hist.empty or len(hist) < 200:
                return {
                    "ticker": ticker,
                    "error": "Insufficient historical data",
                    "meets_criteria": False,
                    "overall_grade": "F"
                }
            
            # Get stock info for fundamentals
            stock_info = self.data_provider.get_stock_info(ticker)
            
            # Identify base ONCE (performance optimization)
            lookback_days = min(60, len(hist))
            recent_data = hist.tail(lookback_days)
            base_info = self._identify_base(recent_data)
            
            # PART 1: Trend & Structure (NON-NEGOTIABLE)
            trend_results = self._check_trend_structure(hist, stock_info)
            
            # PART 2: Base Quality (pass base_info)
            base_results = self._check_base_quality(hist, base_info)
            
            # PART 3: Relative Strength (pass base_info; use benchmark_override when provided)
            rs_results = self._check_relative_strength(ticker, hist, base_info, benchmark=benchmark)
            
            # PART 4: Volume Signature (pass base_info)
            volume_results = self._check_volume_signature(hist, base_info)
            
            # PART 5: Breakout Day Rules (pass base_info)
            breakout_results = self._check_breakout_rules(hist, base_info)
            
            # Combine all results
            checklist = {
                "trend_structure": trend_results,
                "base_quality": base_results,
                "relative_strength": rs_results,
                "volume_signature": volume_results,
                "breakout_rules": breakout_results
            }
            
            # Calculate overall grade
            grade_result = self._calculate_grade(checklist)
            
            # Calculate buy/sell prices (entry/exit points)
            buy_sell_prices = self._calculate_buy_sell_prices(hist, base_info, checklist)
            
            return {
                "ticker": ticker,
                "overall_grade": grade_result["grade"],
                "meets_criteria": grade_result["meets_criteria"],
                "position_size": grade_result["position_size"],
                "checklist": checklist,
                "buy_sell_prices": buy_sell_prices,
                "detailed_analysis": {
                    "current_price": float(hist['Close'].iloc[-1]),
                    "52_week_high": float(hist['High'].tail(252).max()) if len(hist) >= 252 else float(hist['High'].max()),
                    "52_week_low": float(hist['Low'].tail(252).min()) if len(hist) >= 252 else float(hist['Low'].min()),
                    "price_from_52w_high_pct": grade_result.get("price_from_52w_high_pct", 0),
                    "price_from_52w_low_pct": grade_result.get("price_from_52w_low_pct", 0),
                },
                "stock_info": stock_info,
                "benchmark_used": benchmark,
            }
            
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}", exc_info=True)
            return {
                "ticker": ticker,
                "error": str(e),
                "meets_criteria": False,
                "overall_grade": "F"
            }
    
    def _check_trend_structure(self, hist: pd.DataFrame, stock_info: Dict) -> Dict:
        """
        PART 1: Trend & Structure (NON-NEGOTIABLE)
        
        Checks:
        - Price above 50, 150, 200 SMA
        - 50 SMA > 150 SMA > 200 SMA
        - All three SMAs sloping UP
        - Price ≥ 30% above 52-week low
        - Price within 10–15% of 52-week high
        """
        results = {
            "passed": True,
            "failures": [],
            "details": {}
        }
        
        try:
            current_price = hist['Close'].iloc[-1]
            
            # Calculate SMAs
            sma_50 = hist['Close'].rolling(window=SMA_50_PERIOD).mean()
            sma_150 = hist['Close'].rolling(window=SMA_150_PERIOD).mean()
            sma_200 = hist['Close'].rolling(window=SMA_200_PERIOD).mean()
            
            # Check if we have enough data
            if len(hist) < MIN_DATA_DAYS:
                results["passed"] = False
                results["failures"].append(f"Insufficient data for {MIN_DATA_DAYS} SMA")
                return results
            
            current_sma_50 = sma_50.iloc[-1]
            current_sma_150 = sma_150.iloc[-1]
            current_sma_200 = sma_200.iloc[-1]
            
            # Check price above SMAs
            above_50 = current_price > current_sma_50
            above_150 = current_price > current_sma_150
            above_200 = current_price > current_sma_200
            
            if not (above_50 and above_150 and above_200):
                results["passed"] = False
                if not above_50:
                    results["failures"].append("Price below 50 SMA")
                if not above_150:
                    results["failures"].append("Price below 150 SMA")
                if not above_200:
                    results["failures"].append("Price below 200 SMA")
            
            # Check SMA order: 50 > 150 > 200
            sma_order_correct = (current_sma_50 > current_sma_150 > current_sma_200)
            if not sma_order_correct:
                results["passed"] = False
                results["failures"].append("SMA order incorrect (50 SMA must be > 150 SMA > 200 SMA)")
            
            # Check SMAs sloping UP (compare current to configured days ago)
            if len(hist) >= (MIN_DATA_DAYS + SMA_SLOPE_LOOKBACK_DAYS):
                sma_50_slope = current_sma_50 > sma_50.iloc[-SMA_SLOPE_LOOKBACK_DAYS]
                sma_150_slope = current_sma_150 > sma_150.iloc[-SMA_SLOPE_LOOKBACK_DAYS]
                sma_200_slope = current_sma_200 > sma_200.iloc[-SMA_SLOPE_LOOKBACK_DAYS]
                
                if not (sma_50_slope and sma_150_slope and sma_200_slope):
                    results["passed"] = False
                    if not sma_50_slope:
                        results["failures"].append(f"{SMA_50_PERIOD} SMA not sloping up")
                    if not sma_150_slope:
                        results["failures"].append(f"{SMA_150_PERIOD} SMA not sloping up")
                    if not sma_200_slope:
                        results["failures"].append(f"{SMA_200_PERIOD} SMA not sloping up")
            else:
                # Use shorter period if needed
                if len(hist) >= (SMA_50_PERIOD + SMA_SLOPE_LOOKBACK_SHORT):
                    sma_50_slope = current_sma_50 > sma_50.iloc[-SMA_SLOPE_LOOKBACK_SHORT]
                    if not sma_50_slope:
                        results["passed"] = False
                        results["failures"].append(f"{SMA_50_PERIOD} SMA not sloping up")
            
            # Calculate 52-week high/low
            if len(hist) >= 252:
                year_data = hist.tail(252)
            else:
                year_data = hist
            
            week_52_high = year_data['High'].max()
            week_52_low = year_data['Low'].min()
            
            # Check price above 52-week low threshold
            price_from_low_pct = ((current_price - week_52_low) / week_52_low) * 100
            if price_from_low_pct < PRICE_FROM_52W_LOW_MIN_PCT:
                results["passed"] = False
                results["failures"].append(f"Price only {price_from_low_pct:.1f}% above 52W low (need ≥{PRICE_FROM_52W_LOW_MIN_PCT}%)")
            
            # Check price within range of 52-week high
            price_from_high_pct = ((week_52_high - current_price) / week_52_high) * 100
            if price_from_high_pct > PRICE_FROM_52W_HIGH_MAX_PCT:
                results["passed"] = False
                results["failures"].append(f"Price {price_from_high_pct:.1f}% below 52W high (need within {PRICE_FROM_52W_HIGH_MAX_PCT}%)")
            elif price_from_high_pct < PRICE_TOO_CLOSE_TO_HIGH_PCT:
                # Too close to high might indicate late stage
                results["failures"].append(f"Price very close to 52W high ({price_from_high_pct:.1f}%) - may be late stage")
            
            # Store details
            results["details"] = {
                "current_price": float(current_price),
                "sma_50": float(current_sma_50),
                "sma_150": float(current_sma_150),
                "sma_200": float(current_sma_200),
                "above_50": above_50,
                "above_150": above_150,
                "above_200": above_200,
                "sma_order_correct": sma_order_correct,
                "52_week_high": float(week_52_high),
                "52_week_low": float(week_52_low),
                "price_from_52w_low_pct": float(price_from_low_pct),
                "price_from_52w_high_pct": float(price_from_high_pct)
            }
            
        except Exception as e:
            logger.error(f"Error checking trend structure: {e}", exc_info=True)
            results["passed"] = False
            results["failures"].append(f"Error: {str(e)}")
        
        return results
    
    def _check_base_quality(self, hist: pd.DataFrame, base_info: Optional[Dict] = None) -> Dict:
        """
        PART 2: Base Quality
        
        Checks:
        - Base length 3–8 weeks (daily chart)
        - Depth ≤ 20–25% (≤15% is elite)
        - No wide, sloppy candles
        - Tight closes near highs
        - Volume contracts inside base
        """
        results = {
            "passed": True,
            "failures": [],
            "details": {}
        }
        
        try:
            # Use provided base_info if available, otherwise identify it
            if base_info is None:
                lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
                recent_data = hist.tail(lookback_days)
                base_info = self._identify_base(recent_data)
            
            if not base_info:
                results["passed"] = False
                results["failures"].append("No clear base pattern identified")
                return results
            
            base_length_weeks = base_info["length_weeks"]
            base_depth_pct = base_info["depth_pct"]
            base_data = base_info["data"]
            
            # Check base length
            if base_length_weeks < BASE_LENGTH_MIN_WEEKS or base_length_weeks > BASE_LENGTH_MAX_WEEKS:
                results["passed"] = False
                results["failures"].append(f"Base length {base_length_weeks:.1f} weeks (need {BASE_LENGTH_MIN_WEEKS}-{BASE_LENGTH_MAX_WEEKS} weeks)")
            
            # Check base depth
            if base_depth_pct > BASE_DEPTH_MAX_PCT:
                results["passed"] = False
                results["failures"].append(f"Base depth {base_depth_pct:.1f}% (need ≤{BASE_DEPTH_MAX_PCT}%, ≤{BASE_DEPTH_ELITE_PCT}% is elite)")
            elif base_depth_pct > BASE_DEPTH_WARNING_PCT:
                results["failures"].append(f"Base depth {base_depth_pct:.1f}% (acceptable but >{BASE_DEPTH_WARNING_PCT}%)")
            
            # Check for wide, sloppy candles (high volatility)
            base_volatility = base_data['Close'].pct_change(fill_method=None).std()
            avg_volatility = hist['Close'].pct_change(fill_method=None).tail(252).std()
            
            if base_volatility > avg_volatility * BASE_VOLATILITY_MULTIPLIER:
                results["passed"] = False
                results["failures"].append("Base shows high volatility (wide, sloppy candles)")
            
            # Check for tight closes near highs
            # Calculate average close position in daily range
            base_data['range_pct'] = ((base_data['Close'] - base_data['Low']) / 
                                      (base_data['High'] - base_data['Low'])) * 100
            avg_close_position = base_data['range_pct'].mean()
            
            if avg_close_position < CLOSE_POSITION_MIN_PCT:
                results["passed"] = False
                results["failures"].append(f"Closes not near highs (avg {avg_close_position:.1f}% of range)")
            
            # Check volume contracts inside base
            lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
            base_volume = base_data['Volume'].mean()
            pre_base_volume = hist.iloc[-(lookback_days + 20):-lookback_days]['Volume'].mean() if len(hist) > (lookback_days + 20) else base_volume
            
            # Make this a warning only, not a failure (volume can be slightly higher)
            if pre_base_volume > 0 and base_volume > pre_base_volume * VOLUME_CONTRACTION_WARNING_BASE:
                results["failures"].append(f"Volume not contracting in base (should be <{VOLUME_CONTRACTION_WARNING_BASE*100:.0f}% of pre-base)")
            
            # Store details
            results["details"] = {
                "base_length_weeks": float(base_length_weeks),
                "base_depth_pct": float(base_depth_pct),
                "base_volatility": float(base_volatility),
                "avg_volatility": float(avg_volatility),
                "avg_close_position_pct": float(avg_close_position),
                "volume_contraction": float(base_volume / pre_base_volume) if pre_base_volume > 0 else 1.0,
                "base_high": float(base_data['High'].max()),
                "base_low": float(base_data['Low'].min())
            }
            
        except Exception as e:
            logger.error(f"Error checking base quality: {e}", exc_info=True)
            results["passed"] = False
            results["failures"].append(f"Error: {str(e)}")
        
        return results
    
    def _identify_base(self, data: pd.DataFrame) -> Optional[Dict]:
        """
        Identify the most recent base pattern in the data
        
        A base is a consolidation period (3-8 weeks) where price moves sideways
        after an advance. This is a natural price pattern - you cannot "add" it.
        
        Returns:
            Dictionary with base information or None
        """
        try:
            # Look for consolidation periods (sideways movement)
            # A base typically follows an advance and shows 3-8 weeks of consolidation
            
            # Method 1: Look for low volatility periods (improved method)
            window = VOLATILITY_WINDOW  # ~2 weeks
            data = data.copy()  # Avoid SettingWithCopyWarning
            data['volatility'] = data['Close'].pct_change(fill_method=None).rolling(window=window).std()
            
            # Find periods with low volatility (potential bases)
            avg_volatility = data['volatility'].mean()
            low_vol_threshold = avg_volatility * LOW_VOL_THRESHOLD_MULTIPLIER
            low_vol_periods = data[data['volatility'] < low_vol_threshold]
            
            # IMPROVED: Check for advance before base (key Minervini rule)
            # A base should follow an advance - price should have been higher before
            if len(data) >= 40:
                price_40d_ago = data['Close'].iloc[-40] if len(data) >= 40 else data['Close'].iloc[0]
                current_price = data['Close'].iloc[-1]
                # Base should follow an advance (price was higher before, or at least not much lower)
                # Allow up to 5% decline (normal consolidation), reject if >10% decline
                if current_price < price_40d_ago * 0.90:  # Price declined >10% = likely a decline, not a base
                    # This might be a decline, not a base after advance
                    pass  # Continue checking, but this is less likely to be a valid base
            
            # Use percentage-based approach as PRIMARY method
            if len(data) >= 20:
                recent_data = data.tail(20)
                recent_low_vol = recent_data[recent_data['volatility'] < low_vol_threshold]
                low_vol_percentage = len(recent_low_vol) / len(recent_data) if len(recent_data) > 0 else 0
                
                if low_vol_percentage >= LOW_VOL_PERCENTAGE_THRESHOLD and len(recent_data) >= LOW_VOL_MIN_DAYS_FOR_PCT:
                    # Use recent data as base
                    base_data = recent_data
                    base_high = base_data['High'].max()
                    base_low = base_data['Low'].min()
                    base_depth_pct = ((base_high - base_low) / base_high) * 100
                    base_length_weeks = len(base_data) / 5.0
                    
                    # Only return if it looks like a valid base
                    if BASE_LENGTH_MIN_WEEKS_IDENTIFY <= base_length_weeks <= BASE_LENGTH_MAX_WEEKS_IDENTIFY and base_depth_pct <= BASE_DEPTH_MAX_PCT_IDENTIFY:
                        return {
                            "data": base_data,
                            "length_weeks": base_length_weeks,
                            "depth_pct": base_depth_pct,
                            "start_date": base_data.index[0],
                            "end_date": base_data.index[-1]
                        }
            
            # Fallback Method: Look for recent consolidation using price range
            # Check last 30-60 days for sideways movement
            if len(data) >= 30:
                # Look at last 30-60 days
                recent_30d = data.tail(30)
                recent_60d = data.tail(min(60, len(data)))
                
                # Calculate price range
                range_30d = ((recent_30d['High'].max() - recent_30d['Low'].min()) / 
                            recent_30d['Close'].mean()) * 100
                range_60d = ((recent_60d['High'].max() - recent_60d['Low'].min()) / 
                            recent_60d['Close'].mean()) * 100
                
                # If recent range is relatively small (consolidation), use it as base
                if range_30d <= RANGE_30D_THRESHOLD_PCT or (range_60d <= RANGE_60D_THRESHOLD_PCT and len(data) >= 40):
                    base_data = recent_30d if range_30d <= RANGE_30D_THRESHOLD_PCT else recent_60d
                    base_high = base_data['High'].max()
                    base_low = base_data['Low'].min()
                    base_depth_pct = ((base_high - base_low) / base_high) * 100
                    base_length_weeks = len(base_data) / 5.0
                    
                    # Only return if reasonable
                    if BASE_LENGTH_MIN_WEEKS_IDENTIFY <= base_length_weeks <= BASE_LENGTH_MAX_WEEKS_IDENTIFY and base_depth_pct <= BASE_DEPTH_MAX_PCT_IDENTIFY:
                        return {
                            "data": base_data,
                            "length_weeks": base_length_weeks,
                            "depth_pct": base_depth_pct,
                            "start_date": base_data.index[0],
                            "end_date": base_data.index[-1]
                        }
            
            # No clear base pattern found
            return None
            
        except Exception as e:
            logger.debug(f"Error identifying base: {e}")
            return None
    
    def _check_relative_strength(self, ticker: str, hist: pd.DataFrame, base_info: Optional[Dict] = None, benchmark: Optional[str] = None) -> Dict:
        """
        PART 3: Relative Strength (CRITICAL)
        
        Checks:
        - RS line near or at new highs
        - Stock outperforms index (DAX / STOXX / FTSE)
        - RSI(14) > 60 before breakout
        """
        bench = benchmark if benchmark is not None else self.benchmark
        results = {
            "passed": True,
            "failures": [],
            "details": {}
        }
        
        try:
            # Calculate RSI
            rsi = self._calculate_rsi(hist['Close'], period=RSI_PERIOD)
            current_rsi = rsi.iloc[-1] if not rsi.empty else 0
            
            # Check RSI at base start if base exists (Minervini says "before breakout")
            rsi_to_check = current_rsi
            if base_info and "start_date" in base_info:
                base_start = base_info["start_date"]
                if base_start in rsi.index:
                    rsi_to_check = rsi.loc[base_start]
                elif base_start in hist.index:
                    # Calculate RSI at base start if not in series
                    base_start_idx = hist.index.get_loc(base_start) if base_start in hist.index else len(hist) - 1
                    if base_start_idx < len(rsi):
                        rsi_to_check = rsi.iloc[base_start_idx]
            
            if rsi_to_check < RSI_MIN_THRESHOLD:
                results["passed"] = False
                if base_info:
                    results["failures"].append(f"RSI({RSI_PERIOD}) at base start = {rsi_to_check:.1f} (need >{RSI_MIN_THRESHOLD})")
                else:
                    results["failures"].append(f"RSI({RSI_PERIOD}) = {rsi_to_check:.1f} (need >{RSI_MIN_THRESHOLD})")
            
            # Calculate relative strength vs benchmark
            rs_data = self.data_provider.calculate_relative_strength(ticker, bench, period=252)
            
            if not rs_data or "error" in rs_data:
                # Try to calculate manually
                benchmark_hist = self.data_provider.get_historical_data(bench, period="1y", interval="1d")
                if not benchmark_hist.empty:
                    # Calculate RS manually
                    stock_returns = hist['Close'].pct_change(fill_method=None).dropna()
                    bench_returns = benchmark_hist['Close'].pct_change(fill_method=None).dropna()
                    
                    # Align dates
                    common_dates = stock_returns.index.intersection(bench_returns.index)
                    if len(common_dates) >= RS_LOOKBACK_DAYS:
                        stock_period = stock_returns.loc[common_dates[-RS_LOOKBACK_DAYS:]]
                        bench_period = bench_returns.loc[common_dates[-RS_LOOKBACK_DAYS:]]
                        
                        stock_cumulative = (1 + stock_period).prod() - 1
                        bench_cumulative = (1 + bench_period).prod() - 1
                        
                        relative_strength = stock_cumulative - bench_cumulative
                        rs_rating = min(100, max(0, 50 + (relative_strength * 100)))
                        
                        rs_data = {
                            "relative_strength": float(relative_strength),
                            "rs_rating": float(rs_rating),
                            "stock_return": float(stock_cumulative),
                            "benchmark_return": float(bench_cumulative)
                        }
                    else:
                        results["passed"] = False
                        results["failures"].append("Insufficient data for relative strength calculation")
                        return results
                else:
                    results["passed"] = False
                    results["failures"].append("Cannot fetch benchmark data for relative strength")
                    return results
            
            # Check if stock outperforms benchmark
            if rs_data.get("relative_strength", 0) <= 0:
                results["passed"] = False
                results["failures"].append("Stock not outperforming benchmark")
            
            # Check if RS line is near new highs
            # Calculate RS line (price / benchmark price)
            benchmark_hist = self.data_provider.get_historical_data(bench, period="1y", interval="1d")
            if not benchmark_hist.empty:
                # Align dates
                common_dates = hist.index.intersection(benchmark_hist.index)
                if len(common_dates) >= RS_LOOKBACK_DAYS:
                    aligned_stock = hist.loc[common_dates]['Close']
                    aligned_bench = benchmark_hist.loc[common_dates]['Close']
                    
                    rs_line = aligned_stock / aligned_bench
                    rs_line_normalized = (rs_line / rs_line.iloc[0]) * 100  # Normalize to start at 100
                    
                    current_rs = rs_line_normalized.iloc[-1]
                    rs_high = rs_line_normalized.tail(RS_LOOKBACK_DAYS).max()
                    rs_from_high_pct = ((rs_high - current_rs) / rs_high) * 100
                    
                    # Check if RS line is trending up, not just absolute value
                    rs_trend_lookback = RS_TREND_LOOKBACK_DAYS if len(rs_line_normalized) >= RS_TREND_LOOKBACK_DAYS else len(rs_line_normalized) - 1
                    rs_trend_ago = rs_line_normalized.iloc[-rs_trend_lookback] if rs_trend_lookback > 0 else rs_line_normalized.iloc[0]
                    rs_trending_up = current_rs > rs_trend_ago
                    
                    # Optionally relax RS line failure when stock is strong (outperforming + RSI >= threshold)
                    relax_rs = RS_RELAX_LINE_DECLINE_IF_STRONG and rs_data.get("relative_strength", 0) > 0 and rsi_to_check >= RSI_MIN_THRESHOLD
                    if rs_from_high_pct > RS_LINE_DECLINE_WARNING_PCT and not relax_rs:
                        if not rs_trending_up and rs_from_high_pct > RS_LINE_DECLINE_FAIL_PCT:
                            results["failures"].append(f"RS line declining ({rs_from_high_pct:.1f}% below recent high)")
                        else:
                            results["failures"].append(f"RS line {rs_from_high_pct:.1f}% below recent high")
                        results["passed"] = False  # Hard failure: RS line decline affects grade
            
            # Store details
            results["details"] = {
                "rsi_14": float(current_rsi),
                "relative_strength": rs_data.get("relative_strength", 0),
                "rs_rating": rs_data.get("rs_rating", 0),
                "stock_return": rs_data.get("stock_return", 0),
                "benchmark_return": rs_data.get("benchmark_return", 0),
                "outperforming": rs_data.get("relative_strength", 0) > 0
            }
            
        except Exception as e:
            logger.error(f"Error checking relative strength: {e}", exc_info=True)
            results["passed"] = False
            results["failures"].append(f"Error: {str(e)}")
        
        return results
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI (Relative Strength Index)"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_atr(self, hist: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range; returns latest ATR value or None."""
        if len(hist) < period + 1:
            return None
        high = hist['High']
        low = hist['Low']
        close = hist['Close']
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None
    
    def _check_volume_signature(self, hist: pd.DataFrame, base_info: Optional[Dict] = None) -> Dict:
        """
        PART 4: Volume Signature
        
        Checks:
        - Dry volume in base
        - Breakout volume +40% or more
        - No heavy sell volume before breakout
        """
        results = {
            "passed": True,
            "failures": [],
            "details": {}
        }
        
        try:
            # Use provided base_info if available, otherwise identify it
            if base_info is None:
                lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
                recent_data = hist.tail(lookback_days)
                base_info = self._identify_base(recent_data)
            
            if not base_info:
                results["passed"] = False
                results["failures"].append("Cannot check volume signature without base")
                return results
            
            base_data = base_info["data"]
            
            # Calculate lookback_days if not already set (when base_info is provided)
            if 'lookback_days' not in locals():
                if base_info and "start_date" in base_info:
                    # Estimate lookback from base start
                    base_start = base_info["start_date"]
                    if base_start in hist.index:
                        base_start_idx = hist.index.get_loc(base_start)
                        lookback_days = len(hist) - base_start_idx + AVG_VOLUME_LOOKBACK_DAYS  # Add buffer
                    else:
                        lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
                else:
                    lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
            
            # Check for dry volume in base
            base_avg_volume = base_data['Volume'].mean()
            pre_base_volume = hist.iloc[-(lookback_days + AVG_VOLUME_LOOKBACK_DAYS):-lookback_days]['Volume'].mean() if len(hist) > (lookback_days + AVG_VOLUME_LOOKBACK_DAYS) else base_avg_volume
            
            volume_contraction = base_avg_volume / pre_base_volume if pre_base_volume > 0 else 1.0
            
            if volume_contraction > VOLUME_CONTRACTION_WARNING:
                results["failures"].append(f"Volume not dry in base (contraction: {volume_contraction:.2f}x)")
            
            # Check for breakout volume
            recent_days = hist.tail(RECENT_DAYS_FOR_VOLUME)
            recent_volume = recent_days['Volume'].mean()
            
            # Check if we're in a breakout (price breaking above base high)
            base_high = base_data['High'].max()
            current_price = hist['Close'].iloc[-1]
            
            if current_price > base_high * (1 + BUY_PRICE_BUFFER_PCT / 100):  # % above base high = breakout
                # Check if volume is above threshold
                avg_volume = hist.tail(AVG_VOLUME_LOOKBACK_DAYS)['Volume'].mean()
                volume_increase = recent_volume / avg_volume if avg_volume > 0 else 0
                
                if volume_increase < BREAKOUT_VOLUME_MULTIPLIER:
                    results["passed"] = False
                    results["failures"].append(f"Breakout volume only {volume_increase:.2f}x (need ≥{BREAKOUT_VOLUME_MULTIPLIER}x)")
            else:
                # Not in breakout yet, just check for heavy sell volume
                down_days = recent_days[recent_days['Close'] < recent_days['Open']]
                if len(down_days) > 0:
                    down_volume = down_days['Volume'].mean()
                    if down_volume > base_avg_volume * HEAVY_SELL_VOLUME_MULTIPLIER:
                        results["failures"].append("Heavy sell volume detected before breakout")
            
            # Store details
            results["details"] = {
                "base_avg_volume": float(base_avg_volume),
                "pre_base_volume": float(pre_base_volume),
                "volume_contraction": float(volume_contraction),
                "recent_volume": float(recent_volume),
                "avg_volume_20d": float(hist.tail(20)['Volume'].mean()),
                "volume_increase": float(recent_volume / hist.tail(20)['Volume'].mean()) if hist.tail(20)['Volume'].mean() > 0 else 0,
                "in_breakout": current_price > base_high * 1.02
            }
            
        except Exception as e:
            logger.error(f"Error checking volume signature: {e}", exc_info=True)
            results["passed"] = False
            results["failures"].append(f"Error: {str(e)}")
        
        return results
    
    def _check_breakout_rules(self, hist: pd.DataFrame, base_info: Optional[Dict] = None) -> Dict:
        """
        PART 5: Breakout Day Rules
        
        Checks:
        - Clears pivot decisively
        - Closes in top 25% of range
        - Volume expansion present
        - Market NOT in correction (we'll skip this as it requires market data)
        """
        results = {
            "passed": True,
            "failures": [],
            "details": {}
        }
        
        try:
            # Use provided base_info if available, otherwise identify it
            if base_info is None:
                lookback_days = min(BASE_LOOKBACK_DAYS, len(hist))
                recent_data = hist.tail(lookback_days)
                base_info = self._identify_base(recent_data)
            
            if not base_info:
                results["passed"] = False
                results["failures"].append("Cannot check breakout rules without base")
                return results
            
            base_high = base_info["data"]['High'].max()
            current_price = hist['Close'].iloc[-1]
            pivot_clearance = base_high * (1 + PIVOT_CLEARANCE_PCT / 100)
            
            # For reporting: last date price closed >= pivot (within longer lookback)
            report_lookback = min(BREAKOUT_LOOKBACK_DAYS_FOR_REPORT, len(hist))
            report_days = hist.tail(report_lookback)
            last_above_pivot_date = None
            days_since_breakout = None
            for i in range(len(report_days) - 1, -1, -1):
                if report_days['Close'].iloc[i] >= pivot_clearance:
                    last_ts = report_days.index[i]
                    last_above_pivot_date = last_ts.date() if hasattr(last_ts, 'date') else str(last_ts)[:10]
                    now_ts = hist.index[-1]
                    days_since_breakout = (now_ts - last_ts).days if hasattr(now_ts - last_ts, 'days') else None
                    break
            
            # Check last N days for breakout conditions (not just current day)
            recent_days = hist.tail(BREAKOUT_LOOKBACK_DAYS)
            cleared_pivot = False
            breakout_day_idx = None
            breakout_day = None
            
            # Check if any day in last N days cleared pivot
            for i in range(len(recent_days)):
                day_price = recent_days['Close'].iloc[i]
                if day_price >= pivot_clearance:
                    cleared_pivot = True
                    breakout_day_idx = i
                    breakout_day = recent_days.iloc[i]
                    break
            
            if not cleared_pivot:
                results["passed"] = False
                results["failures"].append(f"Price not clearing pivot decisively (need ≥{PIVOT_CLEARANCE_PCT}% above base high in last {BREAKOUT_LOOKBACK_DAYS} days)")
                # Store details even if no breakout
                results["details"] = {
                    "pivot_price": float(base_high),
                    "current_price": float(current_price),
                    "clears_pivot": False,
                    "close_position_pct": 0,
                    "volume_ratio": 0,
                    "in_breakout": False,
                    "last_above_pivot_date": last_above_pivot_date,
                    "days_since_breakout": days_since_breakout,
                }
                return results
            
            # Check breakout day specifically
            breakout_price = breakout_day['Close']
            breakout_high = breakout_day['High']
            breakout_low = breakout_day['Low']
            breakout_volume = breakout_day['Volume']
            
            # Check close position on breakout day (hard failure: affects grade)
            daily_range = breakout_high - breakout_low
            close_position = 0
            if daily_range > 0:
                close_position = ((breakout_price - breakout_low) / daily_range) * 100
                if close_position < CLOSE_POSITION_MIN_PCT_BREAKOUT:
                    results["failures"].append(f"Close not in top {100-CLOSE_POSITION_MIN_PCT_BREAKOUT}% of range on breakout day (at {close_position:.1f}%)")
                    results["passed"] = False
            else:
                results["failures"].append("Zero daily range on breakout day")
                results["passed"] = False
            
            # Check volume: on breakout day and optionally on next N days (configurable)
            avg_volume = hist.tail(AVG_VOLUME_LOOKBACK_DAYS)['Volume'].mean()
            volume_ratio = breakout_volume / avg_volume if avg_volume > 0 else 0
            volume_ok = volume_ratio >= VOLUME_EXPANSION_MIN
            if not volume_ok and USE_MULTI_DAY_VOLUME_CONFIRMATION and VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT > 0:
                # Allow volume confirmation on breakout day or in the next N days
                end_idx = min(breakout_day_idx + 1 + VOLUME_CONFIRMATION_DAYS_AFTER_BREAKOUT, len(recent_days))
                for j in range(breakout_day_idx, end_idx):
                    day_vol = recent_days['Volume'].iloc[j]
                    if avg_volume > 0 and (day_vol / avg_volume) >= VOLUME_EXPANSION_MIN:
                        volume_ok = True
                        volume_ratio = day_vol / avg_volume
                        break
            if not volume_ok:
                results["passed"] = False
                results["failures"].append(f"Volume expansion insufficient ({volume_ratio:.2f}x, need ≥{VOLUME_EXPANSION_MIN}x)")
            
            # Store details
            results["details"] = {
                "pivot_price": float(base_high),
                "current_price": float(current_price),
                "breakout_day_price": float(breakout_price),
                "clears_pivot": True,
                "close_position_pct": float(close_position),
                "volume_ratio": float(volume_ratio),
                "in_breakout": True,
                "last_above_pivot_date": last_above_pivot_date,
                "days_since_breakout": days_since_breakout,
            }
            
        except Exception as e:
            logger.error(f"Error checking breakout rules: {e}", exc_info=True)
            results["passed"] = False
            results["failures"].append(f"Error: {str(e)}")
        
        return results
    
    def _calculate_grade(self, checklist: Dict) -> Dict:
        """
        Calculate overall grade based on checklist
        
        A+ Verdict Rule:
        - All boxes checked → Full position
        - 1–2 minor flaws → Half position
        - More than 2 → WALK AWAY
        """
        # Count failures
        total_failures = 0
        critical_failures = 0
        
        # Trend & Structure is NON-NEGOTIABLE
        if not checklist["trend_structure"]["passed"]:
            critical_failures += len(checklist["trend_structure"]["failures"])
        
        # Count other failures
        for category, result in checklist.items():
            if category != "trend_structure":
                if not result["passed"]:
                    total_failures += len(result["failures"])
        
        # Calculate grade
        if critical_failures > 0:
            grade = CRITICAL_FAILURE_GRADE
            meets_criteria = False
            position_size = "None"
        elif total_failures == 0:
            grade = "A+"
            meets_criteria = True
            position_size = "Full"
        elif total_failures <= MAX_FAILURES_FOR_A:
            grade = "A"
            meets_criteria = True
            position_size = "Half"
        elif total_failures <= MAX_FAILURES_FOR_B:
            grade = "B"
            meets_criteria = False
            position_size = "Half"
        else:
            grade = "C"
            meets_criteria = False
            position_size = "None"
        
        # Calculate price metrics for detailed analysis
        price_from_52w_high_pct = 0
        price_from_52w_low_pct = 0
        
        if "trend_structure" in checklist and "details" in checklist["trend_structure"]:
            details = checklist["trend_structure"]["details"]
            price_from_52w_high_pct = details.get("price_from_52w_high_pct", 0)
            price_from_52w_low_pct = details.get("price_from_52w_low_pct", 0)
        
        return {
            "grade": grade,
            "meets_criteria": meets_criteria,
            "position_size": position_size,
            "total_failures": total_failures + critical_failures,
            "critical_failures": critical_failures,
            "price_from_52w_high_pct": price_from_52w_high_pct,
            "price_from_52w_low_pct": price_from_52w_low_pct
        }
    
    def _calculate_buy_sell_prices(self, hist: pd.DataFrame, base_info: Optional[Dict], checklist: Dict) -> Dict:
        """
        Calculate buy and sell prices based on Minervini methodology
        
        Buy Price: Pivot point (base high) - this is the entry point
        Stop Loss: 5% below buy price (max loss; 2:1 R/R with 10% target)
        Profit Target 1: 10% above buy price (take partial profits)
        Profit Target 2: 40-50% above buy price (let winners run, trail stop)
        
        Returns:
            Dictionary with buy_price, stop_loss, profit_target_1, profit_target_2
        """
        current_price = float(hist['Close'].iloc[-1])
        buy_price = current_price
        pivot_price = None
        stop_loss = None
        profit_target_1 = None
        profit_target_2 = None
        risk_reward_ratio = None
        
        try:
            # Get pivot price (base high) if base exists
            if base_info and "data" in base_info:
                pivot_price = float(base_info["data"]['High'].max())
                
                # Buy price is the pivot point (base high) - this is Minervini's entry point
                # If already above pivot, use pivot price (ideal entry) or current if significantly above
                if current_price >= pivot_price * (1 + BUY_PRICE_BUFFER_PCT / 100):
                    # Already in breakout - buy at pivot (ideal) or slightly below current
                    buy_price = pivot_price  # Always use pivot as buy price
                else:
                    # Not yet in breakout - buy at pivot point when it breaks out
                    buy_price = pivot_price
            
            # Calculate stop loss: below buy price (Minervini's rule)
            stop_loss = buy_price * (1 - STOP_LOSS_PCT / 100)
            
            # Optional ATR-based stop (for reporting / volatile names)
            stop_loss_atr = None
            atr_value = None
            if USE_ATR_STOP:
                atr_value = self._calculate_atr(hist, period=ATR_PERIOD)
                if atr_value is not None:
                    stop_loss_atr = float(buy_price - atr_value * ATR_STOP_MULTIPLIER)
            
            # Profit Target 1: above buy price (take partial profits)
            profit_target_1 = buy_price * (1 + PROFIT_TARGET_1_PCT / 100)
            
            # Profit Target 2: above buy price (let winners run, then trail stop)
            profit_target_2 = buy_price * (1 + PROFIT_TARGET_2_PCT / 100)
            
            # Calculate risk/reward ratio
            risk = buy_price - stop_loss
            reward = profit_target_1 - buy_price
            if risk > 0:
                risk_reward_ratio = reward / risk
            
            # Calculate distance from current price to buy price
            distance_to_buy_pct = ((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0
            
            # Base recency: days since base end (for reporting / optional filter)
            days_since_base_end = None
            if base_info and "end_date" in base_info:
                end_ts = base_info["end_date"]
                now_ts = hist.index[-1]
                try:
                    days_since_base_end = (now_ts - end_ts).days if hasattr(now_ts - end_ts, 'days') else None
                except Exception:
                    days_since_base_end = None
            
            out = {
                "pivot_price": pivot_price,
                "buy_price": float(buy_price),
                "current_price": float(current_price),
                "distance_to_buy_pct": float(distance_to_buy_pct),
                "stop_loss": float(stop_loss),
                "stop_loss_pct": float(STOP_LOSS_PCT),
                "profit_target_1": float(profit_target_1),
                "profit_target_1_pct": float(PROFIT_TARGET_1_PCT),
                "profit_target_2": float(profit_target_2),
                "profit_target_2_pct": float(PROFIT_TARGET_2_PCT),
                "risk_reward_ratio": float(risk_reward_ratio) if risk_reward_ratio else None,
                "risk_per_share": float(buy_price - stop_loss),
                "potential_profit_1": float(profit_target_1 - buy_price),
                "potential_profit_2": float(profit_target_2 - buy_price),
                "in_breakout": current_price >= buy_price * (1 + BUY_PRICE_BUFFER_PCT / 100) if pivot_price else False,
                "days_since_base_end": days_since_base_end,
            }
            if USE_ATR_STOP and stop_loss_atr is not None:
                out["stop_loss_atr"] = stop_loss_atr
                out["atr_value"] = atr_value
            return out
            
        except Exception as e:
            logger.error(f"Error calculating buy/sell prices: {e}", exc_info=True)
            return {
                "pivot_price": None,
                "buy_price": float(current_price),
                "current_price": float(current_price),
                "distance_to_buy_pct": 0,
                "stop_loss": None,
                "error": str(e)
            }
    
    def scan_multiple(self, tickers: List[str]) -> List[Dict]:
        """
        Scan multiple stocks
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            List of scan results, sorted by grade (A+ first)
        """
        results = []
        for ticker in tickers:
            result = self.scan_stock(ticker)
            results.append(result)
        
        # Sort by grade (A+ > A > B > C > F)
        grade_order = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}
        results.sort(key=lambda x: (grade_order.get(x.get("overall_grade", "F"), 4), 
                                    -x.get("detailed_analysis", {}).get("price_from_52w_high_pct", 100)))
        
        return results
    
    def get_market_regime(self, benchmark: Optional[str] = None) -> Dict:
        """
        Check if market (benchmark) is above 200 SMA (optional filter for report).
        Returns {"above_200sma": bool, "benchmark": str, "error": str or None}.
        """
        bench = benchmark or self.benchmark
        try:
            hist = self.data_provider.get_historical_data(bench, period="1y", interval="1d")
            if hist.empty or len(hist) < SMA_200_PERIOD:
                return {"above_200sma": None, "benchmark": bench, "error": "Insufficient data"}
            sma_200 = hist['Close'].rolling(window=SMA_200_PERIOD).mean().iloc[-1]
            current = hist['Close'].iloc[-1]
            return {"above_200sma": bool(current > sma_200), "benchmark": bench, "error": None}
        except Exception as e:
            return {"above_200sma": None, "benchmark": bench, "error": str(e)}

