"""Streamlit frontend för Bokföringssystem.

Kör med: streamlit run frontend/app.py
"""

import os
import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime
import json

# Sidkonfiguration
st.set_page_config(
    page_title="Bokföringssystem",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Anpassat tema via CSS
st.markdown("""
<style>
    .stMetric .metric-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
    }
    .audit-entry {
        border-left: 3px solid #4CAF50;
        padding: 8px 12px;
        margin: 6px 0;
        background-color: #f8f9fa;
        border-radius: 0 4px 4px 0;
    }
    .audit-action-created { border-left-color: #4CAF50; }
    .audit-action-posted { border-left-color: #2196F3; }
    .audit-action-updated { border-left-color: #FF9800; }
    .audit-action-corrected { border-left-color: #f44336; }
    .audit-action-deleted { border-left-color: #9E9E9E; }
    div[data-testid="stExpander"] details summary p {
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# API-konfiguration
DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")

API_URL = st.sidebar.text_input("API-adress", DEFAULT_API_URL)
API_KEY = st.sidebar.text_input("API-nyckel", DEFAULT_API_KEY, type="password")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# Kontrollera API-hälsa
def check_health():
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

# Sidnavigering
st.sidebar.title("📊 Bokföringssystem")
st.sidebar.markdown("---")

# Hälsokontroll
health = check_health()
if health:
    st.sidebar.success(f"✅ API ansluten (v{health.get('version', '?')})")
else:
    st.sidebar.error("❌ API offline")
    st.sidebar.info("Starta API:et med: `docker-compose up`")

page = st.sidebar.radio(
    "Navigering",
    ["🏠 Översikt", "📒 Kontoplan", "📝 Verifikationer", "📄 Fakturor", "📖 Huvudbok", "📈 Rapporter", "🎯 Demodata"]
)

# Hjälpfunktioner
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

def get_voucher_audit(voucher_id):
    """Hämta ändringshistorik för en verifikation."""
    try:
        resp = requests.get(f"{API_URL}/api/v1/vouchers/{voucher_id}/audit", headers=HEADERS)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def format_currency(amount_ore):
    """Formatera öre som SEK."""
    if amount_ore is None:
        return "0,00 kr"
    return f"{amount_ore / 100:,.2f} kr".replace(",", " ").replace(".", ",").rstrip()

def format_timestamp(ts_str):
    """Formatera ISO-tidsstämpel till läsbart format."""
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ts_str or "-"

def translate_action(action):
    """Översätt audit-action till svenska."""
    translations = {
        "created": "🆕 Skapad",
        "updated": "✏️ Ändrad",
        "posted": "✅ Bokförd",
        "sent": "📤 Skickad",
        "booked": "📚 Bokförd",
        "registered": "📝 Registrerad",
        "locked": "🔒 Låst",
        "deleted": "🗑️ Borttagen",
        "corrected": "🔄 Korrigerad",
    }
    return translations.get(action, action)

def translate_account_type(t):
    """Översätt kontotyp till svenska."""
    translations = {
        "asset": "Tillgång",
        "liability": "Skuld",
        "equity": "Eget kapital",
        "revenue": "Intäkt",
        "expense": "Kostnad",
        "vat_in": "Ingående moms",
        "vat_out": "Utgående moms",
    }
    return translations.get(t, t)

def translate_status(s):
    """Översätt status till svenska."""
    translations = {
        "draft": "Utkast",
        "posted": "Bokförd",
        "sent": "Skickad",
        "paid": "Betald",
        "partially_paid": "Delvis betald",
    }
    return translations.get(s, s)

def render_audit_history(voucher_id):
    """Visa ändringshistorik för en verifikation."""
    audit_data = get_voucher_audit(voucher_id)
    
    if not audit_data or not audit_data.get("entries"):
        st.info("Ingen ändringshistorik tillgänglig.")
        return
    
    entries = audit_data.get("entries", [])
    st.markdown(f"**{len(entries)} händelse(r) registrerade**")
    
    for entry in entries:
        action = entry.get("action", "")
        actor = entry.get("actor", "okänd")
        timestamp = format_timestamp(entry.get("timestamp"))
        payload = entry.get("payload") or {}
        
        # Visa händelse med styling
        action_text = translate_action(action)
        
        st.markdown(f"""
        <div class="audit-entry audit-action-{action}">
            <strong>{action_text}</strong> &nbsp;|&nbsp; 
            👤 <em>{actor}</em> &nbsp;|&nbsp; 
            🕐 <em>{timestamp}</em>
        </div>
        """, unsafe_allow_html=True)
        
        # Visa detaljer om payload finns
        if payload:
            with st.container():
                # Visa före/efter-värden
                if "before" in payload and "after" in payload:
                    col_before, col_after = st.columns(2)
                    with col_before:
                        st.markdown("**Före:**")
                        for key, val in payload["before"].items():
                            st.caption(f"  {key}: {val}")
                    with col_after:
                        st.markdown("**Efter:**")
                        for key, val in payload["after"].items():
                            st.caption(f"  {key}: {val}")
                elif "description" in payload:
                    st.caption(f"  Beskrivning: {payload['description']}")
                elif "rows" in payload:
                    st.caption(f"  Antal rader: {len(payload['rows'])}")
                else:
                    # Visa övrig payload
                    for key, val in payload.items():
                        if key not in ("id", "entity_type", "entity_id"):
                            st.caption(f"  {key}: {val}")

# ==================== ÖVERSIKT ====================
if page == "🏠 Översikt":
    st.title("🏠 Översikt")
    
    # Mätvärden
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
    
    # Senaste aktivitet
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📝 Senaste verifikationerna")
        if vouchers:
            recent = sorted(vouchers, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
            for v in recent:
                status_icon = "✅" if v.get("status") == "posted" else "📝"
                ver_nr = f"{v.get('series')}{v.get('number', 0):06d}"
                st.markdown(f"{status_icon} **{ver_nr}** - {v.get('description', 'Saknas')}")
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
                st.markdown(f"{icon} **{inv.get('invoice_number')}** - {inv.get('customer_name', 'Saknas')}")
                st.caption(f"{format_currency(inv.get('amount_inc_vat', 0))} | {translate_status(inv.get('status'))}")
        else:
            st.info("Inga fakturor")
    
    # Diagram
    st.markdown("---")
    st.subheader("📊 Omsättning över tid")
    
    if vouchers:
        monthly_data = {}
        for v in vouchers:
            if v.get("status") == "posted":
                month = v.get("date", "")[:7]
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
            st.info("Ingen bokförd omsättning ännu")
    else:
        st.info("Skapa verifikationer för att se statistik")

# ==================== KONTOPLAN ====================
elif page == "📒 Kontoplan":
    st.title("📒 Kontoplan (BAS 2026)")
    
    accounts = get_accounts()
    
    if accounts:
        # Filtrera efter typ
        account_types = ["Alla"] + sorted(list(set(a.get("account_type", "okänd") for a in accounts)))
        type_labels = {t: translate_account_type(t) for t in account_types if t != "Alla"}
        type_labels["Alla"] = "Alla"
        
        selected_type = st.selectbox("Filtrera efter typ", account_types, format_func=lambda x: type_labels.get(x, x))
        
        # Sök
        search = st.text_input("🔍 Sök konto", "")
        
        # Filtrera
        filtered = accounts
        if selected_type != "Alla":
            filtered = [a for a in filtered if a.get("account_type") == selected_type]
        if search:
            filtered = [a for a in filtered if search.lower() in a.get("name", "").lower() 
                       or search in a.get("code", "")]
        
        # Visa som tabell
        df = pd.DataFrame([
            {
                "Konto": a.get("code"),
                "Namn": a.get("name"),
                "Typ": translate_account_type(a.get("account_type")),
                "Aktiv": "✅" if a.get("active") else "❌"
            }
            for a in filtered
        ])
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Visar {len(filtered)} av {len(accounts)} konton")
        
        # Kontogrupper
        st.markdown("---")
        st.subheader("📊 Konton per typ")
        
        type_counts = {}
        for a in accounts:
            t = translate_account_type(a.get("account_type", "okänd"))
            type_counts[t] = type_counts.get(t, 0) + 1
        
        df_types = pd.DataFrame([
            {"Typ": k, "Antal": v}
            for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        ])
        st.bar_chart(df_types.set_index("Typ"))
    else:
        st.info("Inga konton hittades. Kör demodatagenerering.")

# ==================== VERIFIKATIONER ====================
elif page == "📝 Verifikationer":
    st.title("📝 Verifikationer")
    
    vouchers = get_vouchers()
    
    if vouchers:
        # Filter
        col1, col2 = st.columns(2)
        with col1:
            status_options = {"Alla": "Alla", "draft": "Utkast", "posted": "Bokförda"}
            status_filter = st.selectbox("Status", list(status_options.keys()), format_func=lambda x: status_options[x])
        with col2:
            series_filter = st.selectbox("Serie", ["Alla"] + sorted(list(set(v.get("series") for v in vouchers))))
        
        # Filtrera
        filtered = vouchers
        if status_filter != "Alla":
            filtered = [v for v in filtered if v.get("status") == status_filter]
        if series_filter != "Alla":
            filtered = [v for v in filtered if v.get("series") == series_filter]
        
        st.caption(f"Visar {len(filtered)} av {len(vouchers)} verifikationer")
        
        # Lista verifikationer
        for v in filtered:
            ver_nr = f"{v.get('series')}{v.get('number', 0):06d}"
            status_text = translate_status(v.get("status"))
            with st.expander(f"{ver_nr} — {v.get('description', 'Saknas')} ({v.get('date')}) [{status_text}]"):
                
                # Flikvy: Detaljer | Historik
                tab_details, tab_audit = st.tabs(["📋 Detaljer", "📜 Ändringshistorik"])
                
                with tab_details:
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col1:
                        status_color = "🟢" if v.get("status") == "posted" else "🟡"
                        st.write(f"{status_color} **Status:** {status_text}")
                    with col2:
                        st.write(f"**Datum:** {v.get('date')}")
                    with col3:
                        st.write(f"**Period:** {v.get('period_id', 'Saknas')[:8]}...")
                    
                    # Kontorader
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
                    balanced = "✅" if total_debit == total_credit else "⚠️ OBALANSERAD"
                    st.caption(f"**Summa:** Debet {format_currency(total_debit)} | Kredit {format_currency(total_credit)} {balanced}")
                    
                    if v.get("status") == "draft":
                        if st.button("✅ Bokför", key=f"post_{v.get('id')}"):
                            try:
                                resp = requests.post(
                                    f"{API_URL}/api/v1/vouchers/{v.get('id')}/post",
                                    headers=HEADERS
                                )
                                if resp.status_code == 200:
                                    st.success("✅ Bokförd!")
                                    st.rerun()
                                else:
                                    st.error(f"Fel vid bokföring: {resp.text}")
                            except Exception as e:
                                st.error(f"Anslutningsfel: {e}")
                
                with tab_audit:
                    st.markdown("### 📜 Ändringshistorik")
                    st.markdown("Alla ändringar av denna verifikation loggas enligt BFL krav på spårbarhet.")
                    render_audit_history(v.get("id"))
    else:
        st.info("Inga verifikationer hittades")
    
    # Skapa ny verifikation
    st.markdown("---")
    st.subheader("➕ Skapa ny verifikation")
    
    periods = get_periods()
    open_periods = [p for p in periods if not p.get("locked")]
    if open_periods:
        with st.form("new_voucher"):
            series = st.selectbox("Serie", ["A", "B"])
            voucher_date = st.date_input("Datum", date.today())
            period_options = [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d}") for p in open_periods]
            period = st.selectbox("Period", period_options, format_func=lambda x: x[1])
            description = st.text_input("Beskrivning")
            
            st.write("**Kontorader**")
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
            with col1:
                account = st.text_input("Konto", value="1510", key="row1_acc")
            with col2:
                row_desc = st.text_input("Beskrivning", value="", key="row1_desc")
            with col3:
                debit = st.number_input("Debet (öre)", value=0, step=100, key="row1_deb")
            with col4:
                credit = st.number_input("Kredit (öre)", value=10000, step=100, key="row1_cred")
            
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
            with col1:
                account2 = st.text_input("Konto", value="3011", key="row2_acc")
            with col2:
                row_desc2 = st.text_input("Beskrivning", value="", key="row2_desc")
            with col3:
                debit2 = st.number_input("Debet (öre)", value=10000, step=100, key="row2_deb")
            with col4:
                credit2 = st.number_input("Kredit (öre)", value=0, step=100, key="row2_cred")
            
            auto_post = st.checkbox("Bokför direkt", value=False)
            
            submitted = st.form_submit_button("🆕 Skapa verifikation")
            
            if submitted:
                if not description:
                    st.error("Beskrivning krävs.")
                else:
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
                        st.error(f"Anslutningsfel: {e}")
    else:
        st.warning("Inga öppna perioder. Skapa en räkenskapsperiod först (använd Demodata).")

# ==================== FAKTUROR ====================
elif page == "📄 Fakturor":
    st.title("📄 Fakturahantering")
    
    invoices = get_invoices()
    
    if invoices:
        # Sammanfattning
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
            st.metric("Summa", format_currency(sum(inv.get("amount_inc_vat", 0) for inv in invoices)))
        
        st.markdown("---")
        
        # Fakturalista
        status_options = {"Alla": "Alla", "draft": "Utkast", "sent": "Skickade", "partially_paid": "Delvis betalda", "paid": "Betalda"}
        status_filter = st.selectbox("Filtrera status", list(status_options.keys()), format_func=lambda x: status_options[x])
        
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
            
            with st.expander(f"{icon} {inv.get('invoice_number')} — {inv.get('customer_name', 'Saknas')} [{translate_status(inv.get('status'))}]"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Kund:** {inv.get('customer_name')}")
                    st.write(f"**E-post:** {inv.get('customer_email', 'Saknas')}")
                with col2:
                    st.write(f"**Fakturadatum:** {inv.get('invoice_date')}")
                    st.write(f"**Förfallodatum:** {inv.get('due_date')}")
                with col3:
                    st.write(f"**Status:** {translate_status(inv.get('status'))}")
                    st.write(f"**Belopp exkl. moms:** {format_currency(inv.get('amount_ex_vat', 0))}")
                    st.write(f"**Moms:** {format_currency(inv.get('vat_amount', 0))}")
                    st.write(f"**Summa inkl. moms:** {format_currency(inv.get('amount_inc_vat', 0))}")
                
                # Fakturarader
                st.write("**Rader:**")
                rows_data = []
                for r in inv.get("rows", []):
                    rows_data.append({
                        "Beskrivning": r.get("description"),
                        "Antal": r.get("quantity"),
                        "À-pris": format_currency(r.get("unit_price", 0)),
                        "Momskod": r.get("vat_code"),
                        "Summa": format_currency(r.get("row_total_ex_vat", 0))
                    })
                if rows_data:
                    st.table(pd.DataFrame(rows_data))
                
                # Betalningar
                payments = inv.get("payments", [])
                if payments:
                    st.write(f"**Betalningar ({len(payments)}):**")
                    for p in payments:
                        st.caption(f"{p.get('payment_date')}: {format_currency(p.get('amount', 0))} ({p.get('payment_method')})")
                
                # Åtgärder
                if inv.get("status") == "draft":
                    if st.button("📤 Skicka faktura", key=f"send_{inv.get('id')}"):
                        try:
                            resp = requests.post(
                                f"{API_URL}/api/v1/invoices/{inv.get('id')}/send",
                                headers=HEADERS
                            )
                            if resp.status_code == 200:
                                st.success("✅ Faktura skickad!")
                                st.rerun()
                            else:
                                st.error(f"Fel: {resp.text}")
                        except Exception as e:
                            st.error(f"Anslutningsfel: {e}")
                
                elif inv.get("status") in ["sent", "partially_paid"]:
                    with st.form(f"payment_{inv.get('id')}"):
                        st.write("**Registrera betalning**")
                        pay_amount = st.number_input("Belopp (öre)", 
                                                    value=inv.get("remaining_amount", inv.get("amount_inc_vat")),
                                                    step=100)
                        pay_date = st.date_input("Betalningsdatum", date.today())
                        pay_methods = {"bank_transfer": "Banköverföring", "card": "Kort", "cash": "Kontant", "swish": "Swish"}
                        pay_method = st.selectbox("Betalningsmetod", list(pay_methods.keys()), format_func=lambda x: pay_methods[x])
                        
                        if st.form_submit_button("💰 Registrera betalning"):
                            try:
                                resp = requests.post(
                                    f"{API_URL}/api/v1/invoices/{inv.get('id')}/payment",
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
                                st.error(f"Anslutningsfel: {e}")
    else:
        st.info("Inga fakturor hittades")
    
    # Skapa faktura
    st.markdown("---")
    st.subheader("➕ Skapa ny faktura")
    
    with st.form("new_invoice"):
        customer_name = st.text_input("Kundnamn")
        customer_email = st.text_input("E-post (valfritt)")
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
                price = st.number_input(f"Pris (öre)", value=0, step=1000, key=f"inv_row_{i}_price")
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
        
        submit = st.form_submit_button("🆕 Skapa faktura")
        
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
                st.error(f"Anslutningsfel: {e}")
        elif submit and not customer_name:
            st.error("Kundnamn krävs.")

# ==================== HUVUDBOK ====================
elif page == "📖 Huvudbok":
    st.title("📖 Huvudbok")
    
    accounts = get_accounts()
    periods = get_periods()
    
    if not accounts:
        st.info("Inga konton hittades. Kör demodatagenerering först.")
    elif not periods:
        st.info("Inga perioder hittades. Skapa ett räkenskapsår först.")
    else:
        # Periodväljare
        period_options = [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d}") for p in periods]
        selected_period = st.selectbox("Välj period", period_options, format_func=lambda x: x[1])
        
        if selected_period:
            period_id = selected_period[0]
            
            # Hämta saldobalans
            tb = get_trial_balance(period_id)
            
            st.subheader("💰 Kontosaldon")
            
            if tb and tb.get("rows"):
                tb_rows = tb.get("rows", [])
                account_lookup = {a.get("code"): a for a in accounts}
                
                overview_data = []
                for r in tb_rows:
                    code = r.get("account_code", "")
                    acc_info = account_lookup.get(code, {})
                    balance = r.get("balance", 0)
                    overview_data.append({
                        "Konto": code,
                        "Namn": acc_info.get("name", ""),
                        "Typ": translate_account_type(acc_info.get("account_type", "")),
                        "Debet": format_currency(r.get("debit", 0)),
                        "Kredit": format_currency(r.get("credit", 0)),
                        "Saldo": format_currency(balance),
                        "_balance_raw": balance,
                        "_type_raw": acc_info.get("account_type", ""),
                    })
                
                df_overview = pd.DataFrame(overview_data)
                
                # Sammanfattning per kontotyp
                col1, col2, col3, col4 = st.columns(4)
                type_sums = {}
                for row in overview_data:
                    t = row["_type_raw"]
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
                
                # Filtrera
                type_filter_options = {"Alla": "Alla", "asset": "Tillgångar", "liability": "Skulder", "equity": "Eget kapital", "revenue": "Intäkter", "expense": "Kostnader"}
                type_filter = st.selectbox("Filtrera kontotyp", list(type_filter_options.keys()), format_func=lambda x: type_filter_options[x])
                
                display_df = df_overview.drop(columns=["_balance_raw", "_type_raw"])
                if type_filter != "Alla":
                    display_df = display_df[df_overview["_type_raw"] == type_filter]
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen bokförd data för vald period.")
            
            # Kontoutdrag
            st.markdown("---")
            st.subheader("📋 Kontoutdrag")
            
            account_options = [(a.get("code"), f"{a.get('code')} — {a.get('name')}") for a in accounts]
            selected_account = st.selectbox(
                "Välj konto för detaljvy",
                account_options,
                format_func=lambda x: x[1]
            )
            
            if selected_account:
                ledger_data = get_account_ledger(selected_account[0], period_id)
                
                if ledger_data and ledger_data.get("rows"):
                    st.write(f"**Konto:** {ledger_data.get('account_code')} — {ledger_data.get('account_name')}")
                    
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
    fiscal_years = get_fiscal_years()
    
    if periods:
        # Val av rapportomfång
        report_scope = st.radio(
            "Rapportomfång",
            ["📅 Enskild period", "📆 Hela räkenskapsåret"],
            horizontal=True
        )
        
        if report_scope == "📅 Enskild period":
            # Periodväljare
            period_options = [(p.get("id"), f"{p.get('year')}-{p.get('month'):02d} ({p.get('start_date')} — {p.get('end_date')})") 
                             for p in periods]
            selected_period = st.selectbox("Välj period", period_options, format_func=lambda x: x[1])
            
            if selected_period:
                period_id = selected_period[0]
                
                # Saldobalans
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
                    st.caption(f"Summa debet: {format_currency(total_debit)} | Summa kredit: {format_currency(total_credit)} | {balanced}")
                else:
                    st.info("Ingen data för vald period")
                
                # Resultaträkning
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
                            revenue_total += abs(balance)
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
            # Helårsrapport
            st.subheader("📆 Helårsrapport")
            
            # Gruppera perioder per år
            years_available = sorted(set(p.get("year") for p in periods), reverse=True)
            
            if years_available:
                selected_year = st.selectbox("Välj räkenskapsår", years_available, format_func=lambda y: f"Hela året {y}")
                
                year_periods = [p for p in periods if p.get("year") == selected_year]
                
                if year_periods:
                    st.info(f"Sammanställer data för {len(year_periods)} perioder under {selected_year}")
                    
                    # Aggregera saldobalans för alla perioder under året
                    accounts = get_accounts()
                    account_lookup = {a.get("code"): a for a in accounts}
                    
                    yearly_totals = {}  # account_code -> {debit, credit, balance}
                    
                    progress_bar = st.progress(0, text="Hämtar perioddata...")
                    for idx, period in enumerate(year_periods):
                        pid = period.get("id")
                        tb = get_trial_balance(pid)
                        if tb and tb.get("rows"):
                            for r in tb.get("rows", []):
                                code = r.get("account_code", "")
                                if code not in yearly_totals:
                                    yearly_totals[code] = {"debit": 0, "credit": 0, "balance": 0}
                                yearly_totals[code]["debit"] += r.get("debit", 0)
                                yearly_totals[code]["credit"] += r.get("credit", 0)
                                yearly_totals[code]["balance"] += r.get("balance", 0)
                        progress_bar.progress((idx + 1) / len(year_periods), text=f"Period {idx+1}/{len(year_periods)}...")
                    
                    progress_bar.empty()
                    
                    if yearly_totals:
                        # Sammanfattning per kontotyp
                        st.subheader(f"💰 Årssaldon {selected_year}")
                        
                        type_sums = {}
                        for code, totals in yearly_totals.items():
                            acc = account_lookup.get(code, {})
                            acc_type = acc.get("account_type", "unknown")
                            type_sums[acc_type] = type_sums.get(acc_type, 0) + totals["balance"]
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("🏦 Tillgångar", format_currency(type_sums.get("asset", 0)))
                        with col2:
                            st.metric("💳 Skulder", format_currency(type_sums.get("liability", 0)))
                        with col3:
                            st.metric("📈 Intäkter", format_currency(abs(type_sums.get("revenue", 0))))
                        with col4:
                            st.metric("📉 Kostnader", format_currency(type_sums.get("expense", 0)))
                        
                        # Resultaträkning
                        st.markdown("---")
                        st.subheader(f"📊 Resultaträkning {selected_year}")
                        
                        revenue_total = abs(type_sums.get("revenue", 0))
                        expense_total = type_sums.get("expense", 0)
                        result = revenue_total - expense_total
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Intäkter", format_currency(revenue_total))
                        with col2:
                            st.metric("Kostnader", format_currency(expense_total))
                        with col3:
                            st.metric("Resultat", format_currency(result),
                                     delta=f"{'Vinst' if result >= 0 else 'Förlust'}")
                        
                        # Detaljerad tabell
                        st.markdown("---")
                        st.subheader(f"📋 Saldobalans helår {selected_year}")
                        
                        type_filter_options = {"Alla": "Alla", "asset": "Tillgångar", "liability": "Skulder", "equity": "Eget kapital", "revenue": "Intäkter", "expense": "Kostnader"}
                        type_filter = st.selectbox("Filtrera kontotyp", list(type_filter_options.keys()), format_func=lambda x: type_filter_options[x])
                        
                        yearly_rows = []
                        for code in sorted(yearly_totals.keys()):
                            totals = yearly_totals[code]
                            acc = account_lookup.get(code, {})
                            acc_type = acc.get("account_type", "unknown")
                            
                            if type_filter != "Alla" and acc_type != type_filter:
                                continue
                            
                            yearly_rows.append({
                                "Konto": code,
                                "Namn": acc.get("name", ""),
                                "Typ": translate_account_type(acc_type),
                                "Debet": format_currency(totals["debit"]),
                                "Kredit": format_currency(totals["credit"]),
                                "Årssaldo": format_currency(totals["balance"]),
                            })
                        
                        if yearly_rows:
                            df_yearly = pd.DataFrame(yearly_rows)
                            st.dataframe(df_yearly, use_container_width=True, hide_index=True)
                        
                        total_debit = sum(t["debit"] for t in yearly_totals.values())
                        total_credit = sum(t["credit"] for t in yearly_totals.values())
                        st.caption(f"Summa debet: {format_currency(total_debit)} | Summa kredit: {format_currency(total_credit)}")
                        
                        # Månadsvis jämförelse
                        st.markdown("---")
                        st.subheader(f"📈 Månadsvis intäkter/kostnader {selected_year}")
                        
                        monthly_summary = []
                        for period in sorted(year_periods, key=lambda p: p.get("month", 0)):
                            pid = period.get("id")
                            tb = get_trial_balance(pid)
                            month_rev = 0
                            month_exp = 0
                            if tb and tb.get("rows"):
                                for r in tb.get("rows", []):
                                    code = r.get("account_code", "")
                                    acc = account_lookup.get(code, {})
                                    if acc.get("account_type") == "revenue":
                                        month_rev += abs(r.get("balance", 0))
                                    elif acc.get("account_type") == "expense":
                                        month_exp += r.get("balance", 0)
                            
                            monthly_summary.append({
                                "Månad": f"{selected_year}-{period.get('month', 0):02d}",
                                "Intäkter (kr)": month_rev / 100,
                                "Kostnader (kr)": month_exp / 100,
                            })
                        
                        if monthly_summary:
                            df_monthly = pd.DataFrame(monthly_summary)
                            st.bar_chart(df_monthly.set_index("Månad"))
                    else:
                        st.info(f"Ingen bokförd data hittades för {selected_year}")
            else:
                st.info("Inga räkenskapsår hittades")
    else:
        st.info("Skapa räkenskapsperioder först")

# ==================== DEMODATA ====================
elif page == "🎯 Demodata":
    st.title("🎯 Demodatagenerator")
    
    st.write("Generera testdata för att visa hur systemet fungerar.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🚀 Snabbstart")
        if st.button("Generera all demodata", type="primary"):
            with st.spinner("Genererar demodata..."):
                try:
                    resp = requests.post(f"{API_URL}/api/v1/agent/seed", headers=HEADERS)
                    if resp.status_code in [200, 201]:
                        st.success("✅ Demodata genererad!")
                        st.balloons()
                    else:
                        st.warning("API seed-endpoint inte tillgänglig. Kör main.py --seed manuellt.")
                except:
                    st.warning("Kunde inte anropa seed-endpoint. Starta om containern med --seed-flaggan.")
    
    with col2:
        st.subheader("📋 Manuell installation")
        
        with st.form("manual_setup"):
            company_name = st.text_input("Företagsnamn", "Demo AB")
            org_number = st.text_input("Organisationsnummer", "559123-4567")
            
            st.write("**Räkenskapsår**")
            fy_start = st.date_input("Startdatum", date(2026, 1, 1))
            fy_end = st.date_input("Slutdatum", date(2026, 12, 31))
            
            st.form_submit_button("Skapa", disabled=True)
            st.caption("(Kräver API-endpoints som inte finns ännu)")
    
    st.markdown("---")
    
    # Nuvarande data
    st.subheader("📊 Befintlig data")
    
    col1, col2, col3 = st.columns(3)
    
    accounts = get_accounts()
    vouchers = get_vouchers()
    invoices = get_invoices()
    
    with col1:
        st.metric("Konton", len(accounts))
    with col2:
        st.metric("Verifikationer", len(vouchers))
    with col3:
        st.metric("Fakturor", len(invoices))
    
    if accounts:
        with st.expander("Förhandsgranskning — konton"):
            st.json(accounts[:5])
    
    if vouchers:
        with st.expander("Förhandsgranskning — verifikationer"):
            st.json(vouchers[:3])
    
    # API-info
    st.markdown("---")
    st.subheader("🔗 API-information")
    
    try:
        resp = requests.get(f"{API_URL}/api/v1/agent/spec/openapi", headers=HEADERS)
        if resp.status_code == 200:
            spec = resp.json()
            st.write(f"**Titel:** {spec.get('info', {}).get('title')}")
            st.write(f"**Version:** {spec.get('info', {}).get('version')}")
            st.write(f"**Endpoints:** {len(spec.get('paths', {}))}")
    except:
        st.info("API-information inte tillgänglig")

# Sidfot
st.sidebar.markdown("---")
st.sidebar.caption("© 2026 Bokföringssystem\nByggt med Streamlit + FastAPI")
