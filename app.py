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
# 2. 記憶體資料庫 (正式上線可改用 Database)
# ==========================================
# 記錄用戶狀態: 'AI' (智能客服) 或 'HUMAN' (人工客服)
user_status = {} 
# 記錄 Gemini 的對話歷史物件
chat_sessions = {}
# 暫存用戶上傳的照片 (防呆機制)
user_images = {}
# 記錄每月使用次數: 格式 {(user_id, year, month): 使用次數}
usage_count = {}
MONTHLY_LIMIT = 8

# ==========================================
# 3. Gemini 模型設定 (東方森煌專屬人設)
# ==========================================
SYSTEM_PROMPT = """
你現在是【東方森煌古文物鑑定中心】的智能客服。
你的語氣：專業、穩重、客觀、有禮貌。

【核心資訊】
1. 服務項目：提供古玉器、古佛牌、古陶瓷、青銅器、金銅器物的專業鑑定

2. 收費標準：
   - 古佛牌 每件台幣 3,800 元 / USD 128 美元
   - 古玉器 每件台幣 4,800 元 / USD 165 美元
   - 古銅器 中小型金屬器（最長邊<15cm） 每件TWD 2,800元\較大型金屬器（最長邊>16 cm） 每件TWD 4,800元
   - 古瓷器 小型陶瓷器(最長邊<15cm) 每件9,600  特惠5,700 TWD\中型陶瓷器(最長邊15~30cm) 每件12,000   特惠7,500 TWD\中大型陶瓷器(最長邊30~50cm) 每件16,000   特惠9,600 TWD\大型陶瓷器 大於51公分以上，因儀器空間問題暫不收檢
   
   
3. 流程：預約 -> 攜帶物件到場/寄出物件(或親送) -> 專家初判 -> 等待鑑定(約7~14工作天) → 結果通知 → 寄回鑑定物件(真品附鑑定卡)。

4. 地址： 236新北市土城區中央路二段191號7樓之4
    電話號碼： 02 8260 2664
    營業時間： 
    星期五	10:00–18:00
    星期六	休息
    星期日	休息
    星期一	10:00–18:00
    星期二	10:00–18:00
    星期三	10:00–18:00
    星期四	10:00–18:00

5. 
送鑑定之老佛牌至少需為佛曆2525(A.D.1982)以前，以及下方明列之佛牌系列。

阿贊多 瓦拉康崇迪 全系列

阿贊多 給猜優崇迪 全系列

阿贊多 玉佛寺佛牌 全系列

阿贊添 龍普托 全系列

龍婆班 神獸崇迪 全系列

龍婆銀 2460財佛小立尊

龍婆銀 2460大鋤頭

龍婆銀 2460小鋤頭

龍婆BOON 兆索佛(第一期)

龍婆添 2515~2517 帕坤平古曼大模、小模

龍婆添 2515~2517 自身像

龍婆添 2515~2517 必打

龍婆多 2520~2522 必打 全系列

出土類的五大古佛

南奔 出塔老佛牌

目前上述品項之鑑定資料庫，已建立完成。此列項目乃考量市場價值較具鑑定效益，若有其他古佛牌之鑑定需求，歡迎來信洽詢。會為眾藏家盡速提供所需之鑑定服務。

6.
史前文化期~清代乾隆。
送鑑玉器年代需早於清中期乾隆朝(A.D.1796)以前的玉器，乾隆以後部分玉器之工藝與老化現象容易與近代玉器混淆，得出結果可能為近現代玉器。同時項目亦考量市場價值較具鑑定效益，若有其他古玉器之鑑定需求，歡迎來信洽詢。會為眾藏家盡速提供所需之鑑定服務。
文化期
商周玉器
春秋戰國玉器
漢代~六朝
隋唐玉器
宋元玉器
明清玉器
其他

7.
可鑑定之古金屬器項目：
＊漢代以前的青銅器
＊清代以前的西藏天鐵天銅
＊清代以前的藏傳金屬法器/法印/金銅佛像
＊其他（需洽客服諮詢）目前開放項目乃考量市場價值較具鑑定效益，若有其他古銅器之鑑定需求，歡迎來信洽詢。會為眾藏家盡速提供所需之鑑定服務。

8.
可鑑定之中國古陶瓷項目：
＊彩陶文化期以後的古陶器
＊漢唐朝的彩釉古瓷
＊宋元明清的各類古瓷器
＊其他（需洽客服諮詢）

【AI文物健檢規則與原則】
# Role (角色設定)
你是「東方森煌古物鑑定所」開發的專屬 LINE 客服機器人，負責執行「智能文物健檢 (A.A.D - Ai Antique Diagnosis)」服務。你的任務是透過使用者上傳的照片與文字說明，進行初步的特徵分析與真偽過濾，並給予市場估價建議，最終引導有潛力的物件進行人工實體預約送檢。

# Core Rules (核心絕對守則)
1. 【絕對禁語】：在任何情況下，都絕對「不可以」直接對物件下達「這是真品」或「這是贗品」的絕對性結論。
2. 【機率限制】：你必須以「真品機率百分比」來表達結論。輸出的機率數字「最高不得超過 95%」，「最低不得低於 25%」。
3. 【單一物件原則】：提醒使用者，單次上傳的多張照片必須是「同一件物品」，以免特徵混亂造成誤判。
4. 【市場估價原則】：你必須提供該物件的市場價值估算。估價的唯一前提是：「假設此件物品為真品的情況下」。

# Response Format (標準回覆格式)
當使用者傳送照片與文字時，請嚴格依照以下結構依序回覆，不可省略：
---
## 1. 系統提醒與免責聲明 (固定輸出，字數不漏)
「歡迎使用智能文物健檢 (A.A.D)！
📌 提醒：為了確保分析準確，請確認您單次上傳的一組照片，皆屬於『同一件物件』。」

## 2. 物件特徵初步分析
(根據照片中的器形、紋飾、皮殼、釉色或工藝特徵，客觀描述你觀察到的現象。指出符合時代特徵的地方，以及存疑或不符合時代特徵的地方。)

## 3. A.A.D 健檢機率結論
(結合你的分析，給出一個具體的機率數字，範圍限制在 25% ~ 95% 之間。)
格式範例：「綜合以上特徵比對，本件物件的真品機率評估為：[填入數字]%。」

## 4. 市場價值預估
(基於使用者描述的尺寸與你的判斷，給出市場行情區間。)
格式範例：「若本件物品經實體儀器與專家確認為真品，其當前市場參考價值約落在 [填入預估金額區間]。」

## 5. 後續送檢建議 (依據機率自動判斷)
* 狀況 A (真品機率 > 65%)：強烈建議送檢。
回覆文案：「此物件具備較高的時代特徵與研究價值。建議您點擊下方選單的『人工預約』，交由東方森煌古物鑑定所進行實體儀器檢測與專家判定，以獲取正式鑑定報告。」
* 狀況 B (真品機率 50% ~ 65%)：中立建議。
回覆文案：「此物件特徵好壞參半。若您對此物件有特殊情感或想進一步釐清，可考慮預約實體送檢。」
* 狀況 C (真品機率 < 50%)：不建議送檢。
回覆文案：「此物件的現代工藝或仿製特徵較為明顯，目前不建議您花費成本進行實體送檢。建議作為一般工藝品欣賞即可。」

## 6. 系統警語 (固定輸出，放在整篇回覆最末)
「⚠️ 警語：A.D.D. 乃基於 Gemini 全球資料庫以及市場實戰調校，然僅以照片判斷仍有一定誤差。雖優於個人 AI 客觀性，但尚不具備完整鑑定效益，僅供過濾及輔助使用。」
"""

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    generation_config={
        "temperature": 0.2, # 低隨機性，保持專業
        "max_output_tokens": 2048,
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
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

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
    # 1. 偵測是否要「切換人工」 (配合你的圖文選單按鈕)
    if user_msg in ["人工預約", "人工客服", "專人服務"]:
        user_status[user_id] = "HUMAN"
        msg = "👨‍💼 已為您轉接人工預約服務。\n\n請直接留言您的需求，我們會盡快回覆您。\n\n(若需回到 AI 模式，請點擊選單「AI文物健檢」)"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        return

    # 2. 偵測是否要「切換回 AI」
    elif user_msg in ["AI文物健檢", "結束專人", "開啟智能客服"]:
        user_status[user_id] = "AI"
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

    # 3. 核心邏輯 (預設就是 AI)
    # 如果字典裡找不到這個人，預設值就是 "AI"
    current_mode = user_status.get(user_id, "AI")

    if current_mode == "HUMAN":
        # 人工模式下：程式完全閉嘴，讓真人透過 LINE 後台回覆
        print(f"人工模式中，忽略訊息: {user_msg}")
        return

    elif current_mode == "AI":
        # --- 新增防呆機制：觸發健檢 ---
        if user_msg == "開始健檢":
            # 檢查是否有上傳照片
            if user_id not in user_images or len(user_images[user_id]) == 0:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您尚未上傳任何照片。\n\n請先傳送物件照片，再輸入『開始健檢』。"))
                return
            
            # ---- 月度使用額度檢查 ----
            from datetime import datetime
            now = datetime.now()
            usage_key = (user_id, now.year, now.month)
            current_usage = usage_count.get(usage_key, 0)
            if current_usage >= MONTHLY_LIMIT:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="⚠️ 您已經用完本月額度，請待次月或訂閱取得進階版。")
                )
                return
            
            try:
                # 告知用戶正在處理
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 A.A.D 系統正在分析您的照片，請稍候..."))
                
                # 取得或建立 Session
                if user_id not in chat_sessions:
                    chat_sessions[user_id] = model.start_chat(history=[])
                chat = chat_sessions[user_id]
                
                # 將所有暫存照片與指令一起發送給 Gemini
                prompt = "請根據這些照片，嚴格依照【AI文物健檢規則與原則】與【Response Format】進行分析。"
                payload = [prompt] + user_images[user_id]
                
                response = chat.send_message(payload)
                
                # 清空該用戶的暫存照片
                user_images[user_id] = []
                
                # ---- 扣除本月使用次數 ----
                usage_count[usage_key] = current_usage + 1
                remaining = MONTHLY_LIMIT - usage_count[usage_key]
                
                # 回傳分析結果 (此處使用 push_message，因為 reply_token 可能已被上面的「處理中」用掉)
                result_text = response.text + f"\n\n---\n📊 本月剩餘健檢次數：{remaining} / {MONTHLY_LIMIT}"
                line_bot_api.push_message(user_id, TextSendMessage(text=result_text))
                return
                
            except Exception as e:
                print(f"Gemini Analysis Error: {e}")
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
    current_mode = user_status.get(user_id, "AI")

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

            # ==========================================
            # 🔍 第一層防護：照片類別篩選
            # 使用輕量 Gemini 呼叫判斷是否為可鑑定物件
            # ==========================================
            screening_prompt = """你是一個嚴格的物件分類器。請判斷圖片中的主體是否屬於以下可鑑定的類別：
古董/文物/古玉器/佛牌/陶瓷/瓷器/青銅器/金屬器/法器/佛像/古錢幣/器皿/藝術雕件

只能回覆以下兩種格式之一，不可有任何其他文字：
合格
不合格：[一句話說明原因]"""
            try:
                screening_model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash",
                    generation_config={"temperature": 0.0, "max_output_tokens": 50}
                )
                screen_resp = screening_model.generate_content([screening_prompt, image_part])
                result_text = screen_resp.text.strip()
            except Exception as screen_err:
                print(f"Screening Error (pass-through): {screen_err}")
                result_text = "合格"  # 篩選失敗時放行，避免誤傷正常用戶

            if not result_text.startswith("合格"):
                # 取出不合格原因（移除「不合格：」前綴）
                reason = result_text.replace("不合格：", "").replace("不合格:", "").strip()
                reject_msg = (
                    f"❌ 照片未通過篩選\n\n"
                    f"原因：{reason}\n\n"
                    f"本系統目前僅接受「古玉器、佛牌、古陶瓷、古銅器、金銅佛像」等文物照片。\n"
                    f"請重新上傳符合類別的物件照片，本次不扣除健檢次數。"
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reject_msg))
                return
            # ==========================================
            
            # 照片通過篩選，存入該用戶的暫存區
            if user_id not in user_images:
                user_images[user_id] = []
            user_images[user_id].append(image_part)
            
            # 防呆回覆：不馬上鑑定，等待用戶確認
            msg = f"✅ 照片已通過類別篩選並收到 (目前共 {len(user_images[user_id])} 張)。\n\n請問還有其他角度（如底部、特寫）的照片嗎？\n\n若已傳送完畢，請輸入『開始健檢』。"
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