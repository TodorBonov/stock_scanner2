"""
Trading 212 API Client
Handles authentication and API calls to Trading 212
"""
import os
import requests
import base64
import time
from typing import Dict, List, Optional
from datetime import datetime
from ticker_utils import clean_ticker
from logger_config import get_logger
from config import DEFAULT_RATE_LIMIT_DELAY, MAX_API_RETRIES, TRADING212_API_TIMEOUT

logger = get_logger(__name__)


class Trading212Client:
    """Client for interacting with Trading 212 API"""
    
    BASE_URL = "https://live.trading212.com/api/v0"
    
    def __init__(self, api_key: str, api_secret: str, rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY):
        """
        Initialize Trading 212 API client
        
        Args:
            api_key: Your Trading 212 API key
            api_secret: Your Trading 212 API secret
            rate_limit_delay: Delay between API calls in seconds (default: from config)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.rate_limit_delay = rate_limit_delay
        self._auth_header = self._generate_auth_header()
        self._last_request_time = 0
        _disable = os.environ.get("DISABLE_SSL_VERIFY", "").strip().lower() in ("1", "true", "yes")
        self._verify_ssl = not _disable
        logger.debug(f"Trading212Client initialized with rate_limit_delay={rate_limit_delay}")
    
    def _generate_auth_header(self) -> str:
        """Generate Basic Auth header"""
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def _make_request(self, method: str, endpoint: str, max_retries: int = MAX_API_RETRIES, **kwargs) -> Dict:
        """
        Make authenticated API request with rate limiting and retry logic
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            max_retries: Maximum number of retry attempts for rate limit errors
            **kwargs: Additional arguments for requests
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json"
        }
        headers.update(kwargs.pop("headers", {}))
        
        # Rate limiting: ensure minimum delay between requests
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        if time_since_last_request < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last_request)
        
        # Add timeout to kwargs if not already specified
        if 'timeout' not in kwargs:
            kwargs['timeout'] = TRADING212_API_TIMEOUT
        if 'verify' not in kwargs:
            kwargs['verify'] = self._verify_ssl
        
        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, headers=headers, **kwargs)
                self._last_request_time = time.time()
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    if attempt < max_retries - 1:
                        wait_time = retry_after if retry_after > 0 else (2 ** attempt) * 2
                        logger.warning(f"Rate limited. Waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()
                
                # Don't retry on 404 errors - resource doesn't exist
                if response.status_code == 404:
                    response.raise_for_status()
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                # Don't retry on 404 errors
                if hasattr(e, 'response') and e.response and e.response.status_code == 404:
                    logger.debug(f"404 error for {endpoint}: {e}")
                    raise
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff
                    logger.warning(f"HTTP request failed: {e}. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"HTTP request failed after {max_retries} attempts: {e}")
                    raise
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff
                    logger.warning(f"Request timeout: {e}. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request timeout after {max_retries} attempts: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff
                    logger.warning(f"Request failed: {e}. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise
    
    def get_account_cash(self) -> Dict:
        """Get account cash balance"""
        return self._make_request("GET", "/equity/account/cash")
    
    def get_positions(self) -> List[Dict]:
        """Get all open positions"""
        # According to Trading 212 API docs: /api/v0/equity/positions
        return self._make_request("GET", "/equity/positions")
    
    def get_position(self, ticker: str) -> Optional[Dict]:
        """Get specific position by ticker"""
        positions = self.get_positions()
        for position in positions:
            if position.get("ticker") == ticker.upper():
                return position
        return None
    
    def get_instrument_info(self, ticker: str) -> Dict:
        """
        Get instrument information
        
        Note: Trading 212 API does not provide individual instrument metadata endpoints.
        The /equity/metadata/instruments endpoint only returns a list of all instruments.
        This method attempts to search the list, but may return empty dict if not found.
        
        Args:
            ticker: Stock ticker symbol (may include _EQ suffix)
        """
        # Trading 212 API only provides /equity/metadata/instruments as a list endpoint
        # Individual instrument lookup is not directly supported
        # We'll try to get the full list and search it, but this is inefficient
        logger.debug(f"Attempting to get instrument info for {ticker} (note: Trading 212 API limitation)")
        
        try:
            # Get all instruments and search for the ticker
            # This is inefficient but the API doesn't support individual lookups
            instruments = self._make_request("GET", "/equity/metadata/instruments", max_retries=1)
            
            if isinstance(instruments, list):
                ticker_upper = ticker.upper()
                ticker_clean = clean_ticker(ticker)
                
                # Search for exact match
                for instrument in instruments:
                    inst_ticker = instrument.get("ticker", "").upper()
                    if inst_ticker == ticker_upper or inst_ticker == ticker_clean:
                        return instrument
                
                logger.debug(f"Instrument {ticker} not found in metadata list")
                return {}
            else:
                logger.warning("Unexpected response format from /equity/metadata/instruments")
                return {}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"Instrument metadata endpoint returned 404 for {ticker}")
                return {}
            logger.warning(f"Error fetching instrument info for {ticker}: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Unexpected error fetching instrument info for {ticker}: {e}")
            return {}
    
    def get_historical_data(self, ticker: str, period: str = "1Y") -> Dict:
        """
        Get historical price data
        
        WARNING: Trading 212 API does not provide historical price data endpoints.
        The /equity/history/ endpoints are only for:
        - /equity/history/orders - order history
        - /equity/history/dividends - dividend history  
        - /equity/history/transactions - transaction history
        
        This method will always return an empty dict. Use external data sources
        (Yahoo Finance, EODHD, etc.) for historical price data.
        
        Args:
            ticker: Stock ticker symbol
            period: Time period (not used, kept for API compatibility)
        """
        # Trading 212 API does not provide historical price data
        # Historical endpoints are only for orders, dividends, and transactions
        logger.debug(f"Historical price data not available from Trading 212 API for {ticker}. "
                    f"Use external data sources (Yahoo Finance, EODHD) instead.")
        return {}
    
    def get_account_info(self) -> Dict:
        """Get account information"""
        # According to Trading 212 API docs: /api/v0/equity/account/summary
        return self._make_request("GET", "/equity/account/summary")
    
    def search_instruments(self, query: str) -> List[Dict]:
        """
        Search for instruments by name or ticker
        
        Note: This endpoint may not exist in Trading 212 API. If it returns 404,
        we'll return an empty list. Consider using /equity/metadata/instruments
        and filtering client-side instead.
        """
        try:
            result = self._make_request("GET", "/equity/search", params={"query": query}, max_retries=1)
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "items" in result:
                return result["items"]
            else:
                logger.warning(f"Unexpected search response format: {type(result)}")
                return []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(f"Search endpoint not available, returning empty list")
                return []
            logger.warning(f"Error searching instruments: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error searching instruments: {e}")
            return []

