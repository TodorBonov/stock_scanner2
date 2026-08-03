"""
US fundamentals from SEC EDGAR (free, unlimited, quarterly). Flag-only signal for the SEPA
"A": latest-quarter EPS / revenue YoY growth + acceleration.

Coverage is US-domestic filers (10-Q/10-K, US-GAAP). Foreign filers (20-F/IFRS) and any
suffixed/foreign ticker resolve to status 'n/a' — we never strip suffixes to bridge a foreign
listing to a US ticker (that caused AIR.PA -> AAR Corp collisions); we only resolve real US
tickers, and verify the match by company name when one is provided.
"""
import os
import re
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from logger_config import get_logger
from config import (
    FUNDAMENTALS_STRONG_EPS_YOY,
    FUNDAMENTALS_WEAK_EPS_YOY,
    FUNDAMENTALS_CACHE_DAYS,
    SEC_EDGAR_USER_AGENT,
)

logger = get_logger(__name__)

_CIK_MAP_FILE = Path("data/edgar_cik_map.json")
_FUND_CACHE_FILE = Path("data/fundamentals_cache.json")
_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]


# ----------------------------- pure helpers (no network) -----------------------------
def quarterly_values(units: dict, unit_key: str) -> List[float]:
    """Ascending list of ~quarter-duration values (80-100 day periods) from an EDGAR concept."""
    out = {}
    for u in (units or {}).get(unit_key, []):
        st, en = u.get("start"), u.get("end")
        if not st or not en:
            continue
        try:
            days = (date.fromisoformat(en) - date.fromisoformat(st)).days
        except Exception:
            continue
        if 80 <= days <= 100:
            out[en] = u["val"]  # later filings for same end-date overwrite (fine)
    return [v for _, v in sorted(out.items())]


def yoy_and_accel(series: List[float]):
    """(latest YoY %, acceleration bool|None) using same-quarter-last-year (index -1 vs -5)."""
    def g(a, b):
        return ((a / b - 1.0) * 100.0) if (b and b > 0) else None
    yoy = g(series[-1], series[-5]) if len(series) >= 5 else None
    prev = g(series[-2], series[-6]) if len(series) >= 6 else None
    accel = (yoy > prev) if (yoy is not None and prev is not None) else None
    return yoy, accel


def classify(eps_yoy: Optional[float], eps_accel: Optional[bool]) -> str:
    """strong / ok / weak / n-a from EPS YoY + acceleration."""
    if eps_yoy is None:
        return "n/a"
    if eps_yoy < FUNDAMENTALS_WEAK_EPS_YOY:
        return "weak"
    if eps_yoy >= FUNDAMENTALS_STRONG_EPS_YOY and eps_accel:
        return "strong"
    return "ok"


def _norm_name(s: str) -> set:
    """Tokens for loose company-name comparison (drop legal suffixes/punctuation)."""
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    drop = {"inc", "corp", "corporation", "co", "ltd", "plc", "se", "ag", "nv", "sa",
            "the", "company", "holdings", "holding", "group", "international", "incorporated"}
    return {t for t in s.split() if t and t not in drop}


def _na(reason: str = "") -> dict:
    return {"status": "n/a", "eps_yoy": None, "eps_accel": None, "rev_yoy": None,
            "source": None, "cik": None, "reason": reason}


# ----------------------------- network -----------------------------
def _session():
    if os.environ.get("DISABLE_SSL_VERIFY", "").strip().lower() in ("1", "true", "yes"):
        try:
            from curl_cffi import requests as cr
            s = cr.Session(impersonate="chrome"); s.verify = False
            return s
        except ImportError:
            pass
    import requests
    return requests.Session()


def load_cik_map(session=None) -> Dict[str, str]:
    """ticker(upper) -> 10-digit CIK, cached weekly to data/."""
    try:
        if _CIK_MAP_FILE.exists() and (time.time() - _CIK_MAP_FILE.stat().st_mtime) < 7 * 86400:
            return json.loads(_CIK_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    s = session or _session()
    try:
        r = s.get("https://www.sec.gov/files/company_tickers.json",
                  headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=40)
        data = r.json()
        m = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
        _CIK_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CIK_MAP_FILE.write_text(json.dumps(m), encoding="utf-8")
        return m
    except Exception as e:
        logger.warning("Could not load EDGAR CIK map: %s", e)
        return {}


def _concept(cik: str, concept: str, session) -> dict:
    try:
        r = session.get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json",
                        headers={"User-Agent": SEC_EDGAR_USER_AGENT}, timeout=40)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception:
        return {}


def get_fundamentals(ticker: str, company_name: Optional[str] = None,
                     session=None, cik_map: Optional[Dict[str, str]] = None) -> dict:
    """
    Quarterly EPS/revenue YoY + acceleration for a US ticker, or status 'n/a' for
    foreign/suffixed/unresolved names. Never strips exchange suffixes.
    """
    t = (ticker or "").strip().upper()
    if not t or "." in t:  # empty or suffixed (foreign listing) -> skip, never strip suffix
        return _na("foreign/suffixed")
    cik_map = cik_map if cik_map is not None else load_cik_map(session)
    cik = cik_map.get(t)
    if not cik:
        return _na("ticker not in EDGAR (likely foreign/not US filer)")
    s = session or _session()

    eps_units = _concept(cik, "EarningsPerShareDiluted", s)
    entity = eps_units.get("entityName") if isinstance(eps_units, dict) else None
    # Verify identity by company name when we have one (guards ticker reuse/collisions)
    if company_name and entity:
        if _norm_name(company_name) and _norm_name(entity) and not (_norm_name(company_name) & _norm_name(entity)):
            return _na(f"name mismatch: '{company_name}' vs EDGAR '{entity}'")

    eps = quarterly_values(eps_units.get("units", {}), "USD/shares") if eps_units else []
    rev = []
    for c in _REVENUE_CONCEPTS:
        u = _concept(cik, c, s)
        rev = quarterly_values(u.get("units", {}), "USD") if u else []
        if rev:
            break

    eps_yoy, eps_accel = yoy_and_accel(eps)
    rev_yoy, _ = yoy_and_accel(rev)
    if eps_yoy is None and rev_yoy is None:
        return _na("no quarterly data (foreign/IFRS filer)")
    return {
        "status": classify(eps_yoy, eps_accel),
        "eps_yoy": round(eps_yoy, 1) if eps_yoy is not None else None,
        "eps_accel": eps_accel,
        "rev_yoy": round(rev_yoy, 1) if rev_yoy is not None else None,
        "source": "edgar",
        "cik": cik,
        "entity": entity,
    }


def fundamentals_for_tickers(tickers, names=None, use_cache=True) -> Dict[str, dict]:
    """
    Resolve fundamentals for many tickers with a disk cache (refresh older than
    FUNDAMENTALS_CACHE_DAYS). `names` optional dict ticker->company_name for verification.
    """
    names = names or {}
    cache = {}
    if use_cache:
        try:
            cache = json.loads(_FUND_CACHE_FILE.read_text(encoding="utf-8")) if _FUND_CACHE_FILE.exists() else {}
        except Exception:
            cache = {}
    s = _session()
    cik_map = load_cik_map(s)
    out = {}
    fresh_cutoff = time.time() - FUNDAMENTALS_CACHE_DAYS * 86400
    for t in tickers:
        c = cache.get(t)
        if c and c.get("_cached_at_ts", 0) > fresh_cutoff:
            out[t] = {k: v for k, v in c.items() if k != "_cached_at_ts"}
            continue
        res = get_fundamentals(t, names.get(t), session=s, cik_map=cik_map)
        out[t] = res
        cache[t] = {**res, "_cached_at_ts": time.time()}
        time.sleep(0.15)  # gentle on SEC
    if use_cache:
        try:
            _FUND_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _FUND_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not write fundamentals cache: %s", e)
    return out
