"""
Data Provider Module
Fetches stock data from multiple sources with automatic fallback:
1. Yahoo Finance (yfinance) - Free, no API key needed, good US coverage
2. Alpha Vantage API - Requires API key, good for international stocks
3. Trading 212 - Final fallback for position data
"""
import pandas as pd
import requests
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from ticker_utils import clean_ticker
import logging

# Try to import yfinance (Yahoo Finance)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    try:
        from yfinance.exceptions import YFRateLimitError
    except ImportError:
        YFRateLimitError = None  # Older yfinance may not have it
except ImportError:
    YFINANCE_AVAILABLE = False
    YFRateLimitError = None

logging.getLogger('urllib3').setLevel(logging.ERROR)  # Suppress HTTP warnings

logger = logging.getLogger(__name__)

# Yahoo Finance rate-limit retry: wait times in seconds (exponential backoff)
YF_RATE_LIMIT_WAIT_SECONDS = [60, 120, 180]
YF_RATE_LIMIT_MAX_RETRIES = len(YF_RATE_LIMIT_WAIT_SECONDS)


def _is_yf_rate_limit_error(exc: Exception) -> bool:
    """True if the exception is Yahoo Finance rate limiting."""
    if YFRateLimitError is not None and isinstance(exc, YFRateLimitError):
        return True
    return "rate limit" in str(exc).lower() or "too many requests" in str(exc).lower()


class StockDataProvider:
    """
    Provides stock data from multiple sources with automatic fallback:
    1. Yahoo Finance (yfinance) - Free, no API key, good US coverage (PRIMARY)
    2. Alpha Vantage - Requires API key, good for international stocks (FALLBACK)
    3. Trading 212 - Final fallback for position data
    """
    
    def __init__(self, alpha_vantage_api_key: Optional[str] = None, 
                 trading212_client=None, prefer_yfinance: bool = True):
        """
        Initialize the data provider
        
        Args:
            alpha_vantage_api_key: Alpha Vantage API key (optional, used as fallback)
                                  Get free key at: https://www.alphavantage.co/support/#api-key
                                  Free tier: 25 requests/day, Premium: higher limits
            trading212_client: Optional Trading212Client for fallback data and ticker search
            prefer_yfinance: If True, use Yahoo Finance first (default: True)
        """
        self.alpha_vantage_key = alpha_vantage_api_key
        self.alpha_vantage_base = "https://www.alphavantage.co/query"
        self.trading212_client = trading212_client
        self.prefer_yfinance = prefer_yfinance and YFINANCE_AVAILABLE
        
        if self.prefer_yfinance:
            logger.info("Using Yahoo Finance (yfinance) as primary data source (free, no API key needed)")
    
    def _get_stock_info_alpha_vantage(self, ticker: str) -> Dict:
        """
        Get stock information and fundamentals from Alpha Vantage
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with stock information or empty dict if not found
        """
        if not self.alpha_vantage_key:
            return {}
        
        try:
            ticker_clean = clean_ticker(ticker)
            
            # Get company overview (includes basic info)
            url = self.alpha_vantage_base
            params = {
                "function": "OVERVIEW",
                "symbol": ticker_clean,
                "apikey": self.alpha_vantage_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                overview = response.json()
                
                # Check for API errors
                if "Error Message" in overview or "Note" in overview:
                    return {}
                
                # Get income statement for growth metrics
                income_params = {
                    "function": "INCOME_STATEMENT",
                    "symbol": ticker_clean,
                    "apikey": self.alpha_vantage_key
                }
                
                income_response = requests.get(url, params=income_params, timeout=30)
                income_data = {}
                income_reports = []
                if income_response.status_code == 200:
                    income_json = income_response.json()
                    if "annualReports" in income_json and income_json["annualReports"]:
                        income_reports = income_json["annualReports"]
                        income_data = income_reports[0] if income_reports else {}
                
                # Get balance sheet for debt metrics
                balance_params = {
                    "function": "BALANCE_SHEET",
                    "symbol": ticker_clean,
                    "apikey": self.alpha_vantage_key
                }
                
                balance_response = requests.get(url, params=balance_params, timeout=30)
                balance_data = {}
                if balance_response.status_code == 200:
                    balance_json = balance_response.json()
                    if "annualReports" in balance_json and balance_json["annualReports"]:
                        balance_data = balance_json["annualReports"][0]
                
                # Calculate growth rates if we have multiple years
                revenue_growth = 0
                earnings_growth = 0
                if len(income_reports) >= 2:
                    current_revenue = float(income_reports[0].get("totalRevenue", 0) or 0)
                    previous_revenue = float(income_reports[1].get("totalRevenue", 0) or 0)
                    if previous_revenue > 0:
                        revenue_growth = ((current_revenue - previous_revenue) / previous_revenue) * 100
                    
                    current_net_income = float(income_reports[0].get("netIncome", 0) or 0)
                    previous_net_income = float(income_reports[1].get("netIncome", 0) or 0)
                    if previous_net_income > 0:
                        earnings_growth = ((current_net_income - previous_net_income) / previous_net_income) * 100
                
                # Calculate profit margin
                profit_margins = 0
                if income_data.get("totalRevenue") and float(income_data.get("totalRevenue", 0) or 0) > 0:
                    net_income = float(income_data.get("netIncome", 0) or 0)
                    total_revenue = float(income_data.get("totalRevenue", 0) or 0)
                    profit_margins = (net_income / total_revenue) * 100
                
                # Calculate ROE
                return_on_equity = 0
                if balance_data.get("totalShareholderEquity") and float(balance_data.get("totalShareholderEquity", 0) or 0) > 0:
                    net_income = float(income_data.get("netIncome", 0) or 0)
                    equity = float(balance_data.get("totalShareholderEquity", 0) or 0)
                    return_on_equity = (net_income / equity) * 100
                
                # Calculate debt to equity
                debt_to_equity = 0
                if balance_data.get("totalShareholderEquity") and float(balance_data.get("totalShareholderEquity", 0) or 0) > 0:
                    total_debt = float(balance_data.get("totalLiabilities", 0) or 0)
                    equity = float(balance_data.get("totalShareholderEquity", 0) or 0)
                    debt_to_equity = total_debt / equity if equity > 0 else 0
                
                return {
                    "ticker": overview.get("Symbol", ticker_clean),
                    "company_name": overview.get("Name", ""),
                    "sector": overview.get("Sector", ""),
                    "industry": overview.get("Industry", ""),
                    "market_cap": float(overview.get("MarketCapitalization", 0) or 0),
                    "current_price": float(overview.get("52WeekHigh", 0) or 0),  # Use 52W high as proxy
                    "earnings_growth": earnings_growth,
                    "revenue_growth": revenue_growth,
                    "profit_margins": profit_margins,
                    "return_on_equity": return_on_equity,
                    "debt_to_equity": debt_to_equity,
                    "trailing_pe": float(overview.get("PERatio", 0) or 0),
                    "forward_pe": float(overview.get("ForwardPE", 0) or 0),
                    "dividend_yield": float(overview.get("DividendYield", 0) or 0) * 100,  # Convert to percentage
                    "beta": float(overview.get("Beta", 1.0) or 1.0),
                    "52_week_high": float(overview.get("52WeekHigh", 0) or 0),
                    "52_week_low": float(overview.get("52WeekLow", 0) or 0),
                    "source": "alpha_vantage"
                }
            
            return {}
        except Exception as e:
            logger.debug(f"Alpha Vantage stock info error for {ticker}: {e}")
            return {}
    
    def _get_historical_data_alpha_vantage(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical data from Alpha Vantage
        
        Args:
            ticker: Stock ticker symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1d, 1w, 1m) - Alpha Vantage supports daily, weekly, monthly
            
        Returns:
            DataFrame with OHLCV data or empty DataFrame
        """
        if not self.alpha_vantage_key:
            return pd.DataFrame()
        
        try:
            # Use centralized ticker cleaning utility
            ticker_clean = clean_ticker(ticker)
            
            # Map interval to Alpha Vantage function
            # Alpha Vantage functions: TIME_SERIES_DAILY, TIME_SERIES_WEEKLY, TIME_SERIES_MONTHLY
            if interval in ["1d", "5d"]:
                function = "TIME_SERIES_DAILY"
                outputsize = "full"  # Get full history
            elif interval in ["1wk", "1w", "1mo", "1m", "3mo"]:
                # For weekly/monthly, use appropriate function
                if interval in ["1wk", "1w"]:
                    function = "TIME_SERIES_WEEKLY"
                else:
                    function = "TIME_SERIES_MONTHLY"
                outputsize = "full"
            else:
                function = "TIME_SERIES_DAILY"
                outputsize = "full"
            
            # Build API request
            url = self.alpha_vantage_base
            params = {
                "function": function,
                "symbol": ticker_clean,
                "apikey": self.alpha_vantage_key,
                "outputsize": outputsize,
                "datatype": "json"
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for API errors
                if "Error Message" in data or "Note" in data:
                    return pd.DataFrame()
                
                # Extract time series data (key varies by function)
                time_series_key = None
                for key in data.keys():
                    if "Time Series" in key:
                        time_series_key = key
                        break
                
                if not time_series_key or time_series_key not in data:
                    return pd.DataFrame()
                
                time_series = data[time_series_key]
                
                if not time_series or not isinstance(time_series, dict):
                    return pd.DataFrame()
                
                # Convert to DataFrame
                records = []
                for date_str, values in time_series.items():
                    records.append({
                        'date': pd.to_datetime(date_str),
                        'Open': float(values.get('1. open', 0)),
                        'High': float(values.get('2. high', 0)),
                        'Low': float(values.get('3. low', 0)),
                        'Close': float(values.get('4. close', 0)),
                        'Volume': int(float(values.get('5. volume', 0)))
                    })
                
                if not records:
                    return pd.DataFrame()
                
                df = pd.DataFrame(records)
                df.set_index('date', inplace=True)
                df = df.sort_index()
                
                # Filter by period if needed (Alpha Vantage returns full history)
                if period != "max":
                    if period == "1d":
                        df = df.tail(1)
                    elif period == "5d":
                        df = df.tail(5)
                    elif period == "1mo" or period == "1m":
                        df = df.tail(30)
                    elif period == "3mo":
                        df = df.tail(90)
                    elif period == "6mo":
                        df = df.tail(180)
                    elif period == "1y":
                        df = df.tail(365)
                    elif period == "2y":
                        df = df.tail(730)
                    elif period == "5y":
                        df = df.tail(1825)
                    elif period == "10y":
                        df = df.tail(3650)
                    elif period == "ytd":
                        current_year = datetime.now().year
                        df = df[df.index >= pd.Timestamp(f"{current_year}-01-01")]
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            return pd.DataFrame()
        except Exception as e:
            logger.debug(f"Alpha Vantage API error for {ticker}: {e}")
            return pd.DataFrame()
    
    def _try_ticker_formats(self, possible_tickers: List[str], func, *args, **kwargs):
        """
        Try multiple ticker formats until one works
        
        Args:
            possible_tickers: List of ticker formats to try
            func: Function to call with ticker
            *args, **kwargs: Additional arguments for func
            
        Returns:
            Result from first successful ticker format, or error dict
        """
        for ticker_format in possible_tickers:
            try:
                result = func(ticker_format, *args, **kwargs)
                # Check if result is valid (not empty, no error)
                if isinstance(result, dict):
                    if "error" not in result and result:
                        return result
                elif isinstance(result, pd.DataFrame):
                    if not result.empty:
                        return result
                elif result:  # Other types
                    return result
            except Exception:
                continue
        
        # If all formats failed, return error
        return {"error": f"Ticker not found in any format: {possible_tickers[0]}"} if possible_tickers else {"error": "No ticker provided"}
    
    def _get_stock_info_yfinance(self, ticker: str) -> Dict:
        """
        Get stock information and fundamentals from Yahoo Finance.
        Retries with backoff on rate limit (YFRateLimitError / Too Many Requests).
        """
        if not YFINANCE_AVAILABLE:
            return {}

        ticker_clean = clean_ticker(ticker)
        last_error = None

        for attempt in range(YF_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                stock = yf.Ticker(ticker_clean)
                info = stock.info

                if not info or len(info) < 5:
                    return {}

                return {
                    "ticker": info.get("symbol", ticker_clean),
                    "company_name": info.get("longName") or info.get("shortName", ""),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": info.get("marketCap", 0),
                    "current_price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
                    "earnings_growth": (info.get("earningsQuarterlyGrowth", 0) or 0) * 100,
                    "revenue_growth": (info.get("revenueGrowth", 0) or 0) * 100,
                    "profit_margins": (info.get("profitMargins", 0) or 0) * 100,
                    "return_on_equity": (info.get("returnOnEquity", 0) or 0) * 100,
                    "debt_to_equity": info.get("debtToEquity", 0),
                    "trailing_pe": info.get("trailingPE", 0),
                    "forward_pe": info.get("forwardPE", 0),
                    "dividend_yield": (info.get("dividendYield", 0) or 0) * 100,
                    "beta": info.get("beta", 1.0),
                    "52_week_high": info.get("fiftyTwoWeekHigh", 0),
                    "52_week_low": info.get("fiftyTwoWeekLow", 0),
                    "source": "yfinance"
                }
            except Exception as e:
                last_error = e
                if _is_yf_rate_limit_error(e) and attempt < YF_RATE_LIMIT_MAX_RETRIES:
                    wait = YF_RATE_LIMIT_WAIT_SECONDS[attempt]
                    logger.warning(f"Yahoo Finance rate limited (stock info) for {ticker}. Waiting {wait}s before retry {attempt + 1}/{YF_RATE_LIMIT_MAX_RETRIES}...")
                    time.sleep(wait)
                else:
                    break

        logger.debug(f"Yahoo Finance stock info error for {ticker}: {last_error}")
        return {}
    
    def get_stock_info(self, ticker: str) -> Dict:
        """
        Get stock information and fundamentals from available sources
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with stock information
        """
        # Try Yahoo Finance first if preferred and available
        if self.prefer_yfinance:
            yf_data = self._get_stock_info_yfinance(ticker)
            if yf_data and "error" not in yf_data:
                return yf_data
        
        # Fallback to Alpha Vantage if available
        if self.alpha_vantage_key:
            alpha_vantage_data = self._get_stock_info_alpha_vantage(ticker)
            if alpha_vantage_data and "error" not in alpha_vantage_data:
                return alpha_vantage_data
        
        # If yfinance wasn't tried yet, try it now as last resort
        if not self.prefer_yfinance and YFINANCE_AVAILABLE:
            yf_data = self._get_stock_info_yfinance(ticker)
            if yf_data and "error" not in yf_data:
                return yf_data
        
        # If all failed, return error
        return {
            "ticker": clean_ticker(ticker),
            "error": "Ticker not found or no data sources available"
        }
    
    def _get_historical_data_yfinance(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical data from Yahoo Finance using yfinance.
        Retries with backoff on rate limit (YFRateLimitError / Too Many Requests).
        """
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available - install with: pip install yfinance")
            return pd.DataFrame()

        ticker_clean = clean_ticker(ticker)
        yf_period = period if period in ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"] else "1y"
        yf_interval = interval if interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"] else "1d"
        last_error = None

        for attempt in range(YF_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                logger.debug(f"Fetching historical data from Yahoo Finance for {ticker_clean}" + (f" (attempt {attempt + 1})" if attempt else ""))
                stock = yf.Ticker(ticker_clean)
                hist = stock.history(period=yf_period, interval=yf_interval)

                if hist.empty:
                    logger.warning(f"Yahoo Finance returned empty data for {ticker_clean}")
                    return pd.DataFrame()

                logger.debug(f"Yahoo Finance returned {len(hist)} rows for {ticker_clean}")
                required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                available_cols = [col for col in hist.columns if col in required_cols]
                if len(available_cols) < len(required_cols):
                    logger.warning(f"Missing required columns. Available: {list(hist.columns)}, Required: {required_cols}")
                    return pd.DataFrame()
                return hist[required_cols].copy()

            except Exception as e:
                last_error = e
                if _is_yf_rate_limit_error(e) and attempt < YF_RATE_LIMIT_MAX_RETRIES:
                    wait = YF_RATE_LIMIT_WAIT_SECONDS[attempt]
                    logger.warning(f"Yahoo Finance rate limited for {ticker}. Waiting {wait}s before retry {attempt + 1}/{YF_RATE_LIMIT_MAX_RETRIES}...")
                    time.sleep(wait)
                else:
                    break

        logger.error(f"Yahoo Finance error for {ticker}: {last_error}", exc_info=True)
        return pd.DataFrame()
    
    def get_historical_data(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Get historical price and volume data from available sources (Yahoo Finance or Alpha Vantage)
        
        Args:
            ticker: Stock ticker symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1d, 1w, 1mo) - varies by provider
            
        Returns:
            DataFrame with OHLCV data
        """
        # Try Yahoo Finance first if preferred and available
        if self.prefer_yfinance:
            yf_data = self._get_historical_data_yfinance(ticker, period, interval)
            if not yf_data.empty:
                return yf_data
        
        # Fallback to Alpha Vantage if available
        if self.alpha_vantage_key:
            alpha_vantage_data = self._get_historical_data_alpha_vantage(ticker, period, interval)
            if not alpha_vantage_data.empty:
                return alpha_vantage_data
        
        # If yfinance wasn't tried yet, try it now as last resort
        if not self.prefer_yfinance and YFINANCE_AVAILABLE:
            yf_data = self._get_historical_data_yfinance(ticker, period, interval)
            if not yf_data.empty:
                return yf_data
        
        return pd.DataFrame()
    
    def calculate_moving_averages(self, ticker: str, periods: List[int] = [50, 200]) -> Dict:
        """
        Calculate moving averages for a stock
        
        Args:
            ticker: Stock ticker symbol
            periods: List of periods for moving averages (e.g., [50, 200])
            
        Returns:
            Dictionary with current price and moving average values
        """
        try:
            logger.debug(f"Calculating moving averages for {ticker}")
            hist = self.get_historical_data(ticker, period="1y")
            if hist.empty:
                logger.warning(f"No historical data available for {ticker} - cannot calculate moving averages")
                return {"error": "No historical data available"}
            
            logger.debug(f"Got {len(hist)} rows of historical data for moving average calculation")
            current_price = hist['Close'].iloc[-1]
            result = {"current_price": float(current_price)}
            
            for period in periods:
                if len(hist) >= period:
                    ma = hist['Close'].rolling(window=period).mean().iloc[-1]
                    result[f"ma_{period}"] = float(ma)
                    result[f"above_ma_{period}"] = current_price > ma
                    logger.debug(f"  {period}-day MA: ${ma:.2f}, Current: ${current_price:.2f}, Above: {current_price > ma}")
                else:
                    logger.warning(f"  Not enough data for {period}-day MA (have {len(hist)} rows, need {period})")
                    result[f"ma_{period}"] = None
                    result[f"above_ma_{period}"] = None
            
            return result
        except Exception as e:
            logger.error(f"Error calculating moving averages for {ticker}: {e}", exc_info=True)
            return {"error": str(e)}
    
    def calculate_relative_strength(self, ticker: str, benchmark: str = "^GSPC", period: int = 252) -> Dict:
        """
        Calculate relative strength vs benchmark (default: S&P 500)
        
        Args:
            ticker: Stock ticker symbol
            benchmark: Benchmark ticker (default: ^GSPC for S&P 500)
            period: Number of trading days to compare
            
        Returns:
            Dictionary with relative strength metrics
        """
        try:
            # Try to get data for the stock (will try multiple formats)
            stock_hist = self.get_historical_data(ticker, period="1y")
            benchmark_hist = self.get_historical_data(benchmark, period="1y")
            
            if stock_hist.empty or benchmark_hist.empty:
                return {}
            
            # Calculate returns
            stock_returns = stock_hist['Close'].pct_change().dropna()
            benchmark_returns = benchmark_hist['Close'].pct_change().dropna()
            
            # Align dates
            common_dates = stock_returns.index.intersection(benchmark_returns.index)
            if len(common_dates) < period:
                period = len(common_dates)
            
            stock_period = stock_returns.loc[common_dates[-period:]]
            benchmark_period = benchmark_returns.loc[common_dates[-period:]]
            
            # Calculate cumulative returns
            stock_cumulative = (1 + stock_period).prod() - 1
            benchmark_cumulative = (1 + benchmark_period).prod() - 1
            
            # Relative strength
            relative_strength = stock_cumulative - benchmark_cumulative
            rs_rating = min(100, max(0, 50 + (relative_strength * 100)))  # Scale to 0-100
            
            return {
                "relative_strength": float(relative_strength),
                "rs_rating": float(rs_rating),
                "stock_return": float(stock_cumulative),
                "benchmark_return": float(benchmark_cumulative),
                "period_days": period
            }
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_volume_patterns(self, ticker: str, lookback_days: int = 20) -> Dict:
        """
        Analyze volume patterns
        
        Args:
            ticker: Stock ticker symbol
            lookback_days: Number of days to analyze
            
        Returns:
            Dictionary with volume analysis
        """
        try:
            hist = self.get_historical_data(ticker, period="3mo")
            if hist.empty or len(hist) < lookback_days:
                return {}
            
            recent_volume = hist['Volume'].tail(lookback_days)
            avg_volume = recent_volume.mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            return {
                "current_volume": float(current_volume),
                "average_volume": float(avg_volume),
                "volume_ratio": float(volume_ratio),
                "above_average": volume_ratio > 1.0,
                "high_volume": volume_ratio > 1.5  # 50% above average
            }
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_price_action(self, ticker: str, lookback_days: int = 60) -> Dict:
        """
        Analyze price action for trend identification
        
        Args:
            ticker: Stock ticker symbol
            lookback_days: Number of days to analyze
            
        Returns:
            Dictionary with price action analysis
        """
        try:
            hist = self.get_historical_data(ticker, period="6mo")
            if hist.empty or len(hist) < lookback_days:
                return {}
            
            recent_prices = hist['Close'].tail(lookback_days)
            
            # Identify higher highs and higher lows
            highs = recent_prices.rolling(window=5).max()
            lows = recent_prices.rolling(window=5).min()
            
            # Check for uptrend (higher highs and higher lows)
            recent_highs = highs.tail(20)
            recent_lows = lows.tail(20)
            
            higher_highs = recent_highs.iloc[-1] > recent_highs.iloc[0]
            higher_lows = recent_lows.iloc[-1] > recent_lows.iloc[0]
            
            # Calculate trend strength
            price_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
            
            # Check for consolidation (low volatility)
            volatility = recent_prices.pct_change().std()
            
            return {
                "uptrend": higher_highs and higher_lows,
                "higher_highs": higher_highs,
                "higher_lows": higher_lows,
                "price_change_pct": float(price_change * 100),
                "volatility": float(volatility),
                "trend_strength": "strong" if abs(price_change) > 0.1 else "moderate" if abs(price_change) > 0.05 else "weak"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def detect_breakout(self, ticker: str, consolidation_days: int = 20, breakout_threshold: float = 0.05) -> Dict:
        """
        Detect breakout patterns
        
        Args:
            ticker: Stock ticker symbol
            consolidation_days: Days to look for consolidation
            breakout_threshold: Percentage move to consider a breakout
            
        Returns:
            Dictionary with breakout analysis
        """
        try:
            hist = self.get_historical_data(ticker, period="3mo")
            if hist.empty or len(hist) < consolidation_days + 5:
                return {}
            
            recent = hist.tail(consolidation_days + 5)
            consolidation_period = recent.head(consolidation_days)
            recent_period = recent.tail(5)
            
            # Find consolidation range
            consolidation_high = consolidation_period['High'].max()
            consolidation_low = consolidation_period['Low'].min()
            consolidation_range = (consolidation_high - consolidation_low) / consolidation_low
            
            # Check for breakout
            current_price = recent['Close'].iloc[-1]
            breakout_above = current_price > consolidation_high * (1 + breakout_threshold)
            breakout_below = current_price < consolidation_low * (1 - breakout_threshold)
            
            # Check volume on breakout
            volume_analysis = self.analyze_volume_patterns(ticker)
            high_volume_breakout = breakout_above and volume_analysis.get("high_volume", False)
            
            return {
                "in_consolidation": consolidation_range < 0.1,  # Less than 10% range
                "breakout_above": breakout_above,
                "breakout_below": breakout_below,
                "consolidation_high": float(consolidation_high),
                "consolidation_low": float(consolidation_low),
                "current_price": float(current_price),
                "high_volume_breakout": high_volume_breakout
            }
        except Exception as e:
            return {"error": str(e)}

