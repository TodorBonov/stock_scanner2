"""
Position sizing helper: suggest position size in $ and shares from account size and risk %.
Uses risk per share (buy_price - stop_loss) so that total risk = account_size * risk_pct.
Run after scan; can read from latest scan results or pass buy/stop manually.
"""
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from config import REPORTS_DIR, SCAN_RESULTS_LATEST


def position_size_from_risk(
    account_size: float,
    risk_pct_per_trade: float,
    buy_price: float,
    stop_loss: float,
) -> Optional[Dict]:
    """
    Given account size, risk % per trade, and buy/stop, return suggested position size.
    risk_per_share = buy_price - stop_loss; risk_amount = account_size * (risk_pct/100);
    shares = risk_amount / risk_per_share; position_value = shares * buy_price.
    """
    if buy_price <= 0 or stop_loss >= buy_price:
        return None
    risk_per_share = buy_price - stop_loss
    if risk_per_share <= 0:
        return None
    risk_amount = account_size * (risk_pct_per_trade / 100)
    shares = int(risk_amount / risk_per_share)
    if shares < 1:
        shares = 0
    position_value = shares * buy_price
    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "risk_pct_of_account": risk_pct_per_trade,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Suggest position size in $ and shares from account size and risk %% per trade"
    )
    parser.add_argument("--account", type=float, required=True, help="Account size (e.g. 10000)")
    parser.add_argument("--risk-pct", type=float, default=1.0, help="Risk per trade as %% of account (default: 1)")
    parser.add_argument("--from-scan", action="store_true", help="Use latest scan results (A-grade + pre-breakout)")
    parser.add_argument("--ticker", type=str, help="Single ticker (with --from-scan)")
    parser.add_argument("--buy", type=float, help="Buy price (manual, without --from-scan)")
    parser.add_argument("--stop", type=float, help="Stop loss price (manual, without --from-scan)")
    args = parser.parse_args()

    if args.from_scan:
        path = Path(SCAN_RESULTS_LATEST)
        if not path.exists():
            print(f"Scan results not found at {path}. Run 04_generate_full_report.py first.")
            return
        with open(path, encoding="utf-8") as f:
            results = json.load(f)
        tickers = [r for r in results if "error" not in r and r.get("buy_sell_prices", {}).get("pivot_price") is not None]
        if args.ticker:
            tickers = [r for r in tickers if r.get("ticker") == args.ticker]
        if not tickers:
            print("No scan results with buy/stop found.")
            return
        print(f"Account: ${args.account:,.2f}  Risk per trade: {args.risk_pct}%")
        print("-" * 60)
        for r in tickers:
            buy_sell = r.get("buy_sell_prices", {})
            buy_price = buy_sell.get("buy_price")
            stop_loss = buy_sell.get("stop_loss")
            if buy_price is None or stop_loss is None:
                continue
            sz = position_size_from_risk(args.account, args.risk_pct, float(buy_price), float(stop_loss))
            if sz is None:
                continue
            ticker = r.get("ticker", "?")
            grade = r.get("overall_grade", "?")
            print(f"  {ticker:12s} Grade {grade}: Buy ${buy_price:.2f} Stop ${stop_loss:.2f}")
            print(f"    -> {sz['shares']} shares (${sz['position_value']:,.2f})  Risk ${sz['risk_amount']:,.2f} ({sz['risk_pct_of_account']}%)")
        return

    if args.buy is not None and args.stop is not None:
        sz = position_size_from_risk(args.account, args.risk_pct, args.buy, args.stop)
        if sz is None:
            print("Invalid buy/stop (need buy > stop).")
            return
        print(f"Account: ${args.account:,.2f}  Risk per trade: {args.risk_pct}%")
        print(f"Buy: ${args.buy:.2f}  Stop: ${args.stop:.2f}")
        print(f"  -> {sz['shares']} shares (${sz['position_value']:,.2f})  Risk ${sz['risk_amount']:,.2f}")
        return

    parser.print_help()
    print("\nExamples:")
    print("  python position_sizing.py --account 20000 --risk-pct 1 --from-scan")
    print("  python position_sizing.py --account 10000 --risk-pct 1 --buy 50 --stop 47.5")


if __name__ == "__main__":
    main()
