"""
Trading 212 Minervini SEPA Scanner
Main interface for scanning stocks according to Mark Minervini's SEPA methodology
"""
import os
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv
from trading212_client import Trading212Client
from data_provider import StockDataProvider
from sepa_checklist import MinerviniScanner
from logger_config import get_logger
from validators import (
    validate_file_path,
    validate_api_key,
    validate_ticker_list,
    mask_credential,
    ValidationError
)
from config import DEFAULT_ENV_PATH

logger = get_logger(__name__)


class TradingBot:
    """Main trading bot interface for Minervini SEPA scanning"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 use_ai: bool = False, skip_trading212: bool = True, benchmark: str = "^GDAXI"):
        """
        Initialize trading bot for Minervini scanning
        
        Args:
            api_key: Trading 212 API key (optional, not needed for scanning)
            api_secret: Trading 212 API secret (optional, not needed for scanning)
            use_ai: Whether to enable AI-powered analysis (not used in current version)
            skip_trading212: Skip Trading 212 API calls (default: True, uses yfinance/Alpha Vantage)
            benchmark: Benchmark index for relative strength (default: ^GDAXI for DAX)
                      Options: ^GDAXI (DAX), ^FCHI (CAC 40), ^AEX (AEX), ^SSMI (Swiss), ^OMX (Nordics)
        """
        # Load environment variables from .env file
        env_file = Path(DEFAULT_ENV_PATH)
        if env_file.exists():
            load_dotenv(env_file)
            logger.debug(f"Loaded environment variables from {env_file}")
        else:
            logger.debug(f"No .env file found at {env_file}, using environment variables only")
        
        # Trading 212 client (optional, only if not skipping)
        self.api_client = None
        if not skip_trading212:
            api_key = api_key or os.getenv("TRADING212_API_KEY")
            api_secret = api_secret or os.getenv("TRADING212_API_SECRET")
            
            if api_key and api_secret:
                try:
                    api_key = validate_api_key(api_key, "Trading 212 API key")
                    api_secret = validate_api_key(api_secret, "Trading 212 API secret")
                    self.api_client = Trading212Client(api_key, api_secret)
                    logger.info(f"Trading 212 client initialized with API key: {mask_credential(api_key)}")
                except ValidationError as e:
                    logger.warning(f"Invalid Trading 212 credentials: {e}. Continuing without Trading 212 API.")
            else:
                logger.info("Trading 212 credentials not provided. Using alternative data sources only.")
        
        # Initialize data provider (uses yfinance as primary, Alpha Vantage as fallback)
        alpha_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        self.data_provider = StockDataProvider(
            alpha_vantage_api_key=alpha_key,
            trading212_client=self.api_client,
            prefer_yfinance=True  # Use Yahoo Finance as primary (free, no API key needed)
        )
        
        if not alpha_key:
            logger.info("ALPHA_VANTAGE_API_KEY not configured. Using Yahoo Finance (yfinance) only.")
            logger.info("  Get a free Alpha Vantage key at: https://www.alphavantage.co/support/#api-key")
            logger.info("  Add it to your .env file: ALPHA_VANTAGE_API_KEY=your_key_here")
        
        # Initialize Minervini scanner
        self.scanner = MinerviniScanner(self.data_provider, benchmark=benchmark)
        self.benchmark = benchmark
        
        logger.info(f"Minervini SEPA Scanner initialized (benchmark: {benchmark})")
    
    def scan_stock(self, ticker: str) -> dict:
        """
        Scan a single stock using Minervini SEPA criteria
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with scan results
        """
        try:
            # Validate ticker
            ticker = validate_ticker_list([ticker])[0]
            
            logger.info(f"Scanning {ticker}...")
            result = self.scanner.scan_stock(ticker)
            
            return result
            
        except ValidationError as e:
            logger.error(f"Invalid ticker: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "meets_criteria": False,
                "overall_grade": "F"
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}", exc_info=True)
            return {
                "ticker": ticker,
                "error": str(e),
                "meets_criteria": False,
                "overall_grade": "F"
            }
    
    def scan_from_file(self, file_path: str) -> dict:
        """
        Scan stocks from a file (one ticker per line)
        
        Args:
            file_path: Path to file containing ticker symbols (one per line)
            
        Returns:
            Dictionary with scan results for all stocks
        """
        try:
            from pathlib import Path
            file_path_obj = Path(file_path)
            
            if not file_path_obj.exists():
                logger.error(f"File not found: {file_path}")
                return {
                    "error": f"File not found: {file_path}",
                    "total_scanned": 0,
                    "results": []
                }
            
            # Read tickers from file
            tickers = []
            with open(file_path_obj, 'r') as f:
                for line in f:
                    ticker = line.strip()
                    # Skip empty lines and comments
                    if ticker and not ticker.startswith('#'):
                        tickers.append(ticker)
            
            if not tickers:
                logger.warning(f"No valid tickers found in file: {file_path}")
                return {
                    "error": "No valid tickers found in file",
                    "total_scanned": 0,
                    "results": []
                }
            
            logger.info(f"Loaded {len(tickers)} tickers from file: {file_path}")
            return self.scan_stocks(tickers)
            
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}", exc_info=True)
            return {
                "error": str(e),
                "total_scanned": 0,
                "results": []
            }
    
    def scan_stocks(self, tickers: List[str]) -> dict:
        """
        Scan multiple stocks using Minervini SEPA criteria
        
        Args:
            tickers: List of ticker symbols to scan
            
        Returns:
            Dictionary with scan results for all stocks
        """
        try:
            # Validate tickers
            tickers = validate_ticker_list(tickers)
            
            logger.info(f"Scanning {len(tickers)} stocks...")
            results = self.scanner.scan_multiple(tickers)
            
            # Count by grade
            grade_counts = {"A+": 0, "A": 0, "B": 0, "C": 0, "F": 0}
            for result in results:
                grade = result.get("overall_grade", "F")
                grade_counts[grade] = grade_counts.get(grade, 0) + 1
            
            return {
                "total_scanned": len(results),
                "grade_counts": grade_counts,
                "results": results
            }
            
        except ValidationError as e:
            logger.error(f"Invalid ticker list: {e}")
            return {
                "error": str(e),
                "total_scanned": 0,
                "results": []
            }
        except Exception as e:
            logger.error(f"Error scanning stocks: {e}", exc_info=True)
            return {
                "error": str(e),
                "total_scanned": 0,
                "results": []
            }
    
    def search_and_scan(self, query: str) -> dict:
        """
        Search for stocks and scan them
        
        Args:
            query: Search query (ticker or company name)
            
        Returns:
            Dictionary with search and scan results
        """
        try:
            if not self.api_client:
                # If no Trading 212 API, treat query as a ticker directly
                logger.info(f"No Trading 212 API - treating '{query}' as a ticker symbol")
                result = self.scan_stock(query)
                return {
                    "query": query,
                    "instruments_found": 1,
                    "results": [result]
                }
            
            # Search for instruments
            instruments = self.api_client.search_instruments(query)
            
            if not instruments:
                return {
                    "query": query,
                    "instruments_found": 0,
                    "results": []
                }
            
            # Extract tickers
            tickers = [inst.get("ticker") for inst in instruments if inst.get("ticker")]
            
            # Scan all found instruments
            scan_results = self.scan_stocks(tickers)
            scan_results["query"] = query
            scan_results["instruments_found"] = len(instruments)
            
            return scan_results
            
        except Exception as e:
            logger.error(f"Error searching and scanning: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query,
                "instruments_found": 0,
                "results": []
            }
