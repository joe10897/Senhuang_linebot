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
            # 擴充新欄位: 購買額度
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS purchased_quota INTEGER DEFAULT 0;")
            # 擴充新欄位: 會員等級
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'FREE';")
            # 擴充新欄位: 訂閱到期日
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expiry TEXT;")
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

def get_user_status_data(user_id, month_str):
    """取得用戶詳細狀態、月用量與相關配額，用於主邏輯判斷"""
    conn = get_connection()
    if not conn:
        return {"tier": "FREE", "free_limit": 3, "usage": 0, "purchased": 0, "current_mode": "HUMAN"}
    try:
        with conn.cursor() as cur:
            # 確認用戶存在
            cur.execute("SELECT current_mode, usage_month, usage_count, purchased_quota, subscription_tier, subscription_expiry FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            
            if not row:
                return {"tier": "FREE", "free_limit": 3, "usage": 0, "purchased": 0, "current_mode": "HUMAN"}
            
            tier = row['subscription_tier'] or 'FREE'
            expiry = row['subscription_expiry']
            
            import datetime
            if expiry:
                try:
                    exp_date = datetime.datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S')
                    if datetime.datetime.now() > exp_date:
                        tier = 'FREE' # 過期退回 FREE
                except:
                    pass

            # 計算當前等級的免費上限
            limits = {'FREE': 3, 'BASIC': 15, 'ADVANCED': 100, 'BUSINESS': 1000}
            free_limit = limits.get(tier, 3)

            # 跨月重置邏輯
            usage = row['usage_count'] or 0
            if row['usage_month'] != month_str:
                usage = 0
                cur.execute("UPDATE users SET usage_month = %s, usage_count = 0 WHERE user_id = %s", (month_str, user_id))
                conn.commit()

            return {
                "tier": tier,
                "free_limit": free_limit,
                "usage": usage,
                "purchased": row['purchased_quota'] or 0,
                "current_mode": row['current_mode'] or "HUMAN",
                "expiry": expiry
            }
    finally:
        conn.close()

def consume_quota(user_id, month_str):
    """
    動態扣除額度 (優先扣月免費、再扣買斷額度)
    回傳: (is_success, 剩餘月免費用量, 剩餘買斷額度)
    """
    conn = get_connection()
    if not conn:
        return (False, 0, 0)
    try:
        # 先取得狀態
        data = get_user_status_data(user_id, month_str)
        free_limit = int(data.get("free_limit", 3))
        usage = int(data.get("usage", 0))
        purchased = int(data.get("purchased", 0))
        
        # 1. 判斷是否有免費額度可扣
        if usage < free_limit:
            new_usage = usage + 1
            new_purchased = purchased
        # 2. 無料可扣，判斷是否有付費額度可扣
        elif purchased > 0:
            new_usage = usage
            new_purchased = purchased - 1
        # 3. 皆無額度
        else:
            return (False, 0, 0)

        # 更新資料庫
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET usage_count = %s, purchased_quota = %s
                WHERE user_id = %s
            """, (new_usage, new_purchased, user_id))
        conn.commit()
        
        return (True, max(0, free_limit - new_usage), new_purchased)
    finally:
        conn.close()

def add_purchased_quota(user_id, amount):
    """由綠界 Webhook 若訂單是購買單次額度時呼叫"""
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, purchased_quota)
                VALUES (%s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET purchased_quota = users.purchased_quota + EXCLUDED.purchased_quota
            """, (user_id, amount))
        conn.commit()
    finally:
        conn.close()

def update_subscription(user_id, tier, expiry_str_or_add_months=1):
    """由綠界 Webhook 若訂單是訂閱/包月時呼叫"""
    import datetime
    
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            # 簡單實作：目前直接把時間往後加一個月 (30天)
            now = datetime.datetime.now()
            next_month = now + datetime.timedelta(days=30)
            expiry_str = next_month.strftime('%Y-%m-%d %H:%M:%S')

            cur.execute("""
                INSERT INTO users (user_id, subscription_tier, subscription_expiry)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    subscription_tier = EXCLUDED.subscription_tier,
                    subscription_expiry = EXCLUDED.subscription_expiry
            """, (user_id, tier, expiry_str))
        conn.commit()
    finally:
        conn.close()
