import os
import io
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

DB_PATH = "nps_accounting.db"
INVOICE_BASE_DIR = os.path.join(os.getcwd(), "invoices")


# ========= DB HELPERS =========

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(INVOICE_BASE_DIR, exist_ok=True)
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

    # Invoices
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_code TEXT,
            invoice_no TEXT,
            date TEXT,
            amount REAL,
            currency TEXT DEFAULT 'IQD',
            status TEXT,
            notes TEXT
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
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            method TEXT,
            account_type TEXT
        )
        """
    )

    # Debts & fixed
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
            country TEXT,
            visa_number TEXT,
            expiry_date TEXT,
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
            code TEXT,
            name TEXT,
            type TEXT   -- Asset, Liability, Equity, Income, Expense
        )
        """
    )

    # Journal entries
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            ref TEXT,
            description TEXT,
            debit_account TEXT,
            credit_account TEXT,
            amount REAL
        )
        """
    )

    conn.commit()
    conn.close()


# ========= UI THEME (GLOBAL) =========

NPS_PRIMARY = "#047857"   # emerald
NPS_DARK = "#022c22"
NPS_LIGHT_BG = "#ecfdf5"


def inject_global_css():
    st.markdown(
        f"""
        <style>
        /* App background */
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at top left, #ecfdf5 0, #f1f5f9 45%, #e5e7eb 100%);
        }}

        /* Sidebar styling */
        [data-testid="stSidebar"] > div:first-child {{
            background: linear-gradient(180deg, {NPS_DARK} 0%, #064e3b 45%, #020617 100%);
            color: #f9fafb;
        }}
        [data-testid="stSidebar"] * {{
            color: #e5e7eb !important;
        }}

        /* Sidebar title & logo */
        .sidebar-title {{
            font-size: 22px !important;
            font-weight: 700 !important;
            padding: 8px 4px 4px 4px;
        }}
        .sidebar-subtitle {{
            font-size: 11px;
            opacity: 0.7;
            padding-left: 2px;
        }}

        /* Sidebar radio buttons (menu) */
        [data-testid="stSidebar"] [role="radiogroup"] label {{
            padding: 6px 10px;
            border-radius: 10px;
            margin-bottom: 4px;
            transition: background 0.15s ease, transform 0.1s ease;
            font-size: 15px;
        }}
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
            background: rgba(15, 118, 110, 0.4);
            transform: translateX(2px);
        }}

        /* Main content card feel */
        .nps-main-card {{
            background: rgba(255, 255, 255, 0.92);
            border-radius: 18px;
            padding: 18px 20px;
            box-shadow: 0 18px 35px rgba(15, 23, 42, 0.12);
            border: 1px solid #e5e7eb;
            margin-bottom: 18px;
        }}

        /* Page header */
        .nps-page-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
            padding: 10px 16px;
            border-radius: 16px;
            background: linear-gradient(120deg, rgba(16,185,129,0.12), rgba(59,130,246,0.05));
            border: 1px solid rgba(16,185,129,0.15);
        }}
        .nps-page-icon {{
            font-size: 26px;
        }}
        .nps-page-header h1 {{
            font-size: 22px;
            margin: 0;
        }}
        .nps-page-header p {{
            margin: 0;
            font-size: 13px;
            opacity: 0.8;
        }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background: rgba(255, 255, 255, 0.96);
            padding: 10px 12px;
            border-radius: 14px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
        }}
        [data-testid="stMetric"] > div {{
            justify-content: space-between;
        }}

        /* Tables */
        .stDataFrame, .stTable {{
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
        }}

        /* Buttons */
        .stButton > button {{
            border-radius: 999px;
            background: {NPS_PRIMARY};
            border: none;
            color: white;
            font-weight: 600;
            padding: 0.4rem 1.1rem;
        }}
        .stButton > button:hover {{
            background: #059669;
            box-shadow: 0 8px 16px rgba(5, 150, 105, 0.45);
        }}

        /* Expander */
        [data-testid="stExpander"] {{
            border-radius: 14px;
            border: 1px solid #d1d5db;
            background: rgba(255,255,255,0.95);
        }}

        /* Download buttons */
        [data-testid="baseButton-secondary"] {{
            border-radius: 999px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def nps_page_header(title: str, subtitle: Optional[str] = None, icon: str = "📊"):
    """Reusable nice header for each page."""
    st.markdown(
        f"""
        <div class="nps-page-header">
            <div class="nps-page-icon">{icon}</div>
            <div>
                <h1>{title}</h1>
                {f"<p>{subtitle}</p>" if subtitle else ""}
            </div>
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


def import_projects_from_csv(uploaded_file):
    """Import projects from CSV.

    Supports two formats:
    1) Full accounting format:
        project_code, name, client_name, location,
        contract_value, start_date, status[, project_type]

    2) HR simple format:
        project_code, project_name, is_held
        - name  := project_name
        - status: "On Hold" if is_held == 1 else "Active"
        - client_name, location  -> ""
        - contract_value         -> 0
        - start_date             -> None
    """
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Error reading projects CSV: {e}")
        return

    # CASE 1: full accounting format
    full_required = [
        "project_code",
        "name",
        "client_name",
        "location",
        "contract_value",
        "start_date",
        "status",
    ]
    conn = get_conn()
    cur = conn.cursor()

    if all(col in df.columns for col in full_required):
        has_type = "project_type" in df.columns
        df["contract_value"] = pd.to_numeric(df["contract_value"], errors="coerce").fillna(0)

        count = 0
        for _, row in df.iterrows():
            start_date_val = row.get("start_date", None)
            if pd.isna(start_date_val):
                start_date_str = None
            else:
                try:
                    start_date_str = pd.to_datetime(start_date_val).date().isoformat()
                except Exception:
                    start_date_str = None

            project_type = "Other"
            if has_type and not pd.isna(row.get("project_type", "")):
                project_type = str(row["project_type"])

            cur.execute(
                """
                INSERT INTO projects (project_code, name, client_name,
                                      location, contract_value, start_date, status, project_type)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(project_code) DO UPDATE SET
                    name=excluded.name,
                    client_name=excluded.client_name,
                    location=excluded.location,
                    contract_value=excluded.contract_value,
                    start_date=excluded.start_date,
                    status=excluded.status,
                    project_type=excluded.project_type
                """,
                (
                    str(row["project_code"]),
                    str(row["name"]),
                    str(row.get("client_name", "")),
                    str(row.get("location", "")),
                    float(row["contract_value"]),
                    start_date_str,
                    str(row.get("status", "Active")),
                    project_type,
                ),
            )
            count += 1

        conn.commit()
        conn.close()
        st.success(f"Imported / updated {count} projects from CSV.")
        return

    # CASE 2: HR simple format
    hr_required = ["project_code", "project_name", "is_held"]
    if all(col in df.columns for col in hr_required):
        st.info(
            "Detected HR export format (project_code, project_name, is_held). "
            "Will auto-map to Accounting structure."
        )

        out = pd.DataFrame()
        out["project_code"] = df["project_code"].astype(str)
        out["name"] = df["project_name"].astype(str)
        out["client_name"] = ""
        out["location"] = ""
        out["contract_value"] = 0.0
        out["start_date"] = None
        out["status"] = df["is_held"].apply(
            lambda v: "On Hold" if str(v) in ["1", "True", "true"] else "Active"
        )
        out["project_type"] = "Other"

        count = 0
        for _, row in out.iterrows():
            cur.execute(
                """
                INSERT INTO projects (project_code, name, client_name,
                                      location, contract_value, start_date, status, project_type)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(project_code) DO UPDATE SET
                    name=excluded.name,
                    client_name=excluded.client_name,
                    location=excluded.location,
                    contract_value=excluded.contract_value,
                    start_date=excluded.start_date,
                    status=excluded.status,
                    project_type=excluded.project_type
                """,
                (
                    row["project_code"],
                    row["name"],
                    row["client_name"],
                    row["location"],
                    float(row["contract_value"]),
                    None,
                    row["status"],
                    row["project_type"],
                ),
            )
            count += 1

        conn.commit()
        conn.close()
        st.success(f"Imported / updated {count} projects from HR CSV (auto-mapped).")
        return

    # Neither format
    conn.close()
    st.error(
        "Projects CSV format not recognized.\n\n"
        "Expected either:\n"
        "1) Accounting format: project_code, name, client_name, location, "
        "contract_value, start_date, status[, project_type]\n"
        "2) HR format: project_code, project_name, is_held"
    )
    st.info(f"Found columns: {list(df.columns)}")


# ========= PAGES =========

def page_dashboard():
    nps_page_header("NPS Accounting Dashboard", "FM & MEP Financial Overview", "📊")

    inv_df = df_from_query("SELECT * FROM invoices")
    cash_df = df_from_query("SELECT * FROM cash_book")
    debts_df = df_from_query("SELECT * FROM debts_fixed")

    total_invoices = inv_df["amount"].sum() if not inv_df.empty else 0
    total_debit = cash_df["debit"].sum() if not cash_df.empty else 0
    total_credit = cash_df["credit"].sum() if not cash_df.empty else 0
    net_cash = total_debit - total_credit
    total_debts = debts_df[debts_df["type"] == "Debt"]["amount"].sum() if not debts_df.empty else 0
    total_assets = debts_df[debts_df["type"] == "Fixed Asset"]["amount"].sum() if not debts_df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invoices", f"{total_invoices:,.0f} IQD")
    c2.metric("Net Cash Movement", f"{net_cash:,.0f} IQD")
    c3.metric("Total Debts", f"{total_debts:,.0f} IQD")
    c4.metric("Fixed Assets", f"{total_assets:,.0f} IQD")

    st.markdown("### 🔍 Recent Activity")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Recent Invoices")
        if inv_df.empty:
            st.info("No invoices yet.")
        else:
            st.dataframe(inv_df.sort_values("date", ascending=False).head(10))

    with col_b:
        st.subheader("Recent Cash Movements")
        if cash_df.empty:
            st.info("No cash entries yet.")
        else:
            st.dataframe(cash_df.sort_values("date", ascending=False).head(10))


def page_project_dashboard():
    nps_page_header("Project Dashboard", "Per-project income, cash and debts", "📂")

    inv_df = df_from_query("SELECT project_code, amount FROM invoices")
    cash_df = df_from_query("SELECT project_code, debit, credit FROM cash_book")

    if inv_df.empty and cash_df.empty:
        st.info("No project financial data yet.")
        return

    # Build summary
    proj_inv = inv_df.groupby("project_code")["amount"].sum().rename("invoices")
    proj_cash = cash_df.groupby("project_code").agg(
        debit_sum=("debit", "sum"), credit_sum=("credit", "sum")
    )
    summary = proj_cash.join(proj_inv, how="outer").fillna(0)
    summary["net_cash"] = summary["debit_sum"] - summary["credit_sum"]

    st.subheader("Project Financial Summary")
    st.dataframe(summary)

    st.markdown("### 📈 Net Cash by Project")
    if not summary.empty:
        st.bar_chart(summary["net_cash"])


def page_cash():
    nps_page_header("Cash Book", "Daily cash-in / cash-out for NPS", "💰")
    conn = get_conn()
    cur = conn.cursor()

    col1, col2 = st.columns(2)
    with col1:
        trans_date = st.date_input("Date", value=date.today())
        project_code = st.text_input("Project Code")
        method = st.selectbox("Method", ["Cash", "Bank", "Transfer", "Other"])
    with col2:
        description = st.text_input("Description")
        account_type = st.selectbox("Account Type", ["General", "Salary", "Material", "Subcontract", "Other"])
        debit = st.number_input("Debit (in)", min_value=0.0, step=1000.0)
        credit = st.number_input("Credit (out)", min_value=0.0, step=1000.0)

    if st.button("Save Cash Entry"):
        cur.execute(
            """
            INSERT INTO cash_book (date, project_code, description, debit, credit, method, account_type)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                trans_date.isoformat(),
                project_code,
                description,
                debit,
                credit,
                method,
                account_type,
            ),
        )
        conn.commit()
        st.success("Cash entry saved.")

    st.markdown("### 📒 Cash Book Entries")
    df = pd.read_sql_query("SELECT * FROM cash_book ORDER BY date DESC, id DESC", conn)
    conn.close()
    st.dataframe(df)


def page_projects():
    nps_page_header("Projects", "Master list for FM / MEP / Small Jobs", "🏗")

    conn = get_conn()
    cur = conn.cursor()

    with st.expander("➕ Add / Update Project", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            project_code = st.text_input("Project Code *")
            name = st.text_input("Project Name *")
            client_name = st.text_input("Client Name", value="NPS")
        with col2:
            location = st.text_input("Location")
            contract_value = st.number_input("Contract Value (IQD)", min_value=0.0, step=1000000.0)
            project_type = st.selectbox("Project Type", ["FM", "MEP", "Small Job", "Other"])
        with col3:
            start_date = st.date_input("Start Date", value=date.today())
            status = st.selectbox("Status", ["Active", "On Hold", "Closed"])

        if st.button("Save Project"):
            if not project_code or not name:
                st.error("Project code and name are required.")
            else:
                cur.execute(
                    """
                    INSERT INTO projects (project_code, name, client_name, location,
                                          contract_value, start_date, status, project_type)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(project_code) DO UPDATE SET
                        name=excluded.name,
                        client_name=excluded.client_name,
                        location=excluded.location,
                        contract_value=excluded.contract_value,
                        start_date=excluded.start_date,
                        status=excluded.status,
                        project_type=excluded.project_type
                    """,
                    (
                        project_code,
                        name,
                        client_name,
                        location,
                        contract_value,
                        start_date.isoformat(),
                        status,
                        project_type,
                    ),
                )
                conn.commit()
                st.success("Project saved / updated.")

    st.markdown("### 📥 Import Projects from CSV (Accounting or HR Format)")
    upload = st.file_uploader("Upload CSV", type=["csv"], key="proj_csv")
    if upload is not None:
        import_projects_from_csv(upload)

    st.markdown("### 📋 Current Projects")
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY project_code", conn)
    conn.close()
    st.dataframe(df)


def page_invoices():
    nps_page_header("Invoices", "Customer invoices linked to projects", "🧾")

    conn = get_conn()
    cur = conn.cursor()

    projects = pd.read_sql_query("SELECT project_code, name FROM projects ORDER BY project_code", conn)
    proj_options = [""] + projects["project_code"].tolist()

    col1, col2, col3 = st.columns(3)
    with col1:
        project_code = st.selectbox("Project Code", proj_options)
        invoice_no = st.text_input("Invoice No")
    with col2:
        inv_date = st.date_input("Invoice Date", value=date.today())
        amount = st.number_input("Amount", min_value=0.0, step=100000.0)
    with col3:
        currency = st.selectbox("Currency", ["IQD", "USD"])
        status = st.selectbox("Status", ["Draft", "Pending", "Paid", "Cancelled"])
        notes = st.text_input("Notes")

    if st.button("Save Invoice"):
        if not project_code:
            st.error("Project code required.")
        else:
            cur.execute(
                """
                INSERT INTO invoices (project_code, invoice_no, date, amount, currency, status, notes)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    project_code,
                    invoice_no,
                    inv_date.isoformat(),
                    amount,
                    currency,
                    status,
                    notes,
                ),
            )
            conn.commit()
            st.success("Invoice saved.")

    st.markdown("### 📋 All Invoices")
    df = pd.read_sql_query("SELECT * FROM invoices ORDER BY date DESC, id DESC", conn)
    conn.close()
    st.dataframe(df)


def page_debts_fixed():
    nps_page_header("Debts & Fixed Assets", "Loans, liabilities and major assets", "📉")
    conn = get_conn()
    cur = conn.cursor()

    col1, col2, col3 = st.columns(3)
    with col1:
        rec_type = st.selectbox("Type", ["Debt", "Fixed Asset"])
        name = st.text_input("Name")
    with col2:
        project_code = st.text_input("Project Code (optional)")
        amount = st.number_input("Amount", min_value=0.0, step=1000000.0)
    with col3:
        start_date = st.date_input("Start Date", value=date.today())
        remarks = st.text_input("Remarks")

    if st.button("Save Record"):
        cur.execute(
            """
            INSERT INTO debts_fixed (type, name, project_code, amount, start_date, remarks)
            VALUES (?,?,?,?,?,?)
            """,
            (
                rec_type,
                name,
                project_code,
                amount,
                start_date.isoformat(),
                remarks,
            ),
        )
        conn.commit()
        st.success("Record saved.")

    st.markdown("### 📋 Debts & Fixed Assets")
    df = pd.read_sql_query("SELECT * FROM debts_fixed", conn)
    conn.close()
    st.dataframe(df)


def page_people():
    nps_page_header("People Cost (Summary)", "Employees & basic salary data", "👥")

    conn = get_conn()
    cur = conn.cursor()

    col1, col2, col3 = st.columns(3)
    with col1:
        emp_code = st.text_input("Employee Code")
        name = st.text_input("Name")
    with col2:
        position = st.text_input("Position")
        project_code = st.text_input("Project Code")
    with col3:
        basic_salary = st.number_input("Basic Salary", min_value=0.0, step=50000.0)
        allowance = st.number_input("Allowance", min_value=0.0, step=50000.0)

    if st.button("Save Person"):
        cur.execute(
            """
            INSERT INTO people (emp_code, name, position, project_code, basic_salary, allowance, is_active)
            VALUES (?,?,?,?,?,?,1)
            """,
            (
                emp_code,
                name,
                position,
                project_code,
                basic_salary,
                allowance,
            ),
        )
        conn.commit()
        st.success("Record saved.")

    st.markdown("### 📋 People")
    df = pd.read_sql_query("SELECT * FROM people", conn)
    conn.close()
    st.dataframe(df)


def page_visas():
    nps_page_header("Visas", "Visa tracking & expiry", "🛂")
    conn = get_conn()
    cur = conn.cursor()

    col1, col2, col3 = st.columns(3)
    with col1:
        emp_code = st.text_input("Employee Code", key="vis_emp")
        name = st.text_input("Name", key="vis_name")
    with col2:
        country = st.text_input("Country")
        visa_number = st.text_input("Visa Number")
    with col3:
        expiry = st.date_input("Expiry Date", value=date.today())
        project_code = st.text_input("Project Code", key="vis_proj")

    if st.button("Save Visa"):
        cur.execute(
            """
            INSERT INTO visas (emp_code, name, country, visa_number, expiry_date, project_code)
            VALUES (?,?,?,?,?,?)
            """,
            (
                emp_code,
                name,
                country,
                visa_number,
                expiry.isoformat(),
                project_code,
            ),
        )
        conn.commit()
        st.success("Visa saved.")

    st.markdown("### 📋 Visa List")
    df = pd.read_sql_query("SELECT * FROM visas", conn)
    conn.close()
    st.dataframe(df)


def page_tickets():
    nps_page_header("Tickets", "Travel tickets & costs", "🎫")
    conn = get_conn()
    cur = conn.cursor()

    col1, col2, col3 = st.columns(3)
    with col1:
        emp_code = st.text_input("Employee Code", key="tick_emp")
        name = st.text_input("Name", key="tick_name")
    with col2:
        from_city = st.text_input("From City")
        to_city = st.text_input("To City")
    with col3:
        travel_date = st.date_input("Travel Date", value=date.today())
        cost = st.number_input("Cost", min_value=0.0, step=50000.0)
        project_code = st.text_input("Project Code", key="tick_proj")

    if st.button("Save Ticket"):
        cur.execute(
            """
            INSERT INTO tickets (emp_code, name, from_city, to_city, travel_date, cost, project_code)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                emp_code,
                name,
                from_city,
                to_city,
                travel_date.isoformat(),
                cost,
                project_code,
            ),
        )
        conn.commit()
        st.success("Ticket saved.")

    st.markdown("### 📋 Tickets")
    df = pd.read_sql_query("SELECT * FROM tickets", conn)
    conn.close()
    st.dataframe(df)


def page_accounts():
    nps_page_header("Chart of Accounts", "Accounting structure for journal entries", "💼")
    conn = get_conn()
    cur = conn.cursor()

    col1, col2 = st.columns(2)
    with col1:
        code = st.text_input("Account Code")
        name = st.text_input("Account Name")
    with col2:
        acc_type = st.selectbox("Type", ["Asset", "Liability", "Equity", "Income", "Expense"])

    if st.button("Save Account"):
        cur.execute(
            """
            INSERT INTO accounts (code, name, type)
            VALUES (?,?,?)
            """,
            (code, name, acc_type),
        )
        conn.commit()
        st.success("Account saved.")

    st.markdown("### 📋 Accounts")
    df = pd.read_sql_query("SELECT * FROM accounts", conn)
    conn.close()
    st.dataframe(df)


def page_journal():
    nps_page_header("Journal Entries", "Manual accounting entries", "📝")
    conn = get_conn()
    cur = conn.cursor()

    accounts_df = pd.read_sql_query("SELECT code, name FROM accounts ORDER BY code", conn)
    acc_choices = [""] + accounts_df["code"].tolist()

    col1, col2 = st.columns(2)
    with col1:
        j_date = st.date_input("Date", value=date.today())
        ref = st.text_input("Reference")
    with col2:
        desc = st.text_input("Description")

    col3, col4, col5 = st.columns(3)
    with col3:
        debit_acc = st.selectbox("Debit Account", acc_choices)
    with col4:
        credit_acc = st.selectbox("Credit Account", acc_choices)
    with col5:
        amount = st.number_input("Amount", min_value=0.0, step=100000.0)

    if st.button("Save Journal Entry"):
        if not debit_acc or not credit_acc:
            st.error("Select both debit and credit accounts.")
        else:
            cur.execute(
                """
                INSERT INTO journal (date, ref, description, debit_account, credit_account, amount)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    j_date.isoformat(),
                    ref,
                    desc,
                    debit_acc,
                    credit_acc,
                    amount,
                ),
            )
            conn.commit()
            st.success("Journal entry saved.")

    st.markdown("### 📋 Journal Entries")
    df = pd.read_sql_query("SELECT * FROM journal ORDER BY date DESC, id DESC", conn)
    conn.close()
    st.dataframe(df)


def page_reports():
    nps_page_header("Reports", "Download high-level views in Excel", "📑")

    conn = get_conn()
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    invoices_df = pd.read_sql_query("SELECT * FROM invoices", conn)
    cash_df = pd.read_sql_query("SELECT * FROM cash_book", conn)
    conn.close()

    st.markdown("### 📥 Download Data as Excel")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        projects_df.to_excel(writer, index=False, sheet_name="Projects")
        invoices_df.to_excel(writer, index=False, sheet_name="Invoices")
        cash_df.to_excel(writer, index=False, sheet_name="CashBook")

    st.download_button(
        "⬇️ Download Projects + Invoices + CashBook",
        data=buffer.getvalue(),
        file_name=f"nps_accounting_{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def page_export():
    nps_page_header("Export / Backup", "Simple CSV exports for all tables", "📤")

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

    for table in tables:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            f"⬇️ Download {table}.csv",
            data=csv_bytes,
            file_name=f"{table}.csv",
            mime="text/csv",
        )

    conn.close()


# ========= MAIN =========

def main():
    st.set_page_config(
        page_title="NPS Accounting System",
        page_icon="💼",
        layout="wide",
    )

    inject_global_css()
    init_db()

    st.sidebar.markdown(
        """
        <div class="sidebar-title">💼 NPS Accounting</div>
        <div class="sidebar-subtitle">FM &amp; MEP Internal Finance</div>
        <hr style="border-color: rgba(148,163,184,0.4); margin: 0.4rem 0 0.8rem 0;">
        """,
        unsafe_allow_html=True,
    )

    menu_items = {
        "Dashboard": "📊 Dashboard",
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
