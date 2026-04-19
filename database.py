import os
import psycopg2
from psycopg2.extras import DictCursor

def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: DATABASE_URL not found. Database functionality will fail if not deployed on Railway with DB attached.")
        return None
    return psycopg2.connect(db_url, cursor_factory=DictCursor)

def init_db():
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            # 建立使用者表
            # user_id: Line User ID
            # current_mode: AI 或 HUMAN
            # usage_month: 紀錄當前使用月份 (格式 'YYYY-MM')
            # usage_count: 該月份已使用次數
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    current_mode TEXT DEFAULT 'HUMAN',
                    usage_month TEXT,
                    usage_count INTEGER DEFAULT 0
                )
            ''')
        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Database initialization error: {e}")
    finally:
        conn.close()

def get_user_mode(user_id):
    conn = get_connection()
    if not conn:
        return "HUMAN"  # 預設為 HUMAN
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_mode FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                return row['current_mode']
            return "HUMAN"
    finally:
        conn.close()

def set_user_mode(user_id, mode):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, current_mode)
                VALUES (%s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET current_mode = EXCLUDED.current_mode
            """, (user_id, mode))
        conn.commit()
    finally:
        conn.close()

def get_usage(user_id, month_str):
    conn = get_connection()
    if not conn:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT usage_month, usage_count FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            
            if row:
                if row['usage_month'] == month_str:
                    return row['usage_count'] or 0
                else:
                    # 跨月了，額度歸零
                    cur.execute("UPDATE users SET usage_month = %s, usage_count = 0 WHERE user_id = %s", (month_str, user_id))
                    conn.commit()
                    return 0
            else:
                # 新用戶，沒有記錄
                return 0
    finally:
        conn.close()

def increment_usage(user_id, month_str):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, usage_month, usage_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    usage_month = EXCLUDED.usage_month,
                    usage_count = CASE 
                        WHEN users.usage_month = EXCLUDED.usage_month THEN users.usage_count + 1 
                        ELSE 1 
                    END
            """, (user_id, month_str))
        conn.commit()
    finally:
        conn.close()
