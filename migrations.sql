-- Projects
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

-- Cash book
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

-- Invoices
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

-- Debts & Fixed Assets
CREATE TABLE IF NOT EXISTS debts_fixed (
    id SERIAL PRIMARY KEY,
    type TEXT,               -- 'Debt' or 'Fixed Asset'
    name TEXT,
    project_code TEXT,
    amount NUMERIC(18,2),
    start_date DATE,
    remarks TEXT
);

-- People
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

-- Visas
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

-- Tickets
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

-- Accounts (chart of accounts)
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT,
    type TEXT
);

-- Journal entries
CREATE TABLE IF NOT EXISTS journal (
    id SERIAL PRIMARY KEY,
    date DATE,
    account_code TEXT,
    description TEXT,
    debit NUMERIC(18,2),
    credit NUMERIC(18,2),
    ref TEXT
);
