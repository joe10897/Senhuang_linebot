import os
import sys

# 修正中文路徑導致的 SSL 憑證抓取失敗問題
try:
    import certifi
    import ssl
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    # 強制重啟全域 SSL 環境，避免舊路徑快取
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    StickerMessage
)
from linebot.models import FlexSendMessage, CarouselContainer, BubbleContainer, BoxComponent, TextComponent, SeparatorComponent
import google.generativeai as genai
def get_price_flex():
    """產生價目表的 Flex Message 物件"""
    
    # --- 卡片 1: 佛牌與玉器 ---
    bubble_1 = BubbleContainer(
        header=BoxComponent(
            layout='vertical',
            background_color='#2c3e50', # 深藍色背景
            contents=[
                TextComponent(text='💎 佛牌與玉器', weight='bold', size='xl', color='#ffffff')
            ]
        ),
        body=BoxComponent(
            layout='vertical',
            contents=[
                # 佛牌
                TextComponent(text='古佛牌', weight='bold', size='md', color='#1DB446'),
                BoxComponent(layout='baseline', contents=[
                    TextComponent(text='鑑定費', size='sm', color='#555555', flex=1),
                    TextComponent(text='NT$ 3,800', size='sm', color='#111111', align='end', flex=2)
                ]),
                TextComponent(text='(約 USD 128)', size='xs', color='#aaaaaa', align='end'),
                SeparatorComponent(margin='md'),
                
                # 玉器
                BoxComponent(layout='vertical', margin='md', contents=[
                    TextComponent(text='古玉器 (清中期前)', weight='bold', size='md', color='#1DB446'),
                    BoxComponent(layout='baseline', contents=[
                        TextComponent(text='鑑定費', size='sm', color='#555555', flex=1),
                        TextComponent(text='NT$ 4,800', size='sm', color='#111111', align='end', flex=2)
                    ]),
                    TextComponent(text='(約 USD 165)', size='xs', color='#aaaaaa', align='end'),
                ])
            ]
        )
    )

    # --- 卡片 2: 古銅器 ---
    bubble_2 = BubbleContainer(
        header=BoxComponent(
            layout='vertical',
            background_color='#8e44ad', # 紫色背景
            contents=[
                TextComponent(text='⚱️ 古銅器', weight='bold', size='xl', color='#ffffff')
            ]
        ),
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(text='金屬器/青銅/佛像', weight='bold', size='md', color='#8e44ad'),
                SeparatorComponent(margin='md'),
                # 中小型
                BoxComponent(layout='baseline', margin='md', contents=[
                    TextComponent(text='中小型', size='sm', weight='bold', flex=1),
                    TextComponent(text='< 15cm', size='xs', color='#aaaaaa', align='end', flex=1)
                ]),
                TextComponent(text='NT$ 2,800', size='md', color='#111111', align='end'),
                
                # 大型
                BoxComponent(layout='baseline', margin='md', contents=[
                    TextComponent(text='大型', size='sm', weight='bold', flex=1),
                    TextComponent(text='> 16cm', size='xs', color='#aaaaaa', align='end', flex=1)
                ]),
                TextComponent(text='NT$ 4,800', size='md', color='#111111', align='end'),
            ]
        )
    )

    # --- 卡片 3: 古瓷器 (比較複雜) ---
    bubble_3 = BubbleContainer(
        header=BoxComponent(
            layout='vertical',
            background_color='#c0392b', # 紅色背景
            contents=[
                TextComponent(text='🏺 古瓷器特惠', weight='bold', size='xl', color='#ffffff')
            ]
        ),
        body=BoxComponent(
            layout='vertical',
            contents=[
                # 小型
                BoxComponent(layout='baseline', contents=[
                    TextComponent(text='小型 (<15cm)', size='xs', color='#555555', flex=4),
                    TextComponent(text='NT$ 5,700', size='sm', weight='bold', color='#c0392b', align='end', flex=3)
                ]),
                TextComponent(text='(原價 $9,600)', size='xxs', color='#aaaaaa', decoration='line-through', align='end'),
                SeparatorComponent(margin='sm'),

                # 中型
                BoxComponent(layout='baseline', margin='sm', contents=[
                    TextComponent(text='中型 (15-30cm)', size='xs', color='#555555', flex=4),
                    TextComponent(text='NT$ 7,500', size='sm', weight='bold', color='#c0392b', align='end', flex=3)
                ]),
                TextComponent(text='(原價 $12,000)', size='xxs', color='#aaaaaa', decoration='line-through', align='end'),
                SeparatorComponent(margin='sm'),

                # 中大型
                BoxComponent(layout='baseline', margin='sm', contents=[
                    TextComponent(text='中大型 (30-50cm)', size='xs', color='#555555', flex=4),
                    TextComponent(text='NT$ 9,600', size='sm', weight='bold', color='#c0392b', align='end', flex=3)
                ]),
                TextComponent(text='(原價 $16,000)', size='xxs', color='#aaaaaa', decoration='line-through', align='end'),
                
                TextComponent(text='* >51cm 暫不收檢', margin='md', size='xs', color='#aaaaaa', style='italic'),
            ]
        )
    )

    return FlexSendMessage(
        alt_text="東方森煌價目表",
        contents=CarouselContainer(contents=[bubble_1, bubble_2, bubble_3])
    )

def get_subscription_flex(host, user_id):
    """產生包含 ECPay 付款連結的多層級訂閱方案 Flex Message"""
    from linebot.models import URIAction, ButtonComponent
    
    def make_plan_bubble(color, title, desc1, desc2, price, price_desc, plan_id):
        payment_url = f"{host}/buy/{user_id}/{plan_id}"
        return BubbleContainer(
            header=BoxComponent(
                layout='vertical',
                background_color=color,
                contents=[TextComponent(text=title, weight='bold', size='xl', color='#ffffff')]
            ),
            body=BoxComponent(
                layout='vertical',
                contents=[
                    TextComponent(text=desc1, weight='bold', size='md', color=color),
                    TextComponent(text=desc2, size='sm', color='#555555', wrap=True),
                    SeparatorComponent(margin='md'),
                    BoxComponent(layout='baseline', margin='md', contents=[
                        TextComponent(text=price, size='lg', weight='bold', color='#111111', flex=1),
                        TextComponent(text=price_desc, size='xs', color='#aaaaaa', align='end', flex=1)
                    ]),
                ]
            ),
            footer=BoxComponent(
                layout='vertical',
                contents=[
                    ButtonComponent(
                        style='primary',
                        color=color,
                        action=URIAction(label='前往付款', uri=payment_url)
                    )
                ]
            )
        )

    b1 = make_plan_bubble('#f39c12', '🪙 單筆儲值', '10 次健檢點數', '永久有效，不會過期', 'NT$ 100', '一次購買', 'point10')
    b2 = make_plan_bubble('#27ae60', '🌱 小資玩家', '單月 15 次健檢', '人工鑑定單次折 100 元', 'NT$ 120', '買斷30天', 'basic_single')
    b3 = make_plan_bubble('#2980b9', '👑 進階藏家', '單月 100 次健檢', '人工鑑定單次折 200 元', 'NT$ 500', '買斷30天', 'advanced_single')
    b4 = make_plan_bubble('#8e44ad', '💎 商務旗艦', '單月 1000 次', '人工鑑定單次折 300 元', 'NT$ 1500', '買斷30天', 'business_single')

    return FlexSendMessage(
        alt_text="東方森煌館 付費與訂閱方案",
        contents=CarouselContainer(contents=[b1, b2, b3, b4])
    )
app = Flask(__name__)

from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 1. 設定區 (請填入你的 Key)
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 記憶體與 PostgreSQL 資料庫
# ==========================================
import database
database.init_db()

# 記錄 Gemini 的對話歷史物件 (短暫對話暫存，維持在記憶體)
chat_sessions = {}
# 暫存用戶上傳的照片 (防呆機制，短暫資料)
user_images = {}
MONTHLY_LIMIT = 8

# ==========================================
# 3. Gemini 模型設定 (東方森煌專屬人設)
# ==========================================
SYSTEM_PROMPT = """
你現在是【東方森煌古文物鑑定中心】的智能客服。
語氣：專業、穩重、客觀、有禮貌。

【核心資訊】
1. 服務項目：古玉器、古佛牌、古陶瓷、青銅器、金銅器物的專業鑑定

2. 收費標準：
   - 古佛牌：TWD 3,800 / USD 128
   - 古玉器：TWD 4,800 / USD 165
   - 古銅器：中小型(<15cm) TWD 2,800；大型(>16cm) TWD 4,800
   - 古瓷器：小型(<15cm) 特惠 TWD 5,700（原 9,600）；中型(15-30cm) 特惠 TWD 7,500（原 12,000）；中大型(30-50cm) 特惠 TWD 9,600（原 16,000）；大型(>51cm) 暫不收檢

3. 流程：預約 → 攜帶/寄送物件 → 專家初判 → 鑑定（約7~14工作天）→ 結果通知 → 寄回（真品附鑑定卡）

4. 聯絡資訊：
   地址：236新北市土城區中央路二段191號7樓之4
   電話：02-8260-2664
   營業：週一至週五 10:00–18:00，週六日休息

5. 可受理佛牌（佛曆2525/A.D.1982以前）：
阿贊多：瓦拉康崇迪、給猜優崇迪、玉佛寺佛牌（全系列）
阿贊添：龍普托（全系列）
龍婆班：神獸崇迪（全系列）
龍婆銀：2460財佛小立尊、2460大鋤頭、2460小鋤頭
龍婆BOON：兆索佛（第一期）
龍婆添：2515~2517 帕坤平古曼大模/小模、自身像、必打
龍婆多：2520~2522 必打（全系列）
出土類五大古佛、南奔出塔老佛牌
其他品項歡迎來信洽詢。

6. 可受理玉器（清中期乾隆/A.D.1796以前）：
文化期、商周、春秋戰國、漢~六朝、隋唐、宋元、明清；其他歡迎洽詢。

7. 可受理古金屬器：漢代以前青銅器、清代以前西藏天鐵天銅、清代以前藏傳金屬法器/法印/金銅佛像；其他歡迎洽詢。

8. 可受理古陶瓷：彩陶文化期以後古陶器、漢唐彩釉古瓷、宋元明清各類古瓷器；其他歡迎洽詢。

【AI文物健檢規則與原則】
# Role
你是「東方森煌古物鑑定所」的專屬 LINE 客服機器人，執行「智能文物健檢 (A.A.D)」服務，透過照片與文字進行初步特徵分析與真偽過濾，給予市場估價，引導有潛力的物件進行實體預約送檢。

# 拒絕條款
若照片明顯不屬於可鑑定範疇（如人體照片、書畫字帖、現代珠寶鑽石、鑑定報告文件等），請直接回覆：
「您所上傳的照片不在檢測項目內，請重新上傳其他照片，或洽真人客服。」

# Core Rules
1. 【絕對禁語】：絕不直接下達「這是真品」或「這是贗品」的絕對性結論。
2. 【機率限制】：以「真品機率百分比」表達結論，範圍限制在 25%~95%。
3. 【單一物件原則】：提醒使用者，單次上傳多張照片必須是同一件物品。
4. 【市場估價原則】：必須提供市場價值估算，前提為「假設此件物品為真品」。

# Response Format（依序輸出，不可省略）
## 1. 提醒（固定輸出）
「歡迎使用智能文物健檢 (A.A.D)！
📌 提醒：請確認您上傳的一組照片，皆屬於同一件物件。」

## 2. 物件特徵初步分析
（客觀描述照片中的器形、紋飾、皮殼、釉色或工藝特徵，指出符合或不符合時代特徵的地方。限制不要超過300字）

## 3. A.A.D 健檢機率結論
格式：「綜合以上特徵比對，本件物件的真品機率評估為：[數字]%。」

## 4. 市場價值預估
格式：「若本件物品經實體儀器與專家確認為真品，其當前市場參考價值約落在 [金額區間]。」

## 5. 後續送檢建議
- 機率 > 65%：「此物件具備較高的時代特徵與研究價值。建議您點擊下方選單的『人工預約』，交由東方森煌古物鑑定所進行實體儀器檢測與專家判定，以獲取正式鑑定報告。」
- 機率 50%~65%：「此物件特徵好壞參半。若您對此物件有特殊情感或想進一步釐清，可考慮預約實體送檢。」
- 機率 < 50%：「此物件的現代工藝或仿製特徵較為明顯，目前不建議您花費成本進行實體送檢。建議作為一般工藝品欣賞即可。」

## 6. 系統警語（固定輸出，置於篇末）
「⚠️ 警語：A.D.D. 乃基於 Gemini 全球資料庫以及市場實戰調校，然僅以照片判斷仍有一定誤差。雖優於個人 AI 客觀性，但尚不具備完整鑑定效益，僅供過濾及輔助使用。」
"""

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "temperature": 0.2, # 低隨機性，保持專業
        "max_output_tokens": 3000,
    },
    system_instruction=SYSTEM_PROMPT
)

# ==========================================
# 4. Webhook 入口
# ==========================================
@app.route("/intro")
def intro():
    try:
        with open("intro.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error loading intro.html: {e}", 404

@app.route("/callback", methods=['POST'])
def callback():
    import threading
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 在背景執行緒處理事件，立刻回傳 200 給 LINE
    # 這樣 LINE 不會因為 Gemini API 耗時而重送 webhook
    def process():
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            app.logger.error("Invalid webhook signature")
        except Exception as e:
            app.logger.error(f"Background handler error: {e}")

    threading.Thread(target=process, daemon=True).start()
    return 'OK'

@app.route("/buy/<user_id>/<plan_id>")
def buy(user_id, plan_id):
    plans = {
        "point10": {"amount": 100, "desc": "購買 10 次健檢額度點數"},
        "basic_single": {"amount": 120, "desc": "訂閱單月 小資玩家 (15次/月)"},
        "advanced_single": {"amount": 500, "desc": "訂閱單月 進階藏家 (100次/月)"},
        "business_single": {"amount": 1500, "desc": "訂閱單月 商務旗艦 (1000次/月)"}
    }
    if plan_id not in plans:
        return "Invalid Plan", 400
    
    amount = plans[plan_id]["amount"]
    desc = plans[plan_id]["desc"]
    
    import uuid
    import ecpay_integration
    # MerchantTradeNo 綠界規定必須唯一且最長20碼
    order_id = "AAD" + uuid.uuid4().hex[:17]
    
    # 將 user_id 和 plan_id 用 "|" 符號裝進 CustomField1 內傳遞給綠界
    custom_field = f"{user_id}|{plan_id}"
    
    # 動態取得伺服器域名作為 Return URL (必須是 HTTPS，否則綠界不會發送 webhook)
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        host = f"https://{railway_domain}"
    else:
        host = request.host_url.rstrip("/")
        
    return_url = f"{host}/ecpay/return"
    client_back_url = "line://app" 
    
    html = ecpay_integration.generate_ecpay_html_form(
        order_id, custom_field, amount, desc, return_url, client_back_url
    )
    return html

@app.route("/ecpay/return", methods=["POST"])
def ecpay_return():
    import ecpay_integration
    import database
    
    if not ecpay_integration.verify_ecpay_callback(request.form):
        return "0|CheckMacValue Error", 400
        
    rtn_code = request.form.get("RtnCode")
    if rtn_code == "1":
        # 交易成功
        custom_field = request.form.get("CustomField1", "")
        parts = custom_field.split("|")
        if len(parts) == 2:
            user_id, plan_id = parts
            
            if plan_id == "point10":
                database.add_purchased_quota(user_id, 10)
                msg_text = "🎉 感謝購買！您的 10 次額度已入帳 (永久有效)。\n現在您可以繼續傳送照片進行智能文物健檢！"
            elif plan_id == "basic_single":
                database.update_subscription(user_id, "BASIC")
                msg_text = "🎉 感謝訂閱！升級為「小資玩家」，本月擁有 15 次智能健檢，且人工鑑定折抵 100 元！"
            elif plan_id == "advanced_single":
                database.update_subscription(user_id, "ADVANCED")
                msg_text = "🎉 感謝訂閱！升級為「進階藏家」，本月擁有 100 次智能健檢，且人工鑑定折抵 200 元！"
            elif plan_id == "business_single":
                database.update_subscription(user_id, "BUSINESS")
                msg_text = "🎉 感謝訂閱！升級為「商務旗艦」，本月擁有 1000 次智能健檢，且人工鑑定折抵 300 元！"
                
            # 取得最新額度資訊並附加在訊息後方
            from datetime import datetime
            now = datetime.now()
            month_str = f"{now.year}-{now.month:02d}"
            user_state = database.get_user_status_data(user_id, month_str)
            free_limit = int(user_state.get('free_limit', 3))
            usage = int(user_state.get('usage', 0))
            purchased = int(user_state.get('purchased', 0))
            tier = user_state.get('tier', 'FREE')
            
            rem_free = max(0, free_limit - usage)
            
            msg_text += f"\n\n---\n📊 目前最新額度狀態：\n⭐ 會員方案：{tier}\n🎁 當月方案額度剩餘：{rem_free} 次\n🪙 終身可用儲值點數：{purchased} 點"
            
            # 主動推播給消費者
            try:
                line_bot_api.push_message(user_id, TextSendMessage(text=msg_text))
            except Exception as e:
                app.logger.error(f"Push message failed: {e}")
                
    return "1|OK"

# ==========================================
# 5. 訊息處理邏輯
# ==========================================

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_msg = event.message.text.strip()
    # 1. 關鍵字觸發：價目表 (優先攔截)
    # 只要訊息包含這些字，就直接丟漂亮的卡片，不經過 Gemini
    price_keywords = ["收費", "費用", "價錢", "價目", "多少錢", "價格"]
    if any(k in user_msg for k in price_keywords):
        flex_msg = get_price_flex() # 呼叫剛剛寫好的函式
        line_bot_api.reply_message(event.reply_token, flex_msg)
        return
        
    buy_keywords = ["購買", "儲值", "點數", "方案", "付費", "訂閱"]
    if any(k in user_msg for k in buy_keywords):
        # 解決 Flask Context 失效問題 (這是背景執行緒)
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        if railway_domain:
            host = f"https://{railway_domain}"
        else:
            host = "http://localhost:8080" # 備用
            
        flex_msg = get_subscription_flex(host, user_id)
        line_bot_api.reply_message(event.reply_token, flex_msg)
        return
        
    quota_keywords = ["查詢額度", "額度", "我的狀態", "會員狀態"]
    if any(k in user_msg for k in quota_keywords):
        from datetime import datetime
        now = datetime.now()
        month_str = f"{now.year}-{now.month:02d}"
        
        user_state = database.get_user_status_data(user_id, month_str)
        free_limit = int(user_state.get('free_limit', 3))
        usage = int(user_state.get('usage', 0))
        purchased = int(user_state.get('purchased', 0))
        tier = user_state.get('tier', 'FREE')
        expiry = user_state.get('expiry', '無') or '無'
        
        rem_free = max(0, free_limit - usage)
        discounts = {'FREE': '無折扣', 'BASIC': '折抵 100 元', 'ADVANCED': '折抵 200 元', 'BUSINESS': '折抵 300 元'}
        disc_text = discounts.get(tier, '無折扣')
        
        msg_text = (
            f"👤 您的會員狀態：\n"
            f"🔸 當前方案：{tier}\n"
            f"🔸 包月到期日：{expiry}\n"
            f"🔸 預約人工鑑定專屬折扣：{disc_text}\n\n"
            f"📊 您的健檢剩餘可用額度：\n"
            f"🎁 本月專屬額度：{rem_free} / {free_limit} 次\n"
            f"🪙 永久買斷點數：{purchased} 點\n\n"
            f"💡 若額度不足，請輸入「購買」瀏覽升級方案。"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text))
        return
        
    # 1. 偵測是否要「切換人工」 (配合你的圖文選單按鈕)
    if user_msg in ["人工預約", "人工客服", "專人服務","真人客服"]:
        database.set_user_mode(user_id, "HUMAN")
        msg = "👨‍💼 已為您轉接人工預約服務。\n\n請直接留言您的需求，我們會盡快回覆您。\n\n(若需回到 AI 模式，請點擊選單「AI文物健檢」)"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # 2. 偵測是否要「切換回 AI」
    elif user_msg in ["AI文物健檢", "結束專人", "開啟智能客服"]:
        database.set_user_mode(user_id, "AI")
        msg = (
            "🤖 歡迎使用【AI文物健檢】服務！\n\n"
            "請直接傳送您的「物件照片」與「文字說明」，我將為您進行初步分析。\n\n"
            "⚠️ 【重要提醒】\n"
            "1. AI文物健檢乃基於資料庫與市場資訊，仍有較高誤差值，不具任何鑑定效益，僅供藏家初步過濾使用。\n"
            "2. 單次上傳的照片，請確保只包含「同一件」物件，以免造成AI誤判。\n\n"
            "若AI評估機率較高，建議您後續點選「人工預約」進行實體鑑定！"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # 3. 核心邏輯：預設為 HUMAN（靜音），需主動點選「AI文物健檢」才啟用 AI
    current_mode = database.get_user_mode(user_id)

    if current_mode == "HUMAN":
        # 「開始健檢」特例：提示用戶先啟動 AI 服務
        if user_msg == "開始健檢":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ 請先點選選單中的「AI文物健檢」以啟動服務，再上傳照片並輸入『開始健檢』。")
            )
            return
        # 其他訊息：人工模式下完全靜音，讓真人透過 LINE 後台回覆
        print(f"人工模式中，忽略訊息: {user_msg}")
        return

    elif current_mode == "AI":
        # --- 新增防呆機制：觸發健檢 ---
        if user_msg == "開始健檢":
            # 檢查是否有上傳照片
            if user_id not in user_images or len(user_images[user_id]) == 0:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您尚未上傳任何照片。\n\n請先傳送物件照片，再輸入『開始健檢』。"))
                return
            
            # ---- 額度檢查 ----
            from datetime import datetime
            now = datetime.now()
            month_str = f"{now.year}-{now.month:02d}"
            
            user_state = database.get_user_status_data(user_id, month_str)
            free_limit = int(user_state.get('free_limit', 3))
            usage = int(user_state.get('usage', 0))
            purchased = int(user_state.get('purchased', 0))
            tier = user_state.get('tier', 'FREE')
            
            if usage >= free_limit and purchased <= 0:
                host = request.host_url.rstrip("/")
                flex_msg = get_subscription_flex(host, user_id)
                line_bot_api.reply_message(
                    event.reply_token,
                    [
                        TextSendMessage(text="⚠️ 您的健檢額度已用盡，請參考以下方案擴充您的額度："),
                        flex_msg
                    ]
                )
                return
            
            try:
                # 告知用戶正在處理
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🔍 系統正在分析您的照片，請稍候... (您的方案：{tier})"))
                
                # 圖片分析改用 generate_content
                prompt = "請根據這些照片，嚴格依照【AI文物健檢規則與原則】與【Response Format】進行分析。"
                payload = [prompt] + user_images[user_id]
                
                response = model.generate_content(
                    payload,
                    request_options={"timeout": 55}  # 55秒後強制停止，避免 Gunicorn worker 被 SIGKILL
                )
                
                # 清空該用戶的暫存照片
                user_images[user_id] = []
                
                # ---- 實際扣除使用次數 ----
                success, rem_free, rem_purchased = database.consume_quota(user_id, month_str)
                
                # 回傳分析結果
                result_text = response.text + f"\n\n---\n📊 目前剩餘可健檢額度：\n🎁 本月免費/訂閱額度：{rem_free} 次\n🪙 單筆儲值備用點數：{rem_purchased} 點"
                line_bot_api.push_message(user_id, TextSendMessage(text=result_text))
                return
                
            except Exception as e:
                import traceback
                print(f"Gemini Analysis Error: {e}")
                print(traceback.format_exc())
                line_bot_api.push_message(user_id, TextSendMessage(text="抱歉，A.A.D 系統分析過程中發生錯誤，請稍後再試。"))
                # 發生錯誤也清空暫存，避免卡死
                user_images[user_id] = []
                return

        # 一般文字問答邏輯
        try:
            # 取得或建立該用戶的對話 Session
            if user_id not in chat_sessions:
                chat_sessions[user_id] = model.start_chat(history=[])
            
            chat = chat_sessions[user_id]
            
            # 發送給 Gemini
            response = chat.send_message(user_msg)
            
            # 回傳 Gemini 的答案
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.text))
        
        except Exception as e:
            print(f"Gemini Error: {e}")
            # 遇到錯誤時的優雅回覆
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，我正在整理思緒中，請再問一次。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    current_mode = database.get_user_mode(user_id)

    if current_mode == "AI":
        try:
            # 取得圖片內容
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = b""
            for chunk in message_content.iter_content():
                image_bytes += chunk

            # 構建 Gemini 支援的圖片格式
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }

            # 存入該用戶的暫存區
            if user_id not in user_images:
                user_images[user_id] = []
            user_images[user_id].append(image_part)

            # 立刻回覆確認（不做額外 AI 呼叫）
            msg = f"✅ 已收到照片 (目前共 {len(user_images[user_id])} 張)。\n\n請問還有其他角度（如底部、特寫）的照片嗎？\n\n若已傳送完畢，請輸入『開始健檢』。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

        except Exception as e:
            print(f"Image Receive Error: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，圖片接收失敗，請重新傳送。"))



# ==========================================
# 6. 啟動伺服器
#cd /Volumes/Work_Drive/東方森煌共用/Senhuang_linebot
#source venv/bin/activate
#cloudflared tunnel --url http://localhost:5001
#https://receiving-prescription-close-convert.trycloudflare.com
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)