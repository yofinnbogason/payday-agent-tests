import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any

import requests
from dotenv import load_dotenv

# ---------------- config / logging ----------------
load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://api.payday.is").rstrip("/")
API_VERSION = os.getenv("API_VERSION", "alpha")
CLIENT_ID = (os.getenv("PAYDAY_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.getenv("PAYDAY_CLIENT_SECRET") or "").strip()

DEBUG = "--debug" in sys.argv
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(levelname)s: %(message)s"
)
# remove --debug so parsing stays simple
if DEBUG:
    sys.argv.remove("--debug")

def require_creds():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing PAYDAY_CLIENT_ID or PAYDAY_CLIENT_SECRET in .env")
        sys.exit(1)

# ---------------- auth (cached) ----------------
_TOKEN_CACHE: Dict[str, Any] = {"access_token": None, "exp": None}

def get_token(force: bool = False) -> str:
    """
    Returns an access token. In-memory cache per process.
    Force=True skips cache.
    """
    if not force and _TOKEN_CACHE.get("access_token"):
        return _TOKEN_CACHE["access_token"]

    require_creds()
    url = f"{BASE_URL}/auth/token"
    headers = {
        "Content-Type": "application/json",
        "Api-Version": API_VERSION,
        "Accept": "application/json",
    }
    payload = {"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}
    logging.debug(f"POST {url}")
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code >= 400:
        print(f"Auth error {r.status_code}: {r.text}")
        r.raise_for_status()
    data = r.json()
    token = data.get("accessToken")
    if not token:
        raise RuntimeError(f"No accessToken in auth response: {data}")
    _TOKEN_CACHE["access_token"] = token
    return token

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Api-Version": API_VERSION,
        "Accept": "application/json",
    }

# -------------- HTTP helper with retry --------------
def _get_with_retry(url: str, token: str, params: Dict[str, Any] | None = None) -> requests.Response:
    """GET once; if 401, refresh token once and retry."""
    logging.debug(f"GET {url} params={params}")
    r = requests.get(url, headers=_headers(token), params=params or {}, timeout=30)
    if r.status_code == 401:
        logging.info("401 received. Refreshing token and retrying once…")
        new_token = get_token(force=True)
        r = requests.get(url, headers=_headers(new_token), params=params or {}, timeout=30)
        # update cache if succeeded
        if r.status_code < 400:
            _TOKEN_CACHE["access_token"] = new_token
    return r

# ---------------- CLI ops ----------------
def list_vendors() -> None:
    token = get_token()
    url = f"{BASE_URL}/accounting/creditors"
    r = _get_with_retry(url, token, params={"balance": "false"})
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text}")
        r.raise_for_status()
    for v in r.json():
        print(f"{v.get('id')} | {v.get('ssn')} | {v.get('name')}")

def list_vendor_balances(asof: str) -> None:
    # sanity check date
    try:
        datetime.strptime(asof, "%Y-%m-%d")
    except ValueError:
        print("Invalid date. Use YYYY-MM-DD.")
        sys.exit(1)

    token = get_token()
    url = f"{BASE_URL}/accounting/creditors"
    r = _get_with_retry(url, token, params={"balance": "true", "date": asof})
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text}")
        r.raise_for_status()
    data = r.json()
    for v in data:
        bid = v.get("id")
        name = v.get("name")
        bal = v.get("balance") or v.get("currentBalance")
        print(f"{bid} | {name} | {bal}")

def find_vendor(name_query: str) -> None:
    """Simple case-insensitive contains filter on the vendors list."""
    token = get_token()
    url = f"{BASE_URL}/accounting/creditors"
    r = _get_with_retry(url, token, params={"balance": "false"})
    if r.status_code >= 400:
        print(f"Error {r.status_code}: {r.text}")
        r.raise_for_status()

    q = name_query.lower()
    hits = []
    for v in r.json():
        name = v.get("name") or ""
        if q in name.lower():
            hits.append(v)

    if not hits:
        print("No matches.")
        return

    for v in hits:
        print(f"{v.get('id')} | {v.get('ssn')} | {v.get('name')}")

def fetch_vendor_statement(vendor_id: str, date_from: str, date_to: str, perpage: int = 100) -> List[Dict[str, Any]]:
    token = get_token()
    url = f"{BASE_URL}/accounting/creditors/{vendor_id}/accountStatement"

    # validate dates
    for d in (date_from, date_to):
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            print("Invalid date. Use YYYY-MM-DD.")
            sys.exit(1)

    all_lines: List[Dict[str, Any]] = []
    page = 1
    while True:
        params = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "perpage": perpage,
            "page": page,
        }
        r = _get_with_retry(url, token, params=params)
        if r.status_code >= 400:
            print(f"Error {r.status_code}: {r.text}")
            r.raise_for_status()
        data = r.json()
        lines = data if isinstance(data, list) else (data.get("items") or data.get("data") or data.get("results") or [])
        if not lines:
            break
        all_lines.extend(lines)
        if len(lines) < perpage:
            break
        page += 1
    return all_lines

# ---------- printing / export ----------
def _fmt_date(d: str) -> str:
    try:
        if not d:
            return ""
        if "T" in d:
            return datetime.fromisoformat(d.replace("Z", "+00:00")).date().isoformat()
        return datetime.fromisoformat(d).date().isoformat()
    except Exception:
        return d or ""

def print_statement(lines: List[Dict[str, Any]], vendor_id: str, date_from: str, date_to: str) -> None:
    print(f"Statement for {vendor_id} ({date_from} → {date_to})")
    running = 0.0
    for ln in lines:
        d = _fmt_date(ln.get("date") or ln.get("voucherDate") or "")
        desc = (ln.get("description") or ln.get("text") or "").strip()
        raw_amt = ln.get("balance") or ln.get("amount") or 0
        try:
            amt = float(raw_amt)
        except Exception:
            amt = 0.0
        debit = amt if amt > 0 else 0.0
        credit = abs(amt) if amt < 0 else 0.0
        running += amt
        print(f"{d} | {desc} | AMT {amt:,.2f} | DR {debit:,.2f} | CR {credit:,.2f} | BAL {running:,.2f}")

def save_statement_csv(lines: List[Dict[str, Any]], out_path: str) -> None:
    import csv
    running = 0.0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "description", "amount", "debit", "credit", "balance"])
        for ln in lines:
            d = ln.get("date") or ln.get("voucherDate") or ""
            desc = (ln.get("description") or ln.get("text") or "").strip()
            raw_amt = ln.get("balance") or ln.get("amount") or 0
            try:
                amt = float(raw_amt)
            except Exception:
                amt = 0.0
            debit = amt if amt > 0 else 0.0
            credit = abs(amt) if amt < 0 else 0.0
            running += amt
            w.writerow([d, desc, amt, debit, credit, running])

# ---------------- main ----------------
def main():
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python app.py vendors [--debug]\n"
            "  python app.py balances --asof YYYY-MM-DD [--debug]\n"
            "  python app.py find-vendor --name \"query\" [--debug]\n"
            "  python app.py statement --vendor-id ID --from YYYY-MM-DD --to YYYY-MM-DD [--csv out.csv] [--debug]"
        )
        sys.exit(0)

    cmd = sys.argv[1].lower()
    try:
        if cmd == "vendors":
            list_vendors()

        elif cmd == "balances":
            idx = sys.argv.index("--asof")
            asof = sys.argv[idx + 1]
            list_vendor_balances(asof)

        elif cmd == "find-vendor":
            idx = sys.argv.index("--name")
            q = sys.argv[idx + 1]
            find_vendor(q)

        elif cmd == "statement":
            vid = sys.argv[sys.argv.index("--vendor-id") + 1]
            dfrom = sys.argv[sys.argv.index("--from") + 1]
            dto = sys.argv[sys.argv.index("--to") + 1]
            lines = fetch_vendor_statement(vid, dfrom, dto)
            print_statement(lines, vid, dfrom, dto)
            if "--csv" in sys.argv:
                out_csv = sys.argv[sys.argv.index("--csv") + 1]
                save_statement_csv(lines, out_csv)
                print(f"Saved CSV → {out_csv}")

        else:
            print("Unknown command. Run without args to see usage.")
    except (ValueError, IndexError):
        print("Missing/invalid arguments. Run without args to see usage.")
        sys.exit(1)

if __name__ == "__main__":
    main()