# src/payday_backend.py
import os, sys, logging
from datetime import datetime
from typing import Dict, Any, List
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "https://api.payday.is").rstrip("/")
API_VERSION = os.getenv("API_VERSION", "alpha")
CLIENT_ID = (os.getenv("PAYDAY_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.getenv("PAYDAY_CLIENT_SECRET") or "").strip()

_TOKEN: Dict[str, Any] = {"access": None}

def get_token(force: bool=False) -> str:
    if _TOKEN["access"] and not force:
        return _TOKEN["access"]
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing PAYDAY_CLIENT_ID or PAYDAY_CLIENT_SECRET in .env"); sys.exit(1)
    r = requests.post(
        f"{BASE_URL}/auth/token",
        headers={"Content-Type":"application/json","Api-Version":API_VERSION,"Accept":"application/json"},
        json={"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}, timeout=30
    )
    r.raise_for_status()
    tok = r.json().get("accessToken")
    if not tok: raise RuntimeError(f"No accessToken in response: {r.text}")
    _TOKEN["access"] = tok
    return tok

def _headers(tok: str) -> Dict[str,str]:
    return {"Authorization": f"Bearer {tok}", "Api-Version": API_VERSION, "Accept": "application/json"}

def list_vendors() -> List[Dict[str,Any]]:
    tok = get_token()
    r = requests.get(f"{BASE_URL}/accounting/creditors", headers=_headers(tok), params={"balance":"false"}, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_vendor_statement(vendor_id: str, date_from: str, date_to: str, perpage: int = 200) -> List[Dict[str,Any]]:
    tok = get_token()
    url = f"{BASE_URL}/accounting/creditors/{vendor_id}/accountStatement"
    all_lines: List[Dict[str,Any]] = []
    page = 1
    while True:
        r = requests.get(url, headers=_headers(tok),
                         params={"dateFrom": date_from, "dateTo": date_to, "perpage": perpage, "page": page},
                         timeout=30)
        if r.status_code == 401:  # refresh once
            tok = get_token(force=True)
            r = requests.get(url, headers=_headers(tok), params={"dateFrom": date_from, "dateTo": date_to, "perpage": perpage, "page": page}, timeout=30)
        r.raise_for_status()
        data = r.json()
        lines = data if isinstance(data, list) else (data.get("items") or data.get("data") or data.get("results") or [])
        if not lines: break
        all_lines.extend(lines)
        if len(lines) < perpage: break
        page += 1
    return all_lines
