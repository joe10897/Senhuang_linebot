# --- 設定環境 ---
$WORK_DIR = "Z:\Senhuang_linebot"
$PYTHON_PATH = "$WORK_DIR\venv\Scripts\python.exe"
$LOG_FILE = "$WORK_DIR\cloudflare.log"
$APP_LOG = "$WORK_DIR\app.log"

Set-Location $WORK_DIR

# 1. 殺死舊的程序 (避免 Port 被佔用)
Stop-Process -Name "python" -ErrorAction SilentlyContinue
Stop-Process -Name "cloudflared" -ErrorAction SilentlyContinue

Write-Host "🚀 開始啟動東方森煌 AI 客服 (Windows 版)..." -ForegroundColor Cyan

# 2. 啟動 Python 主程式
Start-Process -FilePath "python.exe" -ArgumentList "app.py" -RedirectStandardOutput $APP_LOG -WindowStyle Hidden
Write-Host "✅ Python App 已啟動 (Port 5001)" -ForegroundColor Green

# 3. 啟動 Cloudflare 隧道
if (Test-Path $LOG_FILE) { Remove-Item $LOG_FILE }
Start-Process -FilePath "cloudflared.exe" -ArgumentList "tunnel --url http://localhost:5001" -RedirectStandardOutput $LOG_FILE -WindowStyle Hidden
Write-Host "⏳ 正在建立 Cloudflare 隧道，請稍候 15 秒..." -ForegroundColor Yellow

Start-Sleep -Seconds 15

# 4. 從 Log 檔裡面抓出新網址
$NEW_URL = Get-Content $LOG_FILE | Select-String -Pattern "https://[^ ]*\.trycloudflare\.com" | ForEach-Object { $_.Matches.Value } | Select-Object -First 1

if (-not $NEW_URL) {
    Write-Host "❌ 抓取網址失敗，請檢查 cloudflare.log" -ForegroundColor Red
    exit
} else {
    Write-Host "🔍 抓到的新網址是：$NEW_URL" -ForegroundColor Cyan
}

# 5. 執行 Python 腳本來更新 LINE Webhook
python update_webhook.py "$NEW_URL"

Write-Host "🎉 所有程序啟動完畢！" -ForegroundColor Green
