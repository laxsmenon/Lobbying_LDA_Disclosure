"""Download Lobbying Disclosure Act filings from the official API (lda.gov).

For each year and quarter it saves two JSON-lines files:
    <raw_dir>/<year>_<period>.jsonl          one row per filing x issue x lobbyist
    <raw_dir>/issues/<year>_<period>.jsonl   one row per filing x issue (text, spend, agencies)

Downloads are resumable: finished quarters are skipped, and an interrupted
quarter restarts from its last saved page.
"""
import getpass
import json
import os
import time
from pathlib import Path

import requests

from .classify import is_self_filer

API_BASE = "https://lda.gov/api/v1/filings/"
PAGE_SIZE = 25                                   # API maximum
PERIODS = ["first_quarter", "second_quarter", "third_quarter", "fourth_quarter",
           "mid_year", "year_end"]
KEY_URL = "https://lda.gov/api/register/"


# --------------------------------------------------------------- API key
def ask_api_key():
    """Ask for the lda.gov API key in the terminal (hidden input).

    The key is used for this run only and never written to disk. If the
    environment variable LDA_API_KEY is set, it is used without asking.
    Press Enter with no key to download anonymously (much slower).
    """
    key = os.environ.get("LDA_API_KEY", "").strip()
    if key:
        print("Using the API key from the LDA_API_KEY environment variable.")
        return key
    print(f"An lda.gov API key makes downloads ~8x faster (free: {KEY_URL}).")
    try:
        key = getpass.getpass("Paste your lda.gov API key (input hidden; Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        print("No key given — continuing anonymously (slow).")
    return key


# --------------------------------------------------------------- HTTP
def make_session(api_key=""):
    """lda.gov's firewall blocks Python's default connection fingerprint
    (403 'Access Denied'); curl_cffi connects exactly like Chrome."""
    try:
        from curl_cffi import requests as creq
        s = creq.Session(impersonate="chrome")
    except ImportError:
        print("Warning: curl_cffi not installed (pip install curl_cffi); lda.gov may refuse the connection.")
        s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    if api_key:
        s.headers.update({"Authorization": f"Token {api_key}"})
    return s


def get(s, url, params=None, retries=8):
    for attempt in range(retries):
        try:
            r = s.get(url, params=params, timeout=60)
        except Exception as e:                                   # network hiccup
            wait = 10 * (attempt + 1)
            print(f"   network error ({e}); retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60))
            print(f"   rate limited; sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code in (401, 403):
            raise RuntimeError(f"{r.status_code} from lda.gov — check your API key. Server says: {r.text[:300]}")
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {url}")


# --------------------------------------------------------------- flatten
def flatten_lobbyists(filing):
    """One row per (filing, issue activity, lobbyist)."""
    rows = []
    client = filing.get("client") or {}
    registrant = filing.get("registrant") or {}
    for i, act in enumerate(filing.get("lobbying_activities") or [], start=1):
        for lb in act.get("lobbyists") or [{}]:
            p = lb.get("lobbyist") or {}
            rows.append({
                "filing_uuid": filing.get("filing_uuid"),
                "filing_type": filing.get("filing_type"),
                "filing_year": filing.get("filing_year"),
                "filing_period": filing.get("filing_period"),
                "registrant_id": registrant.get("id"),
                "registrant_name": registrant.get("name"),
                "client_name": client.get("name"),
                "activity_order": i,
                "issue_code": act.get("general_issue_code"),
                "lobbyist_api_id": p.get("id"),
                "first_name": p.get("first_name"),
                "last_name": p.get("last_name"),
                "suffix": p.get("suffix"),
                "covered_position": lb.get("covered_position"),
                "new": lb.get("new"),
            })
    return rows


def flatten_issues(filing):
    """One row per (filing, issue activity): issue text and filing-level facts."""
    client = filing.get("client") or {}
    registrant = filing.get("registrant") or {}
    self_filer = is_self_filer(registrant.get("name"), client.get("name"), client.get("client_self_select"))
    rows = []
    for i, act in enumerate(filing.get("lobbying_activities") or [], start=1):
        rows.append({
            "filing_uuid": filing.get("filing_uuid"),
            "filing_type": filing.get("filing_type"),
            "filing_year": filing.get("filing_year"),
            "filing_period": filing.get("filing_period"),
            "dt_posted": filing.get("dt_posted"),
            "registrant_id": registrant.get("id"),
            "registrant_name": registrant.get("name"),
            "client_id": client.get("id"),
            "client_name": client.get("name"),
            "self_filer": self_filer,
            "client_self_select": client.get("client_self_select"),
            "income": filing.get("income"),
            "expenses": filing.get("expenses"),
            "activity_order": i,
            "issue_code": act.get("general_issue_code"),
            "description": act.get("description"),
            "n_lobbyists": len(act.get("lobbyists") or []),
            "government_entities": "; ".join(g.get("name", "") for g in act.get("government_entities") or []),
            "filing_document_url": filing.get("filing_document_url"),
        })
    return rows


# --------------------------------------------------------------- download
def download(years, raw_dir, api_key="", periods=None):
    raw_dir = Path(raw_dir)
    (raw_dir / "issues").mkdir(parents=True, exist_ok=True)
    s = make_session(api_key)
    pause = 0.6 if api_key else 4.5                    # stay under the rate limit
    for year in years:
        for period in periods or PERIODS:
            if year >= 2012 and period in ("mid_year", "year_end"):
                continue                               # semi-annual periods ended in 2011-12
            tag = f"{year}_{period}"
            done, ckpt = raw_dir / f"{tag}.done", raw_dir / f"{tag}.next"
            if done.exists():
                print(f"{tag}: already downloaded")
                continue
            url = ckpt.read_text().strip() if ckpt.exists() else API_BASE
            params = None if ckpt.exists() else {"filing_year": year, "filing_period": period, "page_size": PAGE_SIZE}
            n = 0
            with open(raw_dir / f"{tag}.jsonl", "a", encoding="utf-8") as fl, \
                 open(raw_dir / "issues" / f"{tag}.jsonl", "a", encoding="utf-8") as fi:
                while url:
                    data = get(s, url, params)
                    params = None                      # the `next` URL already carries them
                    for f in data.get("results", []):
                        for row in flatten_lobbyists(f):
                            fl.write(json.dumps(row) + "\n")
                        for row in flatten_issues(f):
                            fi.write(json.dumps(row) + "\n")
                    n += len(data.get("results", []))
                    url = data.get("next")
                    if url:
                        ckpt.write_text(url)
                    if n % 2500 < PAGE_SIZE:
                        print(f"{tag}: {n:,} / {data.get('count', 0):,} filings")
                    time.sleep(pause)
            done.touch()
            ckpt.unlink(missing_ok=True)
            print(f"{tag}: finished ({n:,} filings)")


def test_connection(api_key=""):
    """Fetch two filings and print their structure."""
    s = make_session(api_key)
    data = get(s, API_BASE, {"filing_year": 2017, "filing_period": "first_quarter", "page_size": 2})
    print(f"Connected. Filings in 2017 Q1: {data.get('count'):,}")
    f = data["results"][0]
    print("Example filing:", f.get("filing_uuid"), f.get("filing_type"), (f.get("client") or {}).get("name"))
    print("First lobbyist row:", flatten_lobbyists(f)[:1])
