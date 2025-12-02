import os
import io
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

# =========================
# BACKEND MODE (SQLite or Neon)
# =========================

# Try to read DATABASE_URL from environment (DigitalOcean, etc.)
NEON_URL = os.environ.get("DATABASE_URL")

# If not found, try Streamlit secrets (Streamlit Cloud)
if not NEON_URL:
    try:
        NEON_URL = st.secrets.get("DATABASE_URL", None)
    except Exception:
        NEON_URL = None

USE_NEON = bool(NEON_URL)

DB_PATH = "nps_accounting.db"
INVOICE_BASE_DIR = os.path.join(os.getcwd(), "invoices")


# ========= DB HELPERS (Neon wrapper) =========

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
    """
    Return a DB connection.
    - If DATABASE_URL is set: Neon PostgreSQL
    - Otherwise: local SQLite DB file
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
    """
    Full DB initializer with auto-migration.
    Works for:
    - SQLite local file
    - Neon PostgreSQL (cloud)
    Automatically adds missing columns and creates tables safely.
    """

    os.makedirs(INVOICE_BASE_DIR, exist_ok=True)

    conn = get_conn()
    cur = conn.cursor()

    # ============================================================
    # ===============  POSTGRES / NEON MODE ======================
    # ============================================================
    if USE_NEON and NEON_URL:
        # ---------- Projects ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                project_code TEXT UNIQUE,
                name TEXT,
                client_name TEXT,
                location TEXT,
                contract_value NUMERIC(18,2) DEFAULT 0,
                start_date DATE,
                status TEXT,
                project_type TEXT DEFAULT 'Other'
            );
        """)

        # ---------- Cash Book ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cash_book (
                id SERIAL PRIMARY KEY,
                date DATE,
                project_code TEXT,
                description TEXT,
                method TEXT,
                ref_no TEXT,
                debit NUMERIC(18,2) DEFAULT 0,
                credit NUMERIC(18,2) DEFAULT 0,
                account_type TEXT,
                remarks TEXT
            );
        """)

        # Auto-migrate cash_book
        for col in ["ref_no TEXT", "account_type TEXT", "remarks TEXT"]:
            try:
                cur.execute(f"ALTER TABLE cash_book ADD COLUMN IF NOT EXISTS {col};")
            except:
                pass

        # ---------- Invoices ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                invoice_no TEXT,
                date DATE,
                project_code TEXT,
                client_name TEXT,
                description TEXT,
                amount NUMERIC(18,2),
                status TEXT,
                remarks TEXT
            );
        """)

        # ---------- Debts & Fixed Assets ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS debts_fixed (
                id SERIAL PRIMARY KEY,
                type TEXT,
                name TEXT,
                project_code TEXT,
                amount NUMERIC(18,2),
                start_date DATE,
                remarks TEXT
            );
        """)

        # ---------- People ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id SERIAL PRIMARY KEY,
                emp_code TEXT,
                name TEXT,
                position TEXT,
                project_code TEXT,
                basic_salary NUMERIC(18,2),
                allowance NUMERIC(18,2),
                is_active INTEGER DEFAULT 1
            );
        """)

        # ---------- Visas ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS visas (
                id SERIAL PRIMARY KEY,
                emp_code TEXT,
                name TEXT,
                visa_no TEXT,
                issue_date DATE,
                expiry_date DATE,
                cost NUMERIC(18,2),
                project_code TEXT
            );
        """)

        # ---------- Tickets ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                emp_code TEXT,
                name TEXT,
                from_city TEXT,
                to_city TEXT,
                travel_date DATE,
                cost NUMERIC(18,2),
                project_code TEXT
            );
        """)

        # ---------- Accounts ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                name TEXT,
                type TEXT
            );
        """)

        # ---------- Journal ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS journal (
                id SERIAL PRIMARY KEY,
                date DATE,
                account_code TEXT,
                description TEXT,
                debit NUMERIC(18,2),
                credit NUMERIC(18,2),
                ref TEXT
            );
        """)

        # Auto-migrate journal
        for col in ["account_code TEXT", "ref TEXT"]:
            try:
                cur.execute(f"ALTER TABLE journal ADD COLUMN IF NOT EXISTS {col};")
            except:
                pass

        conn.commit()
        conn.close()
        st.session_state["db_ready"] = True
        return

    # ============================================================
    # ====================  SQLITE MODE ===========================
    # ============================================================

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ---------- Projects ----------
    cur.execute("""
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
        );
    """)

    # ---------- Cash Book ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            project_code TEXT,
            description TEXT,
            method TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0
        );
    """)

    # Auto-migrate cash_book
    for col in ["ref_no TEXT", "account_type TEXT", "remarks TEXT"]:
        try:
            cur.execute(f"ALTER TABLE cash_book ADD COLUMN {col};")
        except:
            pass

    # ---------- Invoices ----------
    cur.execute("""
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
        );
    """)

    # ---------- Debts ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS debts_fixed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            name TEXT,
            project_code TEXT,
            amount REAL,
            start_date TEXT,
            remarks TEXT
        );
    """)

    # ---------- People ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            position TEXT,
            project_code TEXT,
            basic_salary REAL,
            allowance REAL,
            is_active INTEGER DEFAULT 1
        );
    """)

    # ---------- Visas ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS visas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            visa_no TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            cost REAL,
            project_code TEXT
        );
    """)

    # ---------- Tickets ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT,
            name TEXT,
            from_city TEXT,
            to_city TEXT,
            travel_date TEXT,
            cost REAL,
            project_code TEXT
        );
    """)

    # ---------- Accounts ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            type TEXT
        );
    """)

    # ---------- Journal ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            debit REAL,
            credit REAL
        );
    """)

    # Auto-migrate journal
    for col in ["account_code TEXT", "ref TEXT"]:
        try:
            cur.execute(f"ALTER TABLE journal ADD COLUMN {col};")
        except:
            pass

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
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    except Exception as e:
        st.error(f"❌ Database error while executing query:\n`{sql}`")
        st.error(str(e))
        return pd.DataFrame()
    finally:
        conn.close()

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


# ========= DASHBOARD PAGES =========

def page_dashboard():
    nps_page_header("NPS Accounting Dashboard", "FM & MEP Financial Overview", "📊")

    inv_df = df_from_query("SELECT * FROM invoices")
    cash_df = df_from_query("SELECT * FROM cash_book")
    debts_df = df_from_query("SELECT * FROM debts_fixed")

    total_invoices = inv_df["amount"].sum() if not inv_df.empty else 0.0
    total_debit = cash_df["debit"].sum() if not cash_df.empty else 0.0
    total_credit = cash_df["credit"].sum() if not cash_df.empty else 0.0
    net_cash = total_debit - total_credit

    total_debts = (
        debts_df.loc[debts_df["type"] == "Debt", "amount"].sum() if not debts_df.empty else 0.0
    )
    total_assets = (
        debts_df.loc[debts_df["type"] == "Fixed Asset", "amount"].sum()
        if not debts_df.empty
        else 0.0
    )

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

    st.markdown("### 📊 Ratios & Coverage")

    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric("⚖️ Debt / Assets", f"{debt_to_assets:,.2f}x" if debt_to_assets is not None else "N/A")
    with r2:
        st.metric("🧯 Cash Coverage", f"{cash_coverage:,.2f}x" if cash_coverage is not None else "N/A")
    with r3:
        st.metric("📈 Collection Ratio", f"{collection_ratio:,.1f}%" if collection_ratio is not None else "N/A")

    st.markdown("### 🚨 Alerts & Warnings")

    any_alert = False
    if net_cash < 0:
        any_alert = True
        st.error("🔴 Net cash is negative – راجع الصرف والالتزامات النقدية.")
    elif net_cash < total_debts and total_debts > 0:
        any_alert = True
        st.warning("🟠 Net cash أقل من إجمالي الديون – راجع خطة التحصيل.")

    if debt_to_assets is not None and debt_to_assets > 1.0:
        any_alert = True
        st.warning("🟠 Debt/Assets ratio > 1 – الديون أعلى من الأصول الثابتة.")

    if collection_ratio is not None and collection_ratio < 70:
        any_alert = True
        st.warning("🟠 Collection ratio أقل من 70% – تحصيل الفواتير ضعيف.")

    if not any_alert:
        st.success("✅ No major alerts detected – الوضع المالي مستقر حاليًا.")

    st.markdown("---")

    st.markdown("### 📉 Monthly Cash Trend & Recent Activity")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        if cash_df.empty:
            st.info("No cash movements yet.")
        else:
            cash_plot = cash_df.copy()
            cash_plot["date"] = pd.to_datetime(cash_plot["date"])
            cash_plot = (
                cash_plot.groupby(pd.Grouper(key="date", freq="M"))[["debit", "credit"]]
                .sum()
                .reset_index()
            )
            cash_plot["month"] = cash_plot["date"].dt.to_period("M").astype(str)
            cash_plot = cash_plot[["month", "debit", "credit"]]
            st.bar_chart(
                cash_plot.set_index("month")[["debit", "credit"]],
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
    nps_page_header("Owners Dashboard", "High-level performance for company owners", "👑")

    proj_df = df_from_query(
        "SELECT project_code, name, client_name, contract_value, status FROM projects"
    )
    inv_df = df_from_query("SELECT project_code, amount, status FROM invoices")
    cash_df = df_from_query("SELECT project_code, debit, credit FROM cash_book")
    debts_df = df_from_query("SELECT project_code, type, amount FROM debts_fixed")

    if proj_df.empty and inv_df.empty and cash_df.empty and debts_df.empty:
        st.info("No financial data yet.")
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
        st.info("No project codes found.")
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
        st.metric("💸 Total Revenue", f"{total_revenue:,.0f} IQD")
    with c2:
        st.metric("💰 Estimated Profit", f"{total_profit:,.0f} IQD")
    with c3:
        st.metric("🏗 Projects", total_projects)
    with c4:
        st.metric(
            "📈 Overall Profit Margin",
            f"{overall_margin:,.1f}%" if overall_margin is not None else "N/A",
        )

    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric(
            "⚖️ Debt / Assets",
            f"{(total_debts / total_assets):,.2f}x" if total_assets > 0 else "N/A",
        )
    with r2:
        st.metric(
            "🧯 Cash Coverage",
            f"{(summary['net_cash'].sum() / total_debts):,.2f}x"
            if total_debts > 0
            else "N/A",
        )
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
def page_project_dashboard():
    nps_page_header("Project Dashboard", "Overview per project", "📂")

    proj_df = df_from_query("SELECT * FROM projects")
    if proj_df.empty:
        st.info("No projects yet.")
        return

    project_code = st.selectbox(
        "Select Project",
        proj_df["project_code"].tolist(),
        format_func=lambda c: f"{c} - {proj_df.loc[proj_df['project_code'] == c, 'name'].iloc[0]}",
    )

    if not project_code:
        return

    inv_df = df_from_query("SELECT * FROM invoices WHERE project_code = ?", (project_code,))
    cash_df = df_from_query("SELECT * FROM cash_book WHERE project_code = ?", (project_code,))
    debts_df = df_from_query("SELECT * FROM debts_fixed WHERE project_code = ?", (project_code,))

    total_revenue = inv_df["amount"].sum() if not inv_df.empty else 0.0
    cash_in = cash_df["debit"].sum() if not cash_df.empty else 0.0
    cash_out = cash_df["credit"].sum() if not cash_df.empty else 0.0
    net_cash = cash_in - cash_out
    debts = debts_df.loc[debts_df["type"] == "Debt", "amount"].sum() if not debts_df.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Revenue", f"{total_revenue:,.0f} IQD")
    with c2:
        st.metric("Cash In", f"{cash_in:,.0f} IQD")
    with c3:
        st.metric("Cash Out", f"{cash_out:,.0f} IQD")
    with c4:
        st.metric("Net Cash", f"{net_cash:,.0f} IQD")

    st.markdown("### Invoices")
    st.dataframe(inv_df, use_container_width=True)

    st.markdown("### Cash Book")
    st.dataframe(cash_df, use_container_width=True)

    st.markdown("### Debts / Assets")
    st.dataframe(debts_df, use_container_width=True)


def page_cash():
    nps_page_header("Cash Book", "Daily cash-in / cash-out for NPS", "💰")

    col1, col2 = st.columns(2)
    with col1:
        trans_date = st.date_input("Date", value=date.today())
        project_code = st.text_input("Project Code")
        method = st.selectbox("Method", ["Cash", "Bank", "Transfer", "Other"])
        ref_no = st.text_input("Reference No.")
    with col2:
        description = st.text_input("Description")
        account_type = st.selectbox(
            "Account Type",
            ["General", "Salary", "Material", "Subcontract", "Other"],
        )
        debit = st.number_input("Debit (in)", min_value=0.0, step=1000.0)
        credit = st.number_input("Credit (out)", min_value=0.0, step=1000.0)
        remarks = st.text_input("Remarks")

    if st.button("💾 Save Cash Entry"):
        if debit > 0 and credit > 0:
            st.error("❌ لا يمكن أن يكون Debit و Credit أكبر من صفر في نفس الحركة.")
        elif debit == 0 and credit == 0:
            st.error("❌ يجب إدخال قيمة إما في Debit أو في Credit.")
        else:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO cash_book (
                        date, project_code, description, method, ref_no,
                        debit, credit, account_type, remarks
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trans_date.isoformat(),
                        project_code.strip() or None,
                        description.strip() or None,
                        method,
                        ref_no.strip() or None,
                        float(debit),
                        float(credit),
                        account_type,
                        remarks.strip() or None,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("✅ Cash entry saved.")
            except Exception as e:
                st.error("❌ Failed to save cash entry.")
                st.error(str(e))

    st.markdown("---")
    st.markdown("### 📒 Cash Book Entries")

    try:
        conn = get_conn()
        df = pd.read_sql_query(
            "SELECT date, project_code, description, method, ref_no, "
            "debit, credit, account_type, remarks "
            "FROM cash_book ORDER BY date DESC, id DESC",
            conn,
        )
        conn.close()
        if df.empty:
            st.info("No cash entries yet.")
        else:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error("❌ Failed to load cash book entries.")
        st.error(str(e))


def page_projects():
    nps_page_header("Projects", "Create and manage projects", "🏗")

    with st.form("project_form"):
        col1, col2 = st.columns(2)
        with col1:
            project_code = st.text_input("Project Code")
            name = st.text_input("Project Name")
            client_name = st.text_input("Client Name")
        with col2:
            location = st.text_input("Location")
            contract_value = st.number_input(
                "Contract Value (IQD)", min_value=0.0, step=1_000_000.0
            )
            start_date = st.date_input("Start Date", value=date.today())
            status = st.selectbox("Status", ["Tender", "Ongoing", "Completed", "On Hold"])
        project_type = st.selectbox("Project Type", ["FM", "MEP", "Other"])
        submitted = st.form_submit_button("💾 Save Project")

    if submitted:
        if not project_code:
            st.error("Project code is required.")
        else:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT OR REPLACE INTO projects (
                        project_code, name, client_name, location,
                        contract_value, start_date, status, project_type
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_code.strip(),
                        name.strip() or None,
                        client_name.strip() or None,
                        location.strip() or None,
                        float(contract_value),
                        start_date.isoformat(),
                        status,
                        project_type,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("✅ Project saved.")
            except Exception as e:
                st.error("❌ Failed to save project.")
                st.error(str(e))

    st.markdown("---")
    st.markdown("### 📋 All Projects")

    df = df_from_query(
        "SELECT project_code, name, client_name, location, contract_value, start_date, status, project_type "
        "FROM projects ORDER BY start_date DESC"
    )
    if df.empty:
        st.info("No projects yet.")
    else:
        df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
        st.dataframe(df, use_container_width=True)


def page_invoices():
    nps_page_header("Invoices", "Issue and track invoices", "🧾")

    with st.form("invoice_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No")
            inv_date = st.date_input("Date", value=date.today())
            project_code = st.text_input("Project Code")
            client_name = st.text_input("Client Name")
        with col2:
            description = st.text_input("Description")
            amount = st.number_input("Amount (IQD)", min_value=0.0, step=100000.0)
            status = st.selectbox("Status", ["Draft", "Submitted", "Paid", "Cancelled"])
            remarks = st.text_input("Remarks")

        uploaded_file = st.file_uploader("Attach Invoice File (optional)", type=["pdf", "jpg", "png"])
        submit_invoice = st.form_submit_button("💾 Save Invoice")

    if submit_invoice:
        if not invoice_no:
            st.error("Invoice No is required.")
        else:
            file_path = None
            if uploaded_file is not None:
                file_path = save_invoice_file(
                    project_code, invoice_no, uploaded_file, uploaded_file.name
                )

            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO invoices (
                        invoice_no, date, project_code, client_name,
                        description, amount, status, remarks
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_no.strip(),
                        inv_date.isoformat(),
                        project_code.strip() or None,
                        client_name.strip() or None,
                        description.strip() or None,
                        float(amount),
                        status,
                        remarks.strip() or None,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("✅ Invoice saved.")
                if file_path:
                    st.info(f"File saved to: {file_path}")
            except Exception as e:
                st.error("❌ Failed to save invoice.")
                st.error(str(e))

    st.markdown("---")
    st.markdown("### 📋 All Invoices")

    df = df_from_query(
        "SELECT invoice_no, date, project_code, client_name, description, amount, status, remarks "
        "FROM invoices ORDER BY date DESC"
    )
    if df.empty:
        st.info("No invoices yet.")
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        st.dataframe(df, use_container_width=True)


def page_debts_fixed():
    nps_page_header("Debts & Fixed Assets", "Loans, payables, and fixed assets", "📉")

    with st.form("debt_form"):
        col1, col2 = st.columns(2)
        with col1:
            dtype = st.selectbox("Type", ["Debt", "Fixed Asset"])
            name = st.text_input("Name")
            project_code = st.text_input("Project Code")
        with col2:
            amount = st.number_input("Amount (IQD)", min_value=0.0, step=100000.0)
            start_date = st.date_input("Start Date", value=date.today())
            remarks = st.text_input("Remarks")
        submitted = st.form_submit_button("💾 Save Entry")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO debts_fixed (
                    type, name, project_code, amount, start_date, remarks
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dtype,
                    name.strip() or None,
                    project_code.strip() or None,
                    float(amount),
                    start_date.isoformat(),
                    remarks.strip() or None,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Entry saved.")
        except Exception as e:
            st.error("❌ Failed to save entry.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 💸 Debts & Assets List")

    df = df_from_query(
        "SELECT type, name, project_code, amount, start_date, remarks "
        "FROM debts_fixed ORDER BY start_date DESC"
    )
    if df.empty:
        st.info("No entries yet.")
    else:
        df["start_date"] = pd.to_datetime(df["start_date"]).dt.date
        st.dataframe(df, use_container_width=True)


def page_people():
    nps_page_header("People / Staff", "Simple employee cost overview", "👥")

    with st.form("people_form"):
        col1, col2 = st.columns(2)
        with col1:
            emp_code = st.text_input("Employee Code")
            name = st.text_input("Name")
            position = st.text_input("Position")
        with col2:
            project_code = st.text_input("Project Code")
            basic_salary = st.number_input("Basic Salary", min_value=0.0, step=50000.0)
            allowance = st.number_input("Allowance", min_value=0.0, step=50000.0)
        is_active = st.checkbox("Active", value=True)
        submitted = st.form_submit_button("💾 Save Employee")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO people (
                    emp_code, name, position, project_code,
                    basic_salary, allowance, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    emp_code.strip() or None,
                    name.strip() or None,
                    position.strip() or None,
                    project_code.strip() or None,
                    float(basic_salary),
                    float(allowance),
                    1 if is_active else 0,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Employee saved.")
        except Exception as e:
            st.error("❌ Failed to save employee.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 👥 Employees List")

    df = df_from_query(
        "SELECT emp_code, name, position, project_code, basic_salary, allowance, is_active "
        "FROM people ORDER BY name"
    )
    if df.empty:
        st.info("No employees yet.")
    else:
        df["is_active"] = df["is_active"].map({1: "Active", 0: "Inactive"})
        st.dataframe(df, use_container_width=True)
def page_visas():
    nps_page_header("Visas", "Visa costs and expiry", "🛂")

    with st.form("visa_form"):
        col1, col2 = st.columns(2)
        with col1:
            emp_code = st.text_input("Employee Code")
            name = st.text_input("Name")
            visa_no = st.text_input("Visa No")
        with col2:
            issue_date = st.date_input("Issue Date", value=date.today())
            expiry_date = st.date_input("Expiry Date", value=date.today())
            cost = st.number_input("Cost", min_value=0.0, step=50000.0)
        project_code = st.text_input("Project Code")
        submitted = st.form_submit_button("💾 Save Visa")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO visas (
                    emp_code, name, visa_no, issue_date,
                    expiry_date, cost, project_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    emp_code.strip() or None,
                    name.strip() or None,
                    visa_no.strip() or None,
                    issue_date.isoformat(),
                    expiry_date.isoformat(),
                    float(cost),
                    project_code.strip() or None,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Visa saved.")
        except Exception as e:
            st.error("❌ Failed to save visa.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 🛂 Visas List")

    try:
        df = df_from_query("SELECT * FROM visas ORDER BY expiry_date")
    except:
        df = pd.DataFrame()

    if df.empty:
        st.info("No visas yet.")
        return

    for col in ["issue_date", "expiry_date"]:
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col]).dt.date
            except:
                pass

    st.dataframe(df, use_container_width=True)


def page_tickets():
    nps_page_header("Tickets", "Flight tickets and travel cost", "🎫")

    with st.form("ticket_form"):
        col1, col2 = st.columns(2)
        with col1:
            emp_code = st.text_input("Employee Code")
            name = st.text_input("Name")
            from_city = st.text_input("From City")
        with col2:
            to_city = st.text_input("To City")
            travel_date = st.date_input("Travel Date", value=date.today())
            cost = st.number_input("Cost", min_value=0.0, step=50000.0)
        project_code = st.text_input("Project Code")
        submitted = st.form_submit_button("💾 Save Ticket")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tickets (
                    emp_code, name, from_city, to_city,
                    travel_date, cost, project_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    emp_code.strip() or None,
                    name.strip() or None,
                    from_city.strip() or None,
                    to_city.strip() or None,
                    travel_date.isoformat(),
                    float(cost),
                    project_code.strip() or None,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Ticket saved.")
        except Exception as e:
            st.error("❌ Failed to save ticket.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 🎫 Tickets List")

    df = df_from_query(
        "SELECT emp_code, name, from_city, to_city, travel_date, cost, project_code "
        "FROM tickets ORDER BY travel_date DESC"
    )
    if df.empty:
        st.info("No tickets yet.")
    else:
        df["travel_date"] = pd.to_datetime(df["travel_date"]).dt.date
        st.dataframe(df, use_container_width=True)


def page_accounts():
    nps_page_header("Accounts", "Chart of accounts (simple)", "📚")

    with st.form("account_form"):
        code = st.text_input("Account Code")
        name = st.text_input("Account Name")
        atype = st.selectbox("Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
        submitted = st.form_submit_button("💾 Save Account")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO accounts (code, name, type)
                VALUES (?, ?, ?)
                """,
                (
                    code.strip(),
                    name.strip() or None,
                    atype,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Account saved.")
        except Exception as e:
            st.error("❌ Failed to save account.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 📋 Accounts List")

    df = df_from_query("SELECT code, name, type FROM accounts ORDER BY code")
    if df.empty:
        st.info("No accounts yet.")
    else:
        st.dataframe(df, use_container_width=True)


def page_journal():
    nps_page_header("Journal", "Manual journal entries", "📝")

    with st.form("journal_form"):
        col1, col2 = st.columns(2)
        with col1:
            jdate = st.date_input("Date", value=date.today())
            account_code = st.text_input("Account Code")
            description = st.text_input("Description")
        with col2:
            debit = st.number_input("Debit", min_value=0.0, step=10000.0)
            credit = st.number_input("Credit", min_value=0.0, step=10000.0)
            ref = st.text_input("Ref / Document No")
        submitted = st.form_submit_button("💾 Save Entry")

    if submitted:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO journal (
                    date, account_code, description, debit, credit, ref
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    jdate.isoformat(),
                    account_code.strip() or None,
                    description.strip() or None,
                    float(debit),
                    float(credit),
                    ref.strip() or None,
                ),
            )
            conn.commit()
            conn.close()
            st.success("✅ Journal entry saved.")
        except Exception as e:
            st.error("❌ Failed to save journal entry.")
            st.error(str(e))

    st.markdown("---")
    st.markdown("### 📋 Journal Entries")

    df = df_from_query(
        "SELECT date, account_code, description, debit, credit, ref "
        "FROM journal ORDER BY date DESC, id DESC"
    )
    if df.empty:
        st.info("No journal entries yet.")
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        st.dataframe(df, use_container_width=True)


def page_reports():
    nps_page_header("Reports", "Summary reports and Excel export", "📑")

    inv_df = df_from_query("SELECT * FROM invoices")
    cash_df = df_from_query("SELECT * FROM cash_book")
    debts_df = df_from_query("SELECT * FROM debts_fixed")

    total_invoices = inv_df["amount"].sum() if not inv_df.empty else 0.0
    total_debit = cash_df["debit"].sum() if not cash_df.empty else 0.0
    total_credit = cash_df["credit"].sum() if not cash_df.empty else 0.0
    net_cash = total_debit - total_credit
    total_debts = debts_df.loc[debts_df["type"] == "Debt", "amount"].sum() if not debts_df.empty else 0.0

    st.markdown("### 📊 Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Invoices", f"{total_invoices:,.0f} IQD")
    with c2:
        st.metric("Net Cash", f"{net_cash:,.0f} IQD")
    with c3:
        st.metric("Total Debts", f"{total_debts:,.0f} IQD")

    st.markdown("---")
    st.markdown("### ⬇️ Export to Excel (All data)")

    try:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            if not inv_df.empty:
                inv_df.to_excel(writer, sheet_name="Invoices", index=False)
            if not cash_df.empty:
                cash_df.to_excel(writer, sheet_name="CashBook", index=False)
            if not debts_df.empty:
                debts_df.to_excel(writer, sheet_name="DebtsFixed", index=False)
        buffer.seek(0)
        st.download_button(
            "⬇️ Download Excel Report",
            data=buffer,
            file_name="nps_accounting_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.error("❌ Failed to generate Excel report.")
        st.error(str(e))


def page_export():
    nps_page_header("Export / Backup", "CSV exports + full DB backup", "📤")

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
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        except Exception:
            continue
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
    st.markdown("### 💾 Full SQLite DB Backup")

    # Only meaningful in SQLite mode
    if not USE_NEON:
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
    else:
        st.info("Running on Neon/PostgreSQL – physical DB file backup is not applicable.")


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
        "Accounts": "📚 Accounts",
        "Journal": "📝 Journal",
        "Reports": "📑 Reports",
        "Export": "📤 Export",
    }

    page = st.sidebar.radio(
        "Navigation",
        list(menu_items.keys()),
        format_func=lambda k: menu_items[k],
    )

    st.sidebar.caption(f"Invoice folder: {INVOICE_BASE_DIR}")

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


