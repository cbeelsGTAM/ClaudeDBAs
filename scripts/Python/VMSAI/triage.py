import json
import os
import sys
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import sqlalchemy
from Utility.vault import Vault


def get_connection_string(env: str) -> str:
    vault = Vault()
    server = vault.get_value(system="AIServices", environment=env, key="SRV")
    database = vault.get_value(system="AIServices", environment=env, key="DB")
    return f"mssql+pyodbc://@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"


def classify_issue(row: dict) -> str:
    vendor = row.get("VendorName") or ""
    run_cmd = row.get("RunCmd") or ""
    contract = row.get("Contract")
    workflow = row.get("Workflow")
    set_workflow = row.get("SetWorkflow")
    same_number_link = row.get("SameNumberLink")

    if vendor == "NONINVOICE":
        return "non-invoice"
    if "No Invoice Number" in run_cmd:
        return "no-invoice-number"
    if "VendorAlias" in run_cmd:
        return "vendor-not-found"
    if same_number_link:
        return "duplicate-number"
    if contract is None and set_workflow is None:
        return "no-contract"
    if workflow is None and set_workflow is not None:
        return "no-workflow"
    return "ready"


def fetch_queue(conn_str: str) -> list:
    engine = sqlalchemy.create_engine(conn_str)
    with engine.begin() as conn:
        df = pd.read_sql("EXEC [REPORT].[ReadyInvoiceReport]", con=conn)
    df = df.where(pd.notna(df), None)
    rows = df.to_dict(orient="records")
    for row in rows:
        row["_issue"] = classify_issue(row)
    return rows


def run_sql(conn_str: str, sql: str) -> str:
    engine = sqlalchemy.create_engine(conn_str)
    with engine.begin() as conn:
        result = conn.execute(sqlalchemy.text(sql))
        try:
            rows = result.fetchall()
            if rows:
                cols = list(result.keys())
                return json.dumps([dict(zip(cols, r)) for r in rows], default=str, indent=2)
        except Exception:
            pass
    return "OK"


def main():
    parser = argparse.ArgumentParser(description="VMS Invoice Triage")
    parser.add_argument("--env", choices=["qa", "prod"], default="prod")
    parser.add_argument("--exec", dest="sql", metavar="SQL", help="Execute a SQL statement")
    args = parser.parse_args()

    conn_str = get_connection_string(args.env)

    if args.sql:
        print(run_sql(conn_str, args.sql))
    else:
        rows = fetch_queue(conn_str)
        print(json.dumps(rows, default=str, indent=2))


if __name__ == "__main__":
    main()
