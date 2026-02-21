"""
Retry Failed Stocks Script
Re-attempts fetching data for stocks that previously failed
"""
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta

from bot import TradingBot
from config import CACHE_FILE
from cache_utils import load_cached_data, save_cached_data

# Load 01_fetch_stock_data to use fetch_stock_data (module name can't start with number, so use spec)
_spec = importlib.util.spec_from_file_location("fetch_stock_data", Path(__file__).parent / "01_fetch_stock_data.py")
fetch_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_module)

MAX_RETRY_AGE_DAYS = 7  # Retry stocks that failed more than 7 days ago


def get_failed_stocks(cached_data, retry_old_errors=True):
    """
    Get list of stocks that failed to fetch
    
    Args:
        cached_data: Cached data dictionary
        retry_old_errors: If True, also retry errors older than MAX_RETRY_AGE_DAYS
    """
    if not cached_data:
        return []
    
    stocks = cached_data.get("stocks", {})
    failed = []
    
    for ticker, stock_data in stocks.items():
        if not stock_data.get("data_available", False):
            error = stock_data.get("error", "")
            fetched_at_str = stock_data.get("fetched_at")
            
            # Check if we should retry this error
            should_retry = False
            
            if not fetched_at_str:
                # No timestamp - definitely retry
                should_retry = True
            elif retry_old_errors:
                try:
                    fetched_at = datetime.fromisoformat(fetched_at_str.replace('Z', '+00:00'))
                    age_days = (datetime.now() - fetched_at.replace(tzinfo=None)).days
                    if age_days > MAX_RETRY_AGE_DAYS:
                        should_retry = True
                except Exception as e:
                    # Invalid timestamp - retry
                    print(f"Warning: invalid fetched_at for {ticker}: {e}")
                    should_retry = True
            
            if should_retry or not fetched_at_str:
                failed.append({
                    "ticker": ticker,
                    "error": error,
                    "fetched_at": fetched_at_str
                })
    
    return failed


def main():
    """Main function"""
    print("="*80)
    print("RETRY FAILED STOCKS")
    print("="*80)
    
    # Load cache
    cached_data = load_cached_data()
    if not cached_data:
        print("Error: Could not load cache file")
        return
    
    # Get failed stocks
    failed_stocks = get_failed_stocks(cached_data, retry_old_errors=True)
    
    if not failed_stocks:
        print("\n✓ No failed stocks found - all stocks have data!")
        return
    
    print(f"\nFound {len(failed_stocks)} stocks with failed fetches:")
    for stock in failed_stocks[:10]:  # Show first 10
        print(f"  - {stock['ticker']:12s}: {stock['error']}")
    if len(failed_stocks) > 10:
        print(f"  ... and {len(failed_stocks) - 10} more")
    
    # Ask for confirmation
    response = input(f"\nRetry fetching data for {len(failed_stocks)} stocks? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled")
        return
    
    # Initialize bot
    bot = TradingBot(skip_trading212=True)
    stocks = cached_data.get("stocks", {})
    
    # Retry each failed stock
    print(f"\n{'='*80}")
    print("RETRYING FAILED STOCKS")
    print(f"{'='*80}\n")
    
    success_count = 0
    still_failed = 0
    
    for i, stock_info in enumerate(failed_stocks, 1):
        ticker = stock_info["ticker"]
        print(f"[{i}/{len(failed_stocks)}] Retrying {ticker:12s}...", end=" ", flush=True)
        
        try:
            result = fetch_module.fetch_stock_data(ticker, bot)
            
            if result.get("data_available", False):
                stocks[ticker] = result
                success_count += 1
                print(f"✓ SUCCESS ({result.get('data_points', 0)} data points)")
            else:
                stocks[ticker] = result
                still_failed += 1
                error_msg = result.get("error", "Unknown error")
                print(f"✗ Still failed: {error_msg}")
        
        except Exception as e:
            print(f"✗ Exception: {e}")
            still_failed += 1
    
    # Update cache
    cached_data["stocks"] = stocks
    cached_data["metadata"]["last_updated"] = datetime.now().isoformat()
    cached_data["metadata"]["stocks_with_data"] = sum(1 for s in stocks.values() if s.get("data_available", False))
    cached_data["metadata"]["stocks_with_errors"] = sum(1 for s in stocks.values() if not s.get("data_available", False))
    
    save_cached_data(cached_data)
    
    # Summary
    print(f"\n{'='*80}")
    print("RETRY COMPLETE")
    print(f"{'='*80}")
    print(f"Total retried: {len(failed_stocks)}")
    print(f"Successfully fetched: {success_count}")
    print(f"Still failed: {still_failed}")
    print(f"Cache updated: {CACHE_FILE}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
