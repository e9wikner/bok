"""Streamlit frontend for Bokföringssystem.

Run with: streamlit run frontend/app.py
"""

import os
import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime
import json

# Page config
st.set_page_config(
    page_title="Bokföringssystem",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration - read from environment or use defaults
DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")

API_URL = st.sidebar.text_input("API URL", DEFAULT_API_URL)
API_KEY = st.sidebar.text_input("API Key", DEFAULT_API_KEY, type="password")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Check API health
def check_health():
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        return resp.status_code == 200
    except:
        return False

# Sidebar navigation
st.sidebar.title("📊 Bokföringssystem")
st.sidebar.markdown("---")

# Health check
if check_health():
    st.sidebar.success("✅ API Connected")
else:
    st.sidebar.error("❌ API Offline")
    st.sidebar.info("Starta API:et med: `docker-compose up`")

page = st.sidebar.radio(
    "Navigering",
    ["🏠 Dashboard", "📒 Kontoplan", "📝 Verifikationer", "📄 Fakturor", "📖 Huvudbok", "📈 Rapporter", "🎯 Demo Data"]
)

# Helper functions
def get_accounts():
    try:
        resp = requests.get(f"{API_URL}/api/v1/accounts", headers=HEADERS)
        return resp.json().get("accounts", []) if resp.status_code == 200 else []
    except:
        return []

def get_vouchers():
    try:
        resp = requests.get(f"{API_URL}/api/v1/vouchers", params={"status": "all"}, headers=HEADERS)
        return resp.json().get("vouchers", []) if resp.status_code == 200 else []
    except:
        return []

def get_invoices():
    try:
        resp = requests.get(f"{API_URL}/api/v1/invoices", headers=HEADERS)
        data = resp.json() if resp.status_code == 200 else {}
        return data.get("invoices", []) if isinstance(data, dict) else data
    except:
        return []

def get_periods():
    try:
        resp = requests.get(f"{API_URL}/api/v1/periods", headers=HEADERS)
        return resp.json().get("periods", []) if resp.status_code == 200 else []
    except:
        return []

def get_fiscal_years():
    try:
        resp = requests.get(f"{API_URL}/api/v1/fiscal-years", headers=HEADERS)
        data = resp.json() if resp.status_code == 200 else {}
        return data.get("fiscal_years", []) if isinstance(data, dict) else []
    except:
        return []

def get_trial_balance(period_id):
    try:
        resp = requests.get(f"{API_URL}/api/v1/reports/trial-balance", params={"period_id": period_id}, headers=HEADERS)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def get_account_ledger(account_code, period_id):
    try:
        resp = requests.get(
            f"{API_URL}/api/v1/reports/account/{account_code}",
            params={"period_id": period_id},
            headers=HEADERS
        )
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def format_currency(amount_ore):
    """Format öre as SEK."""
    return f"{amount_ore / 100:,.2f} kr".replace(",", " ")

# ==================== DASHBOARD ====================
if page == "🏠 Dashboard":
    st.title("🏠 Översikt")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    accounts = get_accounts()
    vouchers = get_vouchers()
    invoices = get_invoices()
    periods = get_periods()
    
    with col1:
        st.metric("Konton", len(accounts))
    with col2:
        st.metric("Verifikationer", len(vouchers))
    with col3:
        st.metric("Fakturor", len(invoices))
    with col4:
        st.metric("Perioder", len(periods))
    
    st.markdown("---")
    
    # Recent activity
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📝 Senaste verifikationerna")
        if vouchers:
            recent = sorted(vouchers, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
            for v in recent:
                status_icon = "✅" if v.get("status") == "posted" else "📝"
                st.markdown(f"{status_icon} **{v.get('series')}{v.get('number')}** - {v.get('description', 'N/A')}")
                st.caption(f"{v.get('date')} | {format_currency(sum(r.get('debit', 0) for r in v.get('rows', [])))}")
        else:
            st.info("Inga verifikationer")
    
    with col_right:
        st.subheader("📄 Senaste fakturorna")
        if invoices:
            recent = sorted(invoices, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
            for inv in recent:
                status_colors = {
                    "draft": "⚪",
                    "sent": "🟡",
                    "paid": "🟢",
                    "partially_paid": "🟠"
                }
                icon = status_colors.get(inv.get("status"), "⚪")
                st.markdown(f"{icon} **{inv.get('invoice_number')}** - {inv.get('customer_name', 'N/A')}")
                st.caption(f"{format_currency(inv.get('amount_inc_vat', 0))} | {inv.get('status')}")
        else:
            st.info("Inga fakturor")
    
    # Charts
    st.markdown("---")
    st.subheader("📊 Omsättning över tid")
    
    if vouchers:
        # Group by month
        monthly_data = {}
        for v in vouchers:
            if v.get("status") == "posted":
                month = v.get("date", "")[:7]  # YYYY-MM
                amount = sum(r.get("credit", 0) for r in v.get("rows", []) 
                          if any(a.get("code", "").startswith(("3", "4")) for a in accounts 
                              if a.get("code") == r.get("account_code")))
                monthly_data[month] = monthly_data.get(month, 0) + amount
        
        if monthly_data:
            df = pd.DataFrame([
                {"Månad": k, "Omsättning (kr)": v / 100}
                for k, v in sorted(monthly_data.items())
            ])
            st.bar_chart(df.set_index("Månad"))
        else:
            st.info("Ingen bokförd omsättning än")
    else:
        st.info("Skapa verifikationer för att se statistik")

# ==================== KONTOPLAN ====================
elif page == "📒 Kontoplan":
    st.title("📒 Kontoplan (BAS 2026)")
    
    accounts = get_accounts()
    
    if accounts:
        # Filter by type
        account_types = ["Alla"] + sorted(list(set(a.get("account_type", "unknown") for a in accounts)))
        selected_type = st.selectbox("Filtera efter typ", account_types)
        
        # Search
        search = st.text_input("🔍 Sök konto", "")
        
        # Filter
        filtered = accounts
        if selected_type != "Alla":
            filtered = [a for a in filtered if a.get("account_type") == selected_type]
        if search:
            filtered = [a for a in filtered if search.lower() in a.get("name", "").lower() 
                       or search in a.get("code", "")]
        
        # Display as table
        df = pd.DataFrame([
            {
                "Konto": a.get("code"),
                "Namn": a.get("name"),
                "Typ": a.get("account_type"),
                "Aktiv": "✅" if a.get("active") else "❌"
            }
            for a in filtered
        ])
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Visar {len(filtered)} av {len(accounts)} konton")
        
        # Account groups visualization
        st.markdown("---")
        st.subheader("📊 Konton per typ")
        
        type_counts = {}
        for a in accounts:
            t = a.get("account_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        
        df_types = pd.DataFrame([
            {"Typ": k, "Antal": v}
            for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        ])
        st.bar_chart(df_types.set_index("Typ"))
    else:
        st.info("Inga konton hittades. Kör demo-data generering.")

# ==================== VERIFIKATIONER ====================
elif page == "📝 Verifikationer":
    st.title("📝 Verifikationer")
    
    vouchers = get_vouchers()
    
    if vouchers:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.selectbox("Status", ["Alla", "draft", "posted"])
        with col2:
            series_filter = st.selectbox("Serie", ["Alla"] + sorted(list(set(v.get("series") for v in vouchers))))
        
        # Filter
        filtered = vouchers
        if status_filter != "Alla":
            filtered = [v for v in filtered if v.get("status") == status_filter]
        if series_filter != "Alla":
            filtered = [v for v in filtered if v.get("series") == series_filter]
        
        # List vouchers
        for v in filtered:
            with st.expander(f"{v.get('series')}{v.get('number')} - {v.get('description', 'N/A')} ({v.get('date')})"):
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    status_color = "🟢" if v.get("status") == "posted" else "🟡"
                    st.write(f"{status_color} **Status:** {v.get('status')}")
                with col2:
                    st.write(f"**Datum:** {v.get('date')}")
                with col3:
                    st.write(f"**Period:** {v.get('period_id', 'N/A')[:8]}...")
                
                # Rows table
                rows_data = []
                for r in v.get("rows", []):
                    rows_data.append({
                        "Konto": r.get("account_code"),
                        "Beskrivning": r.get("description", "-"),
                        "Debet": format_currency(r.get("debit", 0)) if r.get("debit") else "",
                        "Kredit": format_currency(r.get("credit", 0)) if r.get("credit") else ""
                    })
                
                if rows_data:
                    st.table(pd.DataFrame(rows_data))
                
                total_debit = sum(r.get("debit", 0) for r in v.get("rows", []))
                total_credit = sum(r.get("credit", 0) for r in v.get("rows", []))
                st.caption(f"**Summa:** Debet {format_currency(total_debit)} | Kredit {format_currency(total_credit)}")
                
                if v.get("status") == "draft":
                    if st.button("Bokför", key=f"post_{v.get('id')}"):
                        try:
                            resp = requests.post(
                                f"{API_URL}/api/v1/vouchers/{v.get('id')}/post",
                                headers=HEADERS
                            )
                            if resp.status_code == 200:
                                st.success("✅ Bokförd!")
                                st.rerun()
                            else:
                                st.error(f"Fel: {resp.text}")
                        except Exception as e:
                            st.error(f"Fel: {e}")
    else:
        st.info("Inga verifikationer hittades")
    
    # Create new voucher form
    st.markdown("---")
    st.subheader("➕ Skapa ny verifikation")
    
    periods = get_periods()
    if periods:
        with st.form("new_voucher"):
            series = st.selectbox("Serie", ["A", "B"])
            voucher_date = st.date_input("Datum", date.today())
            period = st.selectbox("Period", 
                [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d}") for p in periods if not p.get("locked")],
                format_func=lambda x: x[1]
            )
            description = st.text_input("Beskrivning")
            
            st.write("**Rader**")
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
            with col1:
                account = st.text_input("Konto", value="1510", key="row1_acc")
            with col2:
                row_desc = st.text_input("Beskrivning", value="", key="row1_desc")
            with col3:
                debit = st.number_input("Debet", value=0, step=100, key="row1_deb")
            with col4:
                credit = st.number_input("Kredit", value=10000, step=100, key="row1_cred")
            
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
            with col1:
                account2 = st.text_input("Konto", value="3011", key="row2_acc")
            with col2:
                row_desc2 = st.text_input("Beskrivning", value="", key="row2_desc")
            with col3:
                debit2 = st.number_input("Debet", value=10000, step=100, key="row2_deb")
            with col4:
                credit2 = st.number_input("Kredit", value=0, step=100, key="row2_cred")
            
            auto_post = st.checkbox("Bokför direkt", value=False)
            
            submitted = st.form_submit_button("Skapa verifikation")
            
            if submitted:
                rows = []
                if debit > 0 or credit > 0:
                    rows.append({"account": account, "debit": debit, "credit": credit, "description": row_desc})
                if debit2 > 0 or credit2 > 0:
                    rows.append({"account": account2, "debit": debit2, "credit": credit2, "description": row_desc2})
                
                data = {
                    "series": series,
                    "date": voucher_date.isoformat(),
                    "period_id": period[0] if period else None,
                    "description": description,
                    "rows": rows,
                    "auto_post": auto_post
                }
                
                try:
                    resp = requests.post(
                        f"{API_URL}/api/v1/vouchers",
                        headers={**HEADERS, "Content-Type": "application/json"},
                        json=data
                    )
                    if resp.status_code == 201:
                        st.success("✅ Verifikation skapad!")
                        st.rerun()
                    else:
                        st.error(f"Fel: {resp.text}")
                except Exception as e:
                    st.error(f"Fel: {e}")
    else:
        st.warning("Skapa en räkenskapsperiod först (använd Demo Data)")

# ==================== FAKTUROR ====================
elif page == "📄 Fakturor":
    st.title("📄 Fakturahantering")
    
    invoices = get_invoices()
    
    if invoices:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        total_outstanding = sum(inv.get("amount_inc_vat", 0) for inv in invoices 
                               if inv.get("status") in ["sent", "partially_paid"])
        total_paid = sum(inv.get("amount_inc_vat", 0) for inv in invoices if inv.get("status") == "paid")
        total_draft = sum(inv.get("amount_inc_vat", 0) for inv in invoices if inv.get("status") == "draft")
        
        with col1:
            st.metric("Obetalt", format_currency(total_outstanding))
        with col2:
            st.metric("Betalt", format_currency(total_paid))
        with col3:
            st.metric("Utkast", format_currency(total_draft))
        with col4:
            st.metric("Totalt", format_currency(sum(inv.get("amount_inc_vat", 0) for inv in invoices)))
        
        st.markdown("---")
        
        # Invoice list
        status_filter = st.selectbox("Filtera status", ["Alla", "draft", "sent", "partially_paid", "paid"])
        
        filtered = invoices
        if status_filter != "Alla":
            filtered = [i for i in filtered if i.get("status") == status_filter]
        
        for inv in filtered:
            status_icons = {
                "draft": "⚪",
                "sent": "🟡",
                "partially_paid": "🟠",
                "paid": "🟢"
            }
            icon = status_icons.get(inv.get("status"), "⚪")
            
            with st.expander(f"{icon} {inv.get('invoice_number')} - {inv.get('customer_name', 'N/A')}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Kund:** {inv.get('customer_name')}")
                    st.write(f"**E-post:** {inv.get('customer_email', 'N/A')}")
                with col2:
                    st.write(f"**Fakturadatum:** {inv.get('invoice_date')}")
                    st.write(f"**Förfallodatum:** {inv.get('due_date')}")
                with col3:
                    st.write(f"**Status:** {inv.get('status')}")
                    st.write(f"**Belopp ex moms:** {format_currency(inv.get('amount_ex_vat', 0))}")
                    st.write(f"**Moms:** {format_currency(inv.get('vat_amount', 0))}")
                    st.write(f"**Totalt:** {format_currency(inv.get('amount_inc_vat', 0))}")
                
                # Invoice rows
                st.write("**Rader:**")
                rows_data = []
                for r in inv.get("rows", []):
                    rows_data.append({
                        "Beskrivning": r.get("description"),
                        "Antal": r.get("quantity"),
                        "À-pris": format_currency(r.get("unit_price", 0)),
                        "Moms": r.get("vat_code"),
                        "Summa": format_currency(r.get("row_total_ex_vat", 0))
                    })
                if rows_data:
                    st.table(pd.DataFrame(rows_data))
                
                # Payments
                payments = inv.get("payments", [])
                if payments:
                    st.write(f"**Betalningar ({len(payments)}):**")
                    for p in payments:
                        st.caption(f"{p.get('payment_date')}: {format_currency(p.get('amount', 0))} ({p.get('payment_method')})")
                
                # Actions
                if inv.get("status") == "draft":
                    if st.button("Skicka faktura", key=f"send_{inv.get('id')}"):
                        try:
                            resp = requests.post(
                                f"{API_URL}/api/v1/invoices/{inv.get('id')}/send",
                                headers=HEADERS
                            )
                            if resp.status_code == 200:
                                st.success("✅ Skickad!")
                                st.rerun()
                            else:
                                st.error(f"Fel: {resp.text}")
                        except Exception as e:
                            st.error(f"Fel: {e}")
                
                elif inv.get("status") in ["sent", "partially_paid"]:
                    with st.form(f"payment_{inv.get('id')}"):
                        st.write("**Registrera betalning**")
                        pay_amount = st.number_input("Belopp (öre)", 
                                                    value=inv.get("remaining_amount", inv.get("amount_inc_vat")),
                                                    step=100)
                        pay_date = st.date_input("Betalningsdatum", date.today())
                        pay_method = st.selectbox("Betalningsmetod", 
                                                 ["bank_transfer", "card", "cash", "swish"])
                        
                        if st.form_submit_button("Registrera betalning"):
                            try:
                                resp = requests.post(
                                    f"{API_URL}/api/v1/invoices/{inv.get('id')}/payments",
                                    headers={**HEADERS, "Content-Type": "application/json"},
                                    json={
                                        "amount": pay_amount,
                                        "payment_date": pay_date.isoformat(),
                                        "payment_method": pay_method
                                    }
                                )
                                if resp.status_code == 200:
                                    st.success("✅ Betalning registrerad!")
                                    st.rerun()
                                else:
                                    st.error(f"Fel: {resp.text}")
                            except Exception as e:
                                st.error(f"Fel: {e}")
    else:
        st.info("Inga fakturor hittades")
    
    # Create invoice form
    st.markdown("---")
    st.subheader("➕ Skapa ny faktura")
    
    with st.form("new_invoice"):
        customer_name = st.text_input("Kundnamn")
        customer_email = st.text_input("Kund e-post")
        invoice_date = st.date_input("Fakturadatum", date.today())
        due_date = st.date_input("Förfallodatum", date.today())
        
        st.write("**Fakturarader**")
        
        rows = []
        for i in range(3):
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                desc = st.text_input(f"Beskrivning {i+1}", key=f"inv_row_{i}_desc")
            with cols[1]:
                qty = st.number_input(f"Antal", value=1, min_value=1, key=f"inv_row_{i}_qty")
            with cols[2]:
                price = st.number_input(f"Pris", value=0, step=1000, key=f"inv_row_{i}_price")
            with cols[3]:
                vat = st.selectbox(f"Moms", ["MP1 (25%)", "MP2 (12%)", "MP3 (6%)"], key=f"inv_row_{i}_vat")
            
            if desc and price > 0:
                vat_code = vat.split()[0]
                rows.append({
                    "description": desc,
                    "quantity": qty,
                    "unit_price": price,
                    "vat_code": vat_code
                })
        
        submit = st.form_submit_button("Skapa faktura")
        
        if submit and customer_name and rows:
            data = {
                "customer_name": customer_name,
                "customer_email": customer_email if customer_email else None,
                "invoice_date": invoice_date.isoformat(),
                "due_date": due_date.isoformat(),
                "rows": rows
            }
            
            try:
                resp = requests.post(
                    f"{API_URL}/api/v1/invoices",
                    headers={**HEADERS, "Content-Type": "application/json"},
                    json=data
                )
                if resp.status_code == 201:
                    result = resp.json()
                    st.success(f"✅ Faktura {result.get('invoice_number')} skapad!")
                    st.rerun()
                else:
                    st.error(f"Fel: {resp.text}")
            except Exception as e:
                st.error(f"Fel: {e}")

# ==================== HUVUDBOK ====================
elif page == "📖 Huvudbok":
    st.title("📖 Huvudbok (General Ledger)")
    
    accounts = get_accounts()
    periods = get_periods()
    
    if not accounts:
        st.info("Inga konton hittades. Kör demo-data generering först.")
    elif not periods:
        st.info("Inga perioder hittades. Skapa ett räkenskapsår först.")
    else:
        # Period selector
        period_options = [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d}") for p in periods]
        selected_period = st.selectbox("Välj period", period_options, format_func=lambda x: x[1])
        
        if selected_period:
            period_id = selected_period[0]
            
            # Get trial balance for overview
            tb = get_trial_balance(period_id)
            
            # Overview: accounts with balances
            st.subheader("💰 Kontosaldon")
            
            if tb and tb.get("rows"):
                tb_rows = tb.get("rows", [])
                
                # Build lookup: account_code -> account info
                account_lookup = {a.get("code"): a for a in accounts}
                
                overview_data = []
                for r in tb_rows:
                    code = r.get("account_code", "")
                    acc_info = account_lookup.get(code, {})
                    balance = r.get("balance", 0)
                    overview_data.append({
                        "Konto": code,
                        "Namn": acc_info.get("name", ""),
                        "Typ": acc_info.get("account_type", ""),
                        "Debet": format_currency(r.get("debit", 0)),
                        "Kredit": format_currency(r.get("credit", 0)),
                        "Saldo": format_currency(balance),
                        "_balance_raw": balance,
                    })
                
                df_overview = pd.DataFrame(overview_data)
                
                # Show summary by account type
                col1, col2, col3, col4 = st.columns(4)
                type_sums = {}
                for row in overview_data:
                    t = row["Typ"]
                    type_sums[t] = type_sums.get(t, 0) + row["_balance_raw"]
                
                type_labels = {
                    "asset": ("🏦 Tillgångar", col1),
                    "liability": ("💳 Skulder", col2),
                    "revenue": ("📈 Intäkter", col3),
                    "expense": ("📉 Kostnader", col4),
                }
                for t, (label, col) in type_labels.items():
                    with col:
                        st.metric(label, format_currency(type_sums.get(t, 0)))
                
                st.markdown("---")
                
                # Filter
                type_filter = st.selectbox("Filtrera kontotyp", ["Alla", "asset", "liability", "equity", "revenue", "expense"])
                
                display_df = df_overview.drop(columns=["_balance_raw"])
                if type_filter != "Alla":
                    display_df = display_df[display_df["Typ"] == type_filter]
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen bokförd data för vald period.")
            
            # Detailed account ledger
            st.markdown("---")
            st.subheader("📋 Kontoutdrag")
            
            # Group accounts by type for easier selection
            account_options = [(a.get("code"), f"{a.get('code')} - {a.get('name')}") for a in accounts]
            selected_account = st.selectbox(
                "Välj konto för detaljvy",
                account_options,
                format_func=lambda x: x[1]
            )
            
            if selected_account:
                ledger_data = get_account_ledger(selected_account[0], period_id)
                
                if ledger_data and ledger_data.get("rows"):
                    st.write(f"**Konto:** {ledger_data.get('account_code')} - {ledger_data.get('account_name')}")
                    
                    ledger_rows = []
                    for r in ledger_data.get("rows", []):
                        ledger_rows.append({
                            "Datum": r.get("date"),
                            "Ver.nr": f"{r.get('voucher_series', '')}{r.get('voucher_number', '')}",
                            "Beskrivning": r.get("description", ""),
                            "Debet": format_currency(r.get("debit", 0)) if r.get("debit") else "",
                            "Kredit": format_currency(r.get("credit", 0)) if r.get("credit") else "",
                            "Saldo": format_currency(r.get("balance", 0)),
                        })
                    
                    df_ledger = pd.DataFrame(ledger_rows)
                    st.dataframe(df_ledger, use_container_width=True, hide_index=True)
                    
                    ending = ledger_data.get("ending_balance", 0)
                    st.success(f"**Slutsaldo:** {format_currency(ending)}")
                else:
                    st.info("Inga transaktioner på detta konto för vald period.")

# ==================== RAPPORTER ====================
elif page == "📈 Rapporter":
    st.title("📈 Rapporter")
    
    periods = get_periods()
    
    if periods:
        # Period selector
        period_options = [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d} ({p.get('start_date')} - {p.get('end_date')})") 
                         for p in periods]
        selected_period = st.selectbox("Välj period", period_options, format_func=lambda x: x[1])
        
        if selected_period:
            period_id = selected_period[0]
            
            # Trial balance
            st.subheader("📊 Saldobalans (Råbalans)")
            tb = get_trial_balance(period_id)
            
            if tb and tb.get("rows"):
                df = pd.DataFrame([
                    {
                        "Konto": r.get("account_code"),
                        "Debet": format_currency(r.get("debit", 0)),
                        "Kredit": format_currency(r.get("credit", 0)),
                        "Saldo": format_currency(r.get("balance", 0))
                    }
                    for r in tb.get("rows", [])
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                total_debit = tb.get("total_debit", 0)
                total_credit = tb.get("total_credit", 0)
                balanced = "✅ Balanserad" if total_debit == total_credit else "⚠️ Obalanserad"
                st.caption(f"Summa Debet: {format_currency(total_debit)} | Summa Kredit: {format_currency(total_credit)} | {balanced}")
            else:
                st.info("Ingen data för vald period")
            
            # Resultaträkning (enkel)
            st.markdown("---")
            st.subheader("📊 Resultaträkning (förenklad)")
            
            if tb and tb.get("rows"):
                accounts = get_accounts()
                account_lookup = {a.get("code"): a for a in accounts}
                
                revenue_total = 0
                expense_total = 0
                
                for r in tb.get("rows", []):
                    code = r.get("account_code", "")
                    acc = account_lookup.get(code, {})
                    balance = r.get("balance", 0)
                    
                    if acc.get("account_type") == "revenue":
                        revenue_total += abs(balance)  # Revenue has credit balance (negative)
                    elif acc.get("account_type") == "expense":
                        expense_total += balance
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Intäkter", format_currency(revenue_total))
                with col2:
                    st.metric("Kostnader", format_currency(expense_total))
                with col3:
                    result = revenue_total - expense_total
                    st.metric("Resultat", format_currency(result), 
                             delta=f"{'Vinst' if result >= 0 else 'Förlust'}")
    else:
        st.info("Skapa räkenskapsperioder först")

# ==================== DEMO DATA ====================
elif page == "🎯 Demo Data":
    st.title("🎯 Demo Data Generator")
    
    st.write("Generera testdata för att visa hur systemet fungerar.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🚀 Snabbstart")
        if st.button("Generera all demo-data", type="primary"):
            with st.spinner("Genererar..."):
                try:
                    # Check if API has seed endpoint
                    resp = requests.post(f"{API_URL}/api/v1/agent/seed", headers=HEADERS)
                    if resp.status_code in [200, 201]:
                        st.success("✅ Demo-data genererad!")
                        st.balloons()
                    else:
                        st.warning("API seed endpoint inte tillgänglig. Kör main.py --seed manuellt.")
                except:
                    st.warning("Kunde inte anropa seed endpoint. Starta om containern med --seed flaggan.")
    
    with col2:
        st.subheader("📋 Manuell setup")
        
        with st.form("manual_setup"):
            company_name = st.text_input("Företagsnamn", "Demo AB")
            org_number = st.text_input("Org.nummer", "559123-4567")
            
            st.write("**Räkenskapsår**")
            fy_start = st.date_input("Start", date(2026, 1, 1))
            fy_end = st.date_input("Slut", date(2026, 12, 31))
            
            st.form_submit_button("Skapa", disabled=True)
            st.caption("(Kräver API-endpoints som inte finns än)")
    
    st.markdown("---")
    
    # Current data overview
    st.subheader("📊 Nuvarande data")
    
    col1, col2, col3 = st.columns(3)
    
    accounts = get_accounts()
    vouchers = get_vouchers()
    invoices = get_invoices()
    periods = get_periods()
    
    with col1:
        st.metric("Konton", len(accounts))
    with col2:
        st.metric("Verifikationer", len(vouchers))
    with col3:
        st.metric("Fakturor", len(invoices))
    
    # Sample data preview
    if accounts:
        with st.expander("Förhandsgranska konton"):
            st.json(accounts[:5])
    
    if vouchers:
        with st.expander("Förhandsgranska verifikationer"):
            st.json(vouchers[:3])
    
    # API Info
    st.markdown("---")
    st.subheader("🔗 API Info")
    
    try:
        resp = requests.get(f"{API_URL}/api/v1/agent/openapi", headers=HEADERS)
        if resp.status_code == 200:
            spec = resp.json()
            st.write(f"**Titel:** {spec.get('info', {}).get('title')}")
            st.write(f"**Version:** {spec.get('info', {}).get('version')}")
            st.write(f"**Endpoints:** {len(spec.get('paths', {}))}")
    except:
        st.info("API info inte tillgänglig")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("© 2026 Bokföringssystem\nByggt med Streamlit + FastAPI")
