# app_streamlit.py
# top of file
import os
import pandas as pd
import time
import streamlit as st
from datetime import date, datetime

from src.payday_backend import list_vendors, fetch_vendor_statement
from src.reviewer import review_vendor,  DATE_FMT

@st.cache_data(ttl=600, show_spinner=False)
def get_vendor_list():
    """Cached pull of all vendors (id, name, ssn)."""
    return list_vendors()

def run_full_review(report_date_iso: str):
    """Loops all vendors with progress, retry-once per vendor, and returns df, details, errors."""
    vendors = get_vendor_list()
    total = len(vendors)
    progress = st.progress(0.0, text=f"Reviewing vendors… 0/{total}")

    rows = []
    details = {}     # vendor_id -> review dict
    errors = []      # list of (vendor_name, error_msg)

    for i, v in enumerate(vendors, start=1):
        vid = v["id"]
        name = v.get("name", vid)

        # fetch statement with one retry
        try:
            lines = fetch_vendor_statement(vid, "2020-01-01", report_date_iso)
        except Exception:
            time.sleep(0.5)
            try:
                lines = fetch_vendor_statement(vid, "2020-01-01", report_date_iso)
            except Exception as e2:
                errors.append((name, str(e2)))
                progress.progress(i/total, text=f"Reviewing vendors… {i}/{total}")
                continue

        # analyze lines → flags/balance/timeline
        try:
            review = review_vendor(lines, report_date_iso)
        except Exception as e:
            errors.append((name, f"review error: {e}"))
            progress.progress(i/total, text=f"Reviewing vendors… {i}/{total}")
            continue

        details[vid] = review
        rows.append({
            "Vendor": name,
            "Balance (ISK)": review["balance"],
            "🔴 Red Flags": "; ".join(review["red"]),
            "🟠 Orange Flags": "; ".join(review["orange"]),
            "id": vid,
        })

        time.sleep(0.15)  # be nice to the API
        progress.progress(i/total, text=f"Reviewing vendors… {i}/{total}")

    progress.empty()
    df = pd.DataFrame(rows).sort_values("Vendor")
    return df, details, errors



# ---- your existing backend imports (reuse your CLI functions in a module) ----
# from payday_backend import get_token, list_vendors, list_vendor_balances, fetch_vendor_statement
# For MVP, you can import directly from your app.py or refactor into src/

# ---- OpenAI (LLM) placeholder ----
# from openai import OpenAI
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

st.set_page_config(page_title="Vendor Reviewer", layout="wide")

# ---------- Sidebar: Controls ----------
st.sidebar.header("Controls")
report_date = st.sidebar.date_input("Report date", value=date.today())
search = st.sidebar.text_input("Search vendor name", value="")
show_only_flagged = st.sidebar.checkbox("Show only flagged", value=False)
run_review = st.sidebar.button("Run review")
DATE_FMT = "%d.%m.%Y" 

def fmt_isk(val) -> str:
    try:
        v = float(val)
        # round to 0 decimals, thousands with dot
        return f"{int(round(v)):,} ISK".replace(",", ".")
    except Exception:
        return str(val)

# ---------- Header ----------
st.title("Vendor Reviewer")
st.caption(f"Report date: {report_date.isoformat()}")

# ---------- Data cache ----------
@st.cache_data(ttl=300, show_spinner=False)
def load_vendors_and_flags(report_date_iso: str, search_text: str):
    # 1) Pull vendors (reuse your existing functions)
    # token = get_token()
    # vendors = list_vendors()  # returns [{id, ssn, name}, ...]
    # For now, stub:
    vendors = [
        {"id": "v1", "name": "AJ3D skerping ehf.", "balance": -63014.0},
        {"id": "v2", "name": "BAUHAUS slhf.", "balance": 18004.0},
        {"id": "v3", "name": "Atlantsolía ehf.", "balance": 0.0},
    ]

    # 2) Compute flags per vendor (deterministic checks + AI review later)
    # Here we stub flags for UI demo
    flags = {
        "v1": {"red": ["Duplicate payments within 2 days"], "orange": ["Break in monthly pattern"]},
        "v2": {"red": ["Vendor shows debit balance"], "orange": []},
        "v3": {"red": [], "orange": ["Inactive vendor"]},
    }

    df = pd.DataFrame([
        {
            "Vendor": v["name"],
            "Balance (ISK)": v["balance"],
            "🔴 Red Flags": "; ".join(flags[v["id"]]["red"]) or "",
            "🟠 Orange Flags": "; ".join(flags[v["id"]]["orange"]) or "",
            "id": v["id"],
        }
        for v in vendors
        if search_text.lower() in v["name"].lower()
    ])
    if show_only_flagged:
        df = df[(df["🔴 Red Flags"] != "") | (df["🟠 Orange Flags"] != "")]
    df.sort_values("Vendor", inplace=True)
    return df, flags

# 👉 put this ABOVE the metrics (and after you read report_date/run_review controls)

if run_review:
    df_vendors, details, errors = run_full_review(report_date.isoformat())
else:
    # for now we still load once on page open; you can change to a cached copy later
    df_vendors, details, errors = run_full_review(report_date.isoformat())

# counts for the metric cards
red_count = int((df_vendors["🔴 Red Flags"] != "").sum()) if not df_vendors.empty else 0
orange_count = int((df_vendors["🟠 Orange Flags"] != "").sum()) if not df_vendors.empty else 0


# ----------- Summary cards -----------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Vendors reviewed", len(df_vendors))
with col2:
    st.metric("Red flagged", red_count)
with col3:
    st.metric("Orange flagged", orange_count)
with col4:
    st.metric("Last sync", datetime.now().strftime("%H:%M:%S"))

# Show errors (if any)
if errors:
    with st.expander(f"Errors while reviewing ({len(errors)})", expanded=False):
        for name, msg in errors:
            st.write(f"- **{name}**: {msg[:300]}")


# Vendor table
st.dataframe(df_vendors, use_container_width=True)

st.divider()

# --- Main body: table (left) + detail (right) ---
left, right = st.columns([3, 4])

with left:
    st.subheader("Vendors")

    # pretty display copy
    df_show = df_vendors.copy()
    df_show["Balance (ISK)"] = df_show["Balance (ISK)"].map(fmt_isk)

    st.dataframe(
        df_show[["Vendor", "Balance (ISK)", "🔴 Red Flags", "🟠 Orange Flags"]],
        use_container_width=True,
        hide_index=True,
    )

    selected_vendor = st.selectbox(
        "Select vendor",
        options=df_vendors["Vendor"].tolist(),
        index=0 if len(df_vendors) else None,
    )
    selected_row = df_vendors[df_vendors["Vendor"] == selected_vendor].iloc[0] if len(df_vendors) else None


with right:
    st.subheader("Vendor detail")
    if selected_row is not None:
        vid = selected_row["id"]
        st.write(f"**{selected_vendor}**")
        st.write(f"Balance (ISK): {selected_row['Balance (ISK)']:,}")
        st.write(f"Red: {selected_row['🔴 Red Flags'] or '—'}")
        st.write(f"Orange: {selected_row['🟠 Orange Flags'] or '—'}")

        # Tabs: AI review, transactions, open items
        t1, t2, t3 = st.tabs(["AI review", "Transactions", "Open items"])

        with t1:
            st.markdown("**AI summary**")
            # Here call OpenAI with the vendor’s timeline to produce narrative:
            # prompt = build_prompt_for_vendor_review(vendor_timeline, report_date)
            # ai_text = client.responses.create(model="gpt-4.1-mini", input=prompt).output_text
            ai_text = "This vendor shows repeated 18,004 ISK payments within 2 days, likely duplicates. Monthly pattern breaks after April."
            st.write(ai_text)

            st.markdown("**Your feedback**")
            fb_col1, fb_col2 = st.columns([1, 3])
            with fb_col1:
                confirm = st.button("✅ Confirm issue")
                dismiss = st.button("❌ Dismiss issue")
            with fb_col2:
                note = st.text_input("Optional note")

            if confirm:
                st.success("Flag confirmed and saved")
                # save_feedback(vid, "confirm", note)
            if dismiss:
                st.warning("Flag dismissed and saved")
                # save_feedback(vid, "dismiss", note)

        with t2:
            st.markdown("**Transactions (period)**")

            rev = details.get(vid, {})
            timeline = rev.get("timeline", [])

            
            if timeline:
                df_tx = pd.DataFrame([
                    {   
                        "date": tx["date"].strftime(DATE_FMT) if hasattr(tx["date"], "strftime") else tx["date"],
                        "description": tx.get("desc", ""),
                        "amount": tx.get("amount", 0.0),
                    }
                    for tx in timeline
                ])
                df_tx_show = df_tx.copy()
                df_tx_show["amount"] = df_tx_show["amount"].map(fmt_isk)

                st.dataframe(df_tx_show, use_container_width=True, hide_index=True)
            else:
                st.info("No transactions available for this vendor.")

        with t3:
            st.markdown("**Open items**")
            df_open = pd.DataFrame([
                {"invoice_no": "INV-1029", "date": "2025-05-30", "amount": 36008.0, "status": "Open"},
            ])
            st.dataframe(df_open, use_container_width=True, hide_index=True)

# ---------- Footer ----------
st.divider()
colA, colB = st.columns([1, 5])
with colA:
    st.download_button("Export table (CSV)", data=df_vendors.to_csv(index=False), file_name="vendors_review.csv")
with colB:
    st.caption("Powered by Payday API + OpenAI. This MVP is for internal review only.")
