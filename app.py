import os
import io
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

# --------- Backend mode: SQLite (default) or Neon PostgreSQL (if secret set) ---------
NEON_URL = None
try:
    NEON_URL = st.secrets.get("DATABASE_URL", None)
except Exception:
    NEON_URL = None

if not NEON_URL:
    NEON_URL = os.environ.get("DATABASE_URL")

USE_NEON = bool(NEON_URL)

DB_PATH = "nps_accounting.db"
INVOICE_BASE_DIR = os.path.join(os.getcwd(), "invoices")


# ========= DB HELPERS =========


class NeonCompatCursor:
    """Cursor wrapper to allow using '?' placeholders with psycopg2 ('%s')."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        if params is not None:
            sql = sql.replace("?", "%s")
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def executemany(self, sql, seq_of_params):
        sql = sql.replace("?", "%s")
        self._cursor.executemany(sql, seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class NeonCompatConnection:
    """Connection wrapper so pandas.read_sql_query etc. still work."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return NeonCompatCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _connect_neon():
    """Return a NeonCompatConnection using psycopg2 and NEON_URL."""
    import psycopg2

    if not NEON_URL:
        raise RuntimeError("NEON_URL is not configured.")
    raw_conn = psycopg2.connect(NEON_URL)
    return NeonCompatConnection(raw_conn)


def get_conn():
    """Return a DB connection.

    - Default / local: SQLite (nps_accounting.db)
    - If USE_NEON and DATABASE_URL provided: Neon PostgreSQL via psycopg2
    """
    if USE_NEON and NEON_URL:
        try:
            return _connect_neon()
        except Exception as e:
            st.error("❌ Failed to connect to Neon database.")
            st.error(str(e))
            raise

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(INVOICE_BASE_DIR, exist_ok=True)

    # If using Neon, just test connection; assume schema created via migrations.
    if USE_NEON and NEON_URL:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            conn.close()
            st.session_state["db_ready"] = True
        except Exception as e:
            st.error("❌ Failed to connect to Neon DB in init_db.")
            st.error(str(e))
            st.session_state["db_ready"] = False
        return

    # SQLite local DB: create tables if not exist (original behavior)
    conn = get_conn()
    cur = conn.cursor()

    # Projects
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_code TEXT UNIQUE,
            name TEXT,
            client_name TEXT,
            location TEXT,
            contract_value REAL DEFAULT 0,
            start_date TEXT,
            status TEXT,
            project_type TEXT DEFAULT 'Other'
        )
        """
    )

    # Cash book
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cash_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            project_code TEXT,
            description TEXT,
            method TEXT,
            ref_no TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            remarks TEXT
        )
        """
    )

    # Invoices
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            date TEXT,
            project_code TEXT,
            client_name TEXT,
            description TEXT,
            amount REAL,
            status TEXT,
            remarks TEXT
        )
        """
    )

    # Debts & Fixed Assets
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS debts_fixed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,               -- 'Debt' or 'Fixed Asset'
            name TEXT,
            project_code TEXT,
            amount REAL,
            start_date TEXT,
            remarks TEXT
        )
        """
    )

    # People (summary, not full HR)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            position TEXT,
            project_code TEXT,
            basic_salary REAL,
            allowance REAL,
            is_active INTEGER DEFAULT 1
        )
        """
    )

    # Visas
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS visas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            visa_no TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            cost REAL,
            project_code TEXT
        )
        """
    )

    # Tickets
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            from_city TEXT,
            to_city TEXT,
            travel_date TEXT,
            cost REAL,
            project_code TEXT
        )
        """
    )

    # Accounts (chart of accounts)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            type TEXT
        )
        """
    )

    # Journal entries
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            account_code TEXT,
            description TEXT,
            debit REAL,
            credit REAL,
            ref TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ========= UI THEME & HELPERS =========


def inject_global_css():
    st.markdown(
        """
        <style>
        .main {
            background-color: #0f172a;
        }
        .nps-card {
            background-color: #020617;
            border-radius: 0.75rem;
            padding: 1rem 1.25rem;
            border: 1px solid #1e293b;
            box-shadow: 0 10px 30px rgba(15,23,42,0.6);
        }
        .nps-main-card {
            background-color: #020617;
            border-radius: 1rem;
            padding: 1.5rem;
            border: 1px solid #1e293b;
        }
        .stMetric {
            background-color: #020617 !important;
            border-radius: 0.75rem !important;
            padding: 0.75rem !important;
            border: 1px solid #1e293b !important;
        }
        .stMetric label {
            color: #94a3b8 !important;
        }
        .stMetric span {
            color: #e5e7eb !important;
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1350px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def nps_page_header(title: str, subtitle: str, icon: str = "💼"):
    st.markdown(
        f"""
        <div style="margin-bottom: 1rem;">
            <h1 style="color:#e5e7eb; margin-bottom:0.2rem;">{icon} {title}</h1>
            <p style="color:#9ca3af;">{subtitle}</p>
            <hr style="border: 1px solid #1f2933; margin-top:0.75rem;" />
        </div>
        """,
        unsafe_allow_html=True,
    )


# ========= UTILITIES =========


def df_from_query(sql: str, params: tuple = ()):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def save_invoice_file(project_code: str, invoice_no: str, file: io.BytesIO, filename: str):
    if not project_code:
        project_code = "GENERAL"

    proj_dir = os.path.join(INVOICE_BASE_DIR, project_code)
    os.makedirs(proj_dir, exist_ok=True)

    base, ext = os.path.splitext(filename)
    safe_invoice = invoice_no.replace("/", "-").replace("\\", "-")
    new_name = f"INV_{safe_invoice}{ext}"
    file_path = os.path.join(proj_dir, new_name)

    with open(file_path, "wb") as f:
        f.write(file.read())

    return file_path


# ========= PAGES =========
# 1) Modern Dashboard
# 2) Owners Dashboard (profit per project + top 5)
# 3) Project Dashboard
# ... rest of pages (cash, projects, invoices, etc.)


def page_dashboard():
    nps_page_header("NPS Accounting Dashboard", "FM & MEP Financial Overview", "📊")

    # ---- Load core data ----
    inv_df = df_from_query("SELECT * FROM invoices")
    cash_df = df_from_query("SELECT * FROM cash_book")
    debts_df = df_from_query("SELECT * FROM debts_fixed")

    # ---- Basic totals ----
    total_invoices = inv_df["amount"].sum() if not inv_df.empty else 0.0
    total_debit = cash_df["debit"].sum() if not cash_df.empty else 0.0  # Cash IN
    total_credit = cash_df["credit"].sum() if not cash_df.empty else 0.0  # Cash OUT
    net_cash = total_debit - total_credit

    total_debts = (
        debts_df.loc[debts_df["type"] == "Debt", "amount"].sum() if not debts_df.empty else 0.0
    )
    total_assets = (
        debts_df.loc[debts_df["type"] == "Fixed Asset", "amount"].sum()
        if not debts_df.empty
        else 0.0
    )

    # ---- Ratios ----
    if total_assets > 0:
        debt_to_assets = total_debts / total_assets
    else:
        debt_to_assets = None

    if total_debts > 0:
        cash_coverage = net_cash / total_debts
    else:
        cash_coverage = None

    collection_ratio = None
    if not inv_df.empty and "status" in inv_df.columns:
        paid_mask = inv_df["status"].astype(str).str.lower().eq("paid")
        paid_amount = inv_df.loc[paid_mask, "amount"].sum()
        if total_invoices > 0:
            collection_ratio = (paid_amount / total_invoices) * 100

    # ------------------------------------------------------------------
    # 🎛️ TOP KPI ROW – modern cards with icons
    # ------------------------------------------------------------------
    st.markdown("### 💼 Key Financial Snapshot")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("💸 Total Invoices", f"{total_invoices:,.0f} IQD")
    with k2:
        st.metric("💰 Net Cash Balance", f"{net_cash:,.0f} IQD")
    with k3:
        st.metric("📉 Total Debts", f"{total_debts:,.0f} IQD")
    with k4:
        st.metric("🏗 Fixed Assets", f"{total_assets:,.0f} IQD")

    # ------------------------------------------------------------------
    # 📊 Ratios row
    # ------------------------------------------------------------------
    st.markdown("### 📊 Ratios & Coverage")

    r1, r2, r3 = st.columns(3)

    with r1:
        if debt_to_assets is not None:
            st.metric("⚖️ Debt / Assets", f"{debt_to_assets:,.2f}x")
        else:
            st.metric("⚖️ Debt / Assets", "N/A")

    with r2:
        if cash_coverage is not None:
            st.metric("🧯 Cash Coverage of Debts", f"{cash_coverage:,.2f}x")
        else:
            st.metric("🧯 Cash Coverage of Debts", "N/A")

    with r3:
        if collection_ratio is not None:
            st.metric("📈 Collection Ratio", f"{collection_ratio:,.1f}%")
        else:
            st.metric("📈 Collection Ratio", "N/A")

    # ------------------------------------------------------------------
    # 🚨 Alerts section
    # ------------------------------------------------------------------
    st.markdown("### 🚨 Alerts & Warnings")

    any_alert = False

    if net_cash < 0:
        any_alert = True
        st.error("🔴 Net cash is **negative** – راجع الصرف والالتزامات النقدية.")
    elif net_cash < total_debts and total_debts > 0:
        any_alert = True
        st.warning("🟠 Net cash أقل من إجمالي الديون – راجع خطة التحصيل وسداد الالتزامات.")

    if debt_to_assets is not None and debt_to_assets > 1.0:
        any_alert = True
        st.warning("🟠 Debt/Assets ratio > 1 – الديون أعلى من قيمة الأصول الثابتة.")

    if collection_ratio is not None and collection_ratio < 70:
        any_alert = True
        st.warning(
            "🟠 Collection ratio أقل من 70% – معدل تحصيل الفواتير ضعيف، راجع الذمم المدينة."
        )

    if not any_alert:
        st.success("✅ No major alerts detected – الوضع المالي مستقر حاليًا.")

    st.markdown("---")

    # ------------------------------------------------------------------
    # 📉 Monthly cash trend + recent activity
    # ------------------------------------------------------------------
    st.markdown("### 📉 Monthly Cash Trend & Recent Activity")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        if cash_df.empty:
            st.info("No cash movements yet to display trend.")
        else:
            cash_df_plot = cash_df.copy()
            cash_df_plot["date"] = pd.to_datetime(cash_df_plot["date"])
            cash_df_plot = (
                cash_df_plot.groupby(pd.Grouper(key="date", freq="M"))[["debit", "credit"]]
                .sum()
                .reset_index()
            )
            cash_df_plot["month"] = cash_df_plot["date"].dt.to_period("M").astype(str)
            cash_df_plot = cash_df_plot[["month", "debit", "credit"]]

            st.markdown("**📆 Monthly Cash In / Out**")
            st.bar_chart(
                cash_df_plot.set_index("month")[["debit", "credit"]],
                use_container_width=True,
            )

    with col_right:
        st.markdown("**🧾 Recent Invoices (Last 10)**")
        if inv_df.empty:
            st.info("No invoices yet.")
        else:
            inv_view = inv_df.copy()
            inv_view["date"] = pd.to_datetime(inv_view["date"]).dt.date
            st.dataframe(
                inv_view.sort_values("date", ascending=False).head(10),
                use_container_width=True,
            )

        st.markdown("**💵 Recent Cash Movements (Last 10)**")
        if cash_df.empty:
            st.info("No cash entries yet.")
        else:
            cash_view = cash_df.copy()
            cash_view["date"] = pd.to_datetime(cash_view["date"]).dt.date
            st.dataframe(
                cash_view.sort_values("date", ascending=False).head(10),
                use_container_width=True,
            )


def page_owners_dashboard():
    """High-level dashboard for owners: profit per project, top projects, and key ratios."""
    nps_page_header("Owners Dashboard", "High-level performance for company owners", "👑")

    proj_df = df_from_query(
        "SELECT project_code, name, client_name, contract_value, status FROM projects"
    )
    inv_df = df_from_query("SELECT project_code, amount, status FROM invoices")
    cash_df = df_from_query("SELECT project_code, debit, credit FROM cash_book")
    debts_df = df_from_query("SELECT project_code, type, amount FROM debts_fixed")

    if proj_df.empty and inv_df.empty and cash_df.empty and debts_df.empty:
        st.info("No financial data yet. Add some projects, invoices and cash entries first.")
        return

    codes = set()
    for df, col in [
        (proj_df, "project_code"),
        (inv_df, "project_code"),
        (cash_df, "project_code"),
        (debts_df, "project_code"),
    ]:
        if not df.empty and col in df.columns:
            codes.update(df[col].dropna().astype(str).tolist())

    if not codes:
        st.info("No project codes found yet.")
        return

    summary = pd.DataFrame(sorted(codes), columns=["project_code"])

    if not inv_df.empty:
        inv_grp = (
            inv_df.groupby("project_code")["amount"]
            .sum()
            .rename("revenue")
            .reset_index()
        )
        summary = summary.merge(inv_grp, on="project_code", how="left")
    else:
        summary["revenue"] = 0.0

    if not cash_df.empty:
        cash_grp = (
            cash_df.groupby("project_code")[["debit", "credit"]]
            .sum()
            .reset_index()
            .rename(columns={"debit": "cash_in", "credit": "cash_out"})
        )
        summary = summary.merge(cash_grp, on="project_code", how="left")
    else:
        summary["cash_in"] = 0.0
        summary["cash_out"] = 0.0

    if not debts_df.empty:
        debt_grp = (
            debts_df[debts_df["type"] == "Debt"]
            .groupby("project_code")["amount"]
            .sum()
            .rename("debts")
            .reset_index()
        )
        asset_grp = (
            debts_df["type"]
            .eq("Fixed Asset")
            .groupby(debts_df["project_code"])
            .sum()
            .rename("assets")
            .reset_index()
        )
        # Better: recompute assets properly
        asset_grp = (
            debts_df[debts_df["type"] == "Fixed Asset"]
            .groupby("project_code")["amount"]
            .sum()
            .rename("assets")
            .reset_index()
        )
        summary = summary.merge(debt_grp, on="project_code", how="left")
        summary = summary.merge(asset_grp, on="project_code", how="left")
    else:
        summary["debts"] = 0.0
        summary["assets"] = 0.0

    if not proj_df.empty:
        proj_info = proj_df[["project_code", "name", "client_name", "contract_value", "status"]]
        summary = summary.merge(proj_info, on="project_code", how="left")

    for col in ["revenue", "cash_in", "cash_out", "debts", "assets", "contract_value"]:
        if col in summary.columns:
            summary[col] = summary[col].fillna(0.0)

    summary["net_cash"] = summary["cash_in"] - summary["cash_out"]
    summary["est_profit"] = summary["revenue"] - summary["cash_out"]

    def safe_margin(row):
        rev = row.get("revenue", 0)
        prof = row.get("est_profit", 0)
        if rev and rev != 0:
            return (prof / rev) * 100.0
        return None

    summary["profit_margin_%"] = summary.apply(safe_margin, axis=1)

    total_revenue = float(summary["revenue"].sum())
    total_profit = float(summary["est_profit"].sum())
    total_debts = float(summary["debts"].sum())
    total_assets = float(summary["assets"].sum())
    total_projects = len(summary)

    if total_revenue > 0:
        overall_margin = (total_profit / total_revenue) * 100.0
    else:
        overall_margin = None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💸 Total Revenue (Invoices)", f"{total_revenue:,.0f} IQD")
    with c2:
        st.metric("💰 Estimated Profit", f"{total_profit:,.0f} IQD")
    with c3:
        st.metric("🏗 Projects (All)", total_projects)
    with c4:
        if overall_margin is not None:
            st.metric("📈 Overall Profit Margin", f"{overall_margin:,.1f}%")
        else:
            st.metric("📈 Overall Profit Margin", "N/A")

    r1, r2, r3 = st.columns(3)
    with r1:
        if total_assets > 0:
            st.metric("⚖️ Debt / Assets", f"{(total_debts / total_assets):,.2f}x")
        else:
            st.metric("⚖️ Debt / Assets", "N/A")
    with r2:
        if total_debts > 0:
            st.metric(
                "🧯 Cash Coverage (Net Cash / Debts)",
                f"{(summary['net_cash'].sum() / total_debts):,.2f}x",
            )
        else:
            st.metric("🧯 Cash Coverage", "N/A")
    with r3:
        st.metric("📉 Total Debts", f"{total_debts:,.0f} IQD")

    st.markdown("---")

    st.markdown("### 🏆 Top 5 Projects by Estimated Profit")
    top_profit = summary.sort_values("est_profit", ascending=False).head(5).copy()

    if top_profit.empty:
        st.info("No projects with revenue/cost data yet.")
    else:
        top_profit_display = top_profit[
            [
                "project_code",
                "name",
                "client_name",
                "revenue",
                "cash_out",
                "est_profit",
                "profit_margin_%"
            ]
        ]
        top_profit_display["profit_margin_%"] = top_profit_display["profit_margin_%"].round(1)
        st.dataframe(top_profit_display, use_container_width=True)

        chart_df = top_profit.set_index("project_code")["est_profit"]
        st.bar_chart(chart_df, use_container_width=True)

    st.markdown("---")

    st.markdown("### 💼 Top 5 Projects by Revenue")
    top_rev = summary.sort_values("revenue", ascending=False).head(5).copy()

    if top_rev.empty:
        st.info("No invoices yet.")
    else:
        top_rev_display = top_rev[
            [
                "project_code",
                "name",
                "client_name",
                "revenue",
                "cash_out",
                "est_profit",
            ]
        ]
        st.dataframe(top_rev_display, use_container_width=True)


# ------- (هنا باقي صفحاتك الأصلية: page_project_dashboard, page_cash, page_projects,
#          page_invoices, page_debts_fixed, page_people, ... إلخ) -------
# أنا ما غيرتها، فقط أبقيتها كما هي في ملفك الأصلي.


# (هنا يظل بقية صفحاتك كما كانت، ثم في النهاية نحدّث page_export و main فقط)

def page_export():
    nps_page_header("Export / Backup", "Simple CSV exports + full DB backup", "📤")

    conn = get_conn()
    tables = [
        "projects",
        "invoices",
        "cash_book",
        "debts_fixed",
        "people",
        "visas",
        "tickets",
        "accounts",
        "journal",
    ]

    st.markdown("### 📄 Table CSV Exports")

    for table in tables:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            f"⬇️ Download {table}.csv",
            data=csv_bytes,
            file_name=f"{table}.csv",
            mime="text/csv",
            key=f"csv_{table}",
        )

    conn.close()

    st.markdown("---")
    st.markdown("### 💾 Full Database Backup (.db)")

    db_full_path = os.path.abspath(DB_PATH)

    if os.path.exists(db_full_path):
        with open(db_full_path, "rb") as f:
            db_bytes = f.read()

        st.download_button(
            "💾 Download nps_accounting.db",
            data=db_bytes,
            file_name=f"nps_accounting_backup_{date.today().isoformat()}.db",
            mime="application/octet-stream",
            key="db_backup",
        )
        st.caption(db_full_path)
    else:
        st.error(f"Database file not found at: {db_full_path}")


# ========= MAIN =========


def main():
    st.set_page_config(
        page_title="NPS Accounting System",
        page_icon="💼",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_global_css()
    init_db()

    st.sidebar.title("NPS Accounting Navigation")

    menu_items = {
        "Dashboard": "📊 Dashboard",
        "Owners Dashboard": "👑 Owners Dashboard",
        "Project Dashboard": "📂 Project Dashboard",
        "Cash Book": "💰 Cash Book",
        "Projects": "🏗 Projects",
        "Invoices": "🧾 Invoices",
        "Debts & Fixed": "📉 Debts & Fixed",
        "People": "👥 People",
        "Visas": "🛂 Visas",
        "Tickets": "🎫 Tickets",
        "Accounts": "💼 Accounts",
        "Journal": "📝 Journal",
        "Reports": "📑 Reports",
        "Export": "📤 Export",
    }

    page = st.sidebar.radio(
        "Navigation",
        list(menu_items.keys()),
        format_func=lambda k: menu_items[k],
    )

    st.sidebar.caption(f"Invoice folder:\n{INVOICE_BASE_DIR}")

    with st.container():
        st.markdown('<div class="nps-main-card">', unsafe_allow_html=True)

        if page == "Dashboard":
            page_dashboard()
        elif page == "Owners Dashboard":
            page_owners_dashboard()
        elif page == "Project Dashboard":
            page_project_dashboard()
        elif page == "Cash Book":
            page_cash()
        elif page == "Projects":
            page_projects()
        elif page == "Invoices":
            page_invoices()
        elif page == "Debts & Fixed":
            page_debts_fixed()
        elif page == "People":
            page_people()
        elif page == "Visas":
            page_visas()
        elif page == "Tickets":
            page_tickets()
        elif page == "Accounts":
            page_accounts()
        elif page == "Journal":
            page_journal()
        elif page == "Reports":
            page_reports()
        else:
            page_export()

        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
