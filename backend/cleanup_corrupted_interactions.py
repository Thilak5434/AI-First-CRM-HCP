"""
Removes any interaction records whose topics_discussed field accidentally got
a JSON blob stuffed into it (a symptom of the duplicate log_interaction bug).
Safe to run anytime - only deletes rows where topics_discussed starts with '{'.

Usage (run from your backend folder, with DATABASE_URL set in .env):
    python cleanup_corrupted_interactions.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./hcp_crm.db"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT id, hcp_id, topics_discussed FROM interactions WHERE topics_discussed LIKE '{%'"
    ))
    rows = result.fetchall()
    if not rows:
        print("No corrupted interactions found.")
    else:
        print(f"Found {len(rows)} corrupted interaction(s):")
        for r in rows:
            print(f"  id={r[0]} hcp_id={r[1]} topics_discussed={r[2][:80]}...")
        confirm = input("Delete these rows? (y/n): ")
        if confirm.lower() == "y":
            ids = [r[0] for r in rows]
            conn.execute(text("DELETE FROM interactions WHERE id = ANY(:ids)") if DATABASE_URL.startswith("postgresql")
                         else text(f"DELETE FROM interactions WHERE id IN ({','.join(map(str, ids))})"),
                         {"ids": ids} if DATABASE_URL.startswith("postgresql") else {})
            conn.commit()
            print(f"Deleted {len(ids)} row(s).")
        else:
            print("Aborted, nothing deleted.")
