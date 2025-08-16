# src/reviewer.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

DATE_FMT = "%Y-%m-%d"

def _to_amount(raw) -> float:
    """Parse numbers that may come as int/float or as localized strings.
    Handles thousands separators (space, NBSP, '.', ',') and decimal commas."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).strip()

    # common junk
    s = s.replace("\u00A0", "")  # NBSP
    s = s.replace(" ", "")

    # Try plain float first
    try:
        return float(s)
    except ValueError:
        pass

    # If it looks like European format (decimal comma),
    # remove thousand separators and flip comma to dot.
    # Example: "63.014" (thousands dot) or "63,014" (decimal comma) or "1.234.567,89"
    # Strategy: if there's a comma and it's the only decimal marker, use it as decimal.
    if "," in s:
        s_eu = s.replace(".", "")  # drop dots as thousands
        s_eu = s_eu.replace(",", ".")
        try:
            return float(s_eu)
        except ValueError:
            pass

    # Last attempt: drop all grouping characters
    s_flat = s.replace(",", "").replace(".", "")
    try:
        return float(s_flat)
    except ValueError:
        return 0.0




def _parse_date(s: str) -> datetime:
    if not s: return None
    # Handles "2025-07-28T00:00:00Z" or "2025-07-28"
    try:
        if "T" in s:
            s = s.replace("Z", "+00:00")
            return datetime.fromisoformat(s).replace(tzinfo=None)
        return datetime.fromisoformat(s)
    except Exception:
        return None

def build_timeline(lines: List[Dict]) -> List[Dict]:
    """Normalize: date, description, amount. API puts txn amount under 'balance'."""
    out = []
    for ln in lines:
        d = ln.get("date") or ln.get("voucherDate")
        desc = (ln.get("description") or ln.get("text") or "").strip()
        raw_amt = ln.get("balance") if ln.get("balance") is not None else ln.get("amount") or 0
        amt = _to_amount(raw_amt)   # <<< use robust parser here
        out.append({"date": _parse_date(d), "description": desc, "amount": amt})
    out = [x for x in out if x["date"] is not None]
    out.sort(key=lambda x: x["date"])
    return out


def ending_balance(timeline: List[Dict], report_dt: datetime) -> float:
    return sum(x["amount"] for x in timeline if x["date"] <= report_dt)

def unpaid_invoice_over_50d(timeline: List[Dict], report_dt: datetime) -> List[str]:
    """MVP: treat positive amounts as 'invoice-like' and negative as payments.
       If a positive amount has not been offset by later negatives, consider it open."""
    cutoff = report_dt - timedelta(days=50)
    # Simple FIFO matching
    open_invoices: List[Tuple[datetime, float]] = []
    for tx in [t for t in timeline if t["date"] <= report_dt]:
        amt = tx["amount"]
        if amt > 0:  # invoice-like
            open_invoices.append((tx["date"], amt))
        elif amt < 0:  # payment-like
            pay = -amt
            # consume FIFO
            i = 0
            while pay > 0 and i < len(open_invoices):
                inv_date, inv_amt = open_invoices[i]
                take = min(pay, inv_amt)
                inv_amt -= take
                pay -= take
                if inv_amt <= 1.0:  # 1 ISK tolerance
                    open_invoices.pop(i)
                else:
                    open_invoices[i] = (inv_date, inv_amt)
                    i += 1
    flags = []
    for inv_date, inv_amt in open_invoices:
        if inv_date <= cutoff and inv_amt > 1.0:
            flags.append(f"Unpaid invoice >50d ({inv_date.date().isoformat()})")
    return flags

def credit_balance_mismatch(timeline: List[Dict], report_dt: datetime) -> bool:
    """If ending balance < 0, check if it equals any single open invoice (±1 ISK)."""
    bal = ending_balance(timeline, report_dt)
    if bal >= -1.0:  # not a credit
        return False
    # Build open invoices (same as above)
    # Reuse minimal version: list positive amounts not fully matched by negatives
    open_amts: List[float] = []
    for tx in [t for t in timeline if t["date"] <= report_dt]:
        if tx["amount"] > 0:
            open_amts.append(tx["amount"])
        elif tx["amount"] < 0:
            pay = -tx["amount"]
            i = 0
            while pay > 0 and i < len(open_amts):
                take = min(pay, open_amts[i])
                open_amts[i] -= take
                pay -= take
                if open_amts[i] <= 1.0:
                    open_amts.pop(i)
                else:
                    i += 1
    credit = -bal  # positive number
    for inv_amt in open_amts:
        if abs(inv_amt - credit) <= 1.0:
            return False  # matches a single open invoice
    return True  # mismatch

def duplicate_payments(timeline: List[Dict], report_dt: datetime) -> List[str]:
    """Find negative amounts duplicated within 1–2 days of each other."""
    pays = [t for t in timeline if t["date"] <= report_dt and t["amount"] < 0]
    flags = []
    for i in range(len(pays)):
        for j in range(i+1, len(pays)):
            if abs(pays[i]["amount"] - pays[j]["amount"]) <= 1.0:
                days = abs((pays[i]["date"] - pays[j]["date"]).days)
                if 1 <= days <= 2:
                    flags.append(f"Duplicate payment {abs(pays[i]['amount']):,.0f} within {days} days ({pays[i]['date'].date()} & {pays[j]['date'].date()})")
    # de-dup text
    return list(dict.fromkeys(flags))

def break_in_monthly_pattern(timeline: List[Dict], report_dt: datetime) -> bool:
    """True if 3+ consecutive months with activity then a gap ≥1 month before report date."""
    months = sorted({(t["date"].year, t["date"].month) for t in timeline if t["date"] <= report_dt})
    if len(months) < 4:
        return False
    # find any run of >=3 consecutive months
    def is_consecutive(a,b):
        y1,m1=a; y2,m2=b
        return (y2*12+m2) - (y1*12+m1) == 1
    run_start = 0
    for i in range(1,len(months)):
        if not is_consecutive(months[i-1], months[i]):
            if i - run_start >= 3:
                # run ended at i-1; now check if there's a gap to report month
                last_y, last_m = months[i-1]
                last_idx = last_y*12 + last_m
                rep_idx = report_dt.year*12 + report_dt.month
                if rep_idx - last_idx >= 1:
                    return True
            run_start = i
    # tail run
    if len(months) - run_start >= 3:
        last_y, last_m = months[-1]
        last_idx = last_y*12 + last_m
        rep_idx = report_dt.year*12 + report_dt.month
        if rep_idx - last_idx >= 1:
            return True
    return False

def inactive_with_balance(timeline: List[Dict], report_dt: datetime) -> bool:
    if len([t for t in timeline if t["date"] <= report_dt]) <= 2:
        last_dt = max((t["date"] for t in timeline if t["date"] <= report_dt), default=None)
        if not last_dt: return False
        age = (report_dt - last_dt).days
        bal = ending_balance(timeline, report_dt)
        return age >= 50 and abs(bal) > 1.0
    return False

def review_vendor(lines: List[Dict], report_date_str: str) -> Dict:
    report_dt = datetime.strptime(report_date_str, DATE_FMT)
    tl = build_timeline(lines)

    red: List[str] = []
    orange: List[str] = []

    # 🔴 rules
    red += unpaid_invoice_over_50d(tl, report_dt)
    if ending_balance(tl, report_dt) > 1.0:
        red.append("Vendor shows debit balance")
    if credit_balance_mismatch(tl, report_dt):
        red.append("Credit balance ≠ any open invoice")
    red += duplicate_payments(tl, report_dt)

    # 🟠 rules
    if break_in_monthly_pattern(tl, report_dt):
        orange.append("Break in monthly pattern")
    if inactive_with_balance(tl, report_dt):
        orange.append("Inactive vendor with non-zero balance")

    bal = ending_balance(tl, report_dt)
    return {
        "balance": bal,
        "red": red,
        "orange": orange,
        "timeline": tl,  # keep for UI/AI narrative
    }
