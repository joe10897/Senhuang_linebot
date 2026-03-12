import sys
import os
from linebot import LineBotApi
from dotenv import load_dotenv

# 1. 載入 .env 裡的 Token
load_dotenv()
RAW_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

# 清理 Token：移除所有可能的引號、空格或換行
if RAW_TOKEN:
    CHANNEL_ACCESS_TOKEN = RAW_TOKEN.strip().replace("'", "").replace('"', "")
else:
    print("❌ 錯誤：找不到 Token，請檢查 .env 檔案")
    sys.exit(1)

# 2. 取得指令傳進來的新網址 (例如：https://xxx.trycloudflare.com)
if len(sys.argv) < 2:
    print("❌ 錯誤：請提供網址參數")
    sys.exit(1)

# 清理網址：移除前後空格、中間可能夾雜的框線符號 | 以及換行符號
raw_url = sys.argv[1]
clean_url = raw_url.strip().replace("|", "").replace("\n", "").replace("\r", "").split()[0]

# 確保網址是以 https:// 開頭
if not clean_url.startswith("https://"):
    print(f"❌ 錯誤：抓取的網址格式不正確: {clean_url}")
    sys.exit(1)

webhook_url = f"{clean_url}/callback"

print(f"🔄 正在向 LINE 更新 Webhook 網址為：{webhook_url}")

# 3. 呼叫 LINE API 更新 Webhook
try:
    line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
    # 使用 LINE 的 set_webhook_endpoint API
    line_bot_api.set_webhook_endpoint(webhook_url)
    print("✅ 成功！LINE 後台網址已自動更新完成。")
except Exception as e:
    print(f"❌ 更新失敗，可能是 Token 錯誤或 API 呼叫超時：\n{e}")
    sys.exit(1)
