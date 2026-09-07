"""
Upgrades musabaqa.db to the official 2026 Kenya Quran Competition Rubric:
- Adds question_number column to deduction_events if missing.
- Creates round_questions table if missing.
- Configures scoring_criteria:
    Memorization: 70.0 pts
    Tajweed & Performance: 30.0 pts
- Configures deduction_types:
    تنبيه (Tanbeeh): 1.0
    الفتح (Al-Fath): 2.0
    اللحن (Al-Lahn): 2.0
    خطأ في التجويد (Tajweed Error): 0.5
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "musabaqa.db")

def upgrade():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 1. Add question_number to deduction_events if not present
    cur.execute("PRAGMA table_info(deduction_events)")
    cols = [col[1] for col in cur.fetchall()]
    if "question_number" not in cols:
        print("Adding question_number to deduction_events...")
        cur.execute("ALTER TABLE deduction_events ADD COLUMN question_number INTEGER DEFAULT 1")

    # 2. Create round_questions table if not present
    cur.execute("""
    CREATE TABLE IF NOT EXISTS round_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        question_number INTEGER NOT NULL DEFAULT 1,
        envelope_number TEXT,
        surah_name TEXT,
        ayah_from INTEGER,
        ayah_to INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(round_id) REFERENCES rounds(id),
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_round_questions_round_id ON round_questions (round_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_round_questions_student_id ON round_questions (student_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_round_questions_question_number ON round_questions (question_number)")

    # 3. Update or recreate scoring_criteria and deduction_types
    # Get distinct category groups
    cur.execute("SELECT DISTINCT category_group FROM categories")
    groups = [r[0] for r in cur.fetchall()]
    if not groups:
        groups = ["JUZ_10_15_20", "JUZ_30"]

    print(f"Updating scoring criteria for category groups: {groups}")

    for grp in groups:
        # Check if Memorization exists
        cur.execute("SELECT id FROM scoring_criteria WHERE category_group = ? AND name_en = 'Memorization'", (grp,))
        mem_row = cur.fetchone()
        if mem_row:
            mem_id = mem_row[0]
            cur.execute("UPDATE scoring_criteria SET max_points = 70.0, name_ar = 'الحفظ' WHERE id = ?", (mem_id,))
        else:
            cur.execute("""
            INSERT INTO scoring_criteria (category_group, name_en, name_ar, max_points, scoring_method)
            VALUES (?, 'Memorization', 'الحفظ', 70.0, 'DEDUCTION_BASED')
            """, (grp,))
            mem_id = cur.lastrowid

        # Check if Tajweed exists
        cur.execute("SELECT id FROM scoring_criteria WHERE category_group = ? AND name_en = 'Tajweed'", (grp,))
        taj_row = cur.fetchone()
        if taj_row:
            taj_id = taj_row[0]
            cur.execute("UPDATE scoring_criteria SET max_points = 30.0, name_ar = 'التجويد وحسن الصوت والأداء' WHERE id = ?", (taj_id,))
        else:
            cur.execute("""
            INSERT INTO scoring_criteria (category_group, name_en, name_ar, max_points, scoring_method)
            VALUES (?, 'Tajweed', 'التجويد وحسن الصوت والأداء', 30.0, 'DEDUCTION_BASED')
            """, (grp,))
            taj_id = cur.lastrowid

        # Delete any other criteria for this group (like Saut 20, Tafsir 10) so total is exactly 100
        cur.execute("SELECT id FROM scoring_criteria WHERE category_group = ? AND id NOT IN (?, ?)", (grp, mem_id, taj_id))
        obsolete_crit_ids = [r[0] for r in cur.fetchall()]
        for ob_id in obsolete_crit_ids:
            cur.execute("DELETE FROM deduction_types WHERE scoring_criteria_id = ?", (ob_id,))
            cur.execute("DELETE FROM scoring_criteria WHERE id = ?", (ob_id,))

        # Now configure deduction types for Memorization:
        # Tanbeeh (-1.0), Al-Fath (-2.0), Al-Lahn (-2.0)
        # Clear old deduction types for this mem_id
        cur.execute("DELETE FROM deduction_types WHERE scoring_criteria_id = ?", (mem_id,))
        cur.execute("""
        INSERT INTO deduction_types (scoring_criteria_id, name_en, name_ar, points_deducted)
        VALUES 
        (?, 'Tanbeeh (Warning)', 'التنبيه', 1.0),
        (?, 'Al-Fath (Prompting)', 'الفتح', 2.0),
        (?, 'Al-Lahn (Vocalization Error)', 'اللحن', 2.0)
        """, (mem_id, mem_id, mem_id))

        # Configure deduction types for Tajweed:
        # Tajweed Error (-0.5)
        cur.execute("DELETE FROM deduction_types WHERE scoring_criteria_id = ?", (taj_id,))
        cur.execute("""
        INSERT INTO deduction_types (scoring_criteria_id, name_en, name_ar, points_deducted)
        VALUES 
        (?, 'Tajweed Error', 'خطأ في التجويد', 0.5)
        """, (taj_id,))

    con.commit()
    print("Database upgrade to official rubric completed successfully!")
    con.close()

if __name__ == "__main__":
    upgrade()
