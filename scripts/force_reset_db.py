
import sqlite3

DB_PATH = "autopack.db"
RUN_ID = "fileorg-test-verification-2025-11-29"

def force_reset():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Inspect schema
    cursor.execute("PRAGMA table_info(phases)")
    columns = cursor.fetchall()
    print("Schema:", [col[1] for col in columns])
    
    # List all runs
    print("Listing all runs in DB:")
    cursor.execute("SELECT DISTINCT run_id FROM phases")
    runs = cursor.fetchall()
    for run in runs:
        print(f"  - {run[0]}")
    
    conn.close()

if __name__ == "__main__":
    force_reset()

