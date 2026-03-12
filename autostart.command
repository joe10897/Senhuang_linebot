#!/bin/bash

# --- 設定路徑 (使用相對路徑避免中文路徑解析問題) ---
WORK_DIR=$(cd "$(dirname "$0")"; pwd)
VENV_PYTHON="./venv/bin/python3"
LOG_FILE="./cloudflare.log"

# 1. 進入工作資料夾
cd "$WORK_DIR" || exit

# 2. 殺死舊的程序 (強制清理以避免衝突)
echo "🧹 正在清理舊的背景程序..."
# 強制殺死所有佔用 5001 port 的程式
lsof -t -i :5001 | xargs kill -9 > /dev/null 2>&1
pkill -9 -f "cloudflared tunnel" > /dev/null 2>&1
sleep 2

echo "🚀 開始啟動東方森煌 AI 客服..."

# 3. 啟動 Python 主程式 (背景執行)
# 使用 nohup 讓它在背景跑，不佔用視窗
nohup $VENV_PYTHON app.py > app.log 2>&1 &
echo "✅ Python App 已啟動 (Port 5001)"

# 4. 啟動 Cloudflare 隧道 (背景執行)
# 重點：把輸出存到 cloudflare.log，這樣我們才抓得到網址
nohup cloudflared tunnel --url http://localhost:5001 > "$LOG_FILE" 2>&1 &
echo "⏳ 正在建立 Cloudflare 隧道，請稍候 10 秒..."

# 5. 從 Log 檔裡面抓出那個隨機網址 (嘗試 3 次抓取)
NEW_URL=""
for i in {1..3}; do
    echo "⏳ 正在嘗試第 $i 次抓取網址..."
    # 使用 grep 抓取包含 trycloudflare.com 的行，並移除多餘符號和換行
    NEW_URL=$(grep "trycloudflare.com" "$LOG_FILE" | grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" | head -n 1)
    
    if [ -n "$NEW_URL" ]; then
        break
    fi
    echo "⚠️  尚未偵測到網址，5 秒後重試..."
    sleep 5
done

if [ -z "$NEW_URL" ]; then
    echo "❌ 抓取網址失敗，目前 cloudflare.log 的內容如下："
    tail -n 10 "$LOG_FILE"
    exit 1
else
    echo "===================================================="
    echo "🎉 所有程序啟動完畢！"
    echo "----------------------------------------------------"
    echo "🌐 抓到的 Cloudflare 網址："
    echo "   $NEW_URL"
    echo ""
    echo "🔗 請將此 Webhook URL 填入 LINE 後台 (如果自動更新失敗):"
    echo "   $NEW_URL/callback"
    echo "----------------------------------------------------"
    echo "===================================================="
fi

# 6. 執行 Python 腳本來更新 LINE 後台
$VENV_PYTHON update_webhook.py "$NEW_URL"

echo "✅ 啟動成功！請測試 LINE 機器人回覆。"