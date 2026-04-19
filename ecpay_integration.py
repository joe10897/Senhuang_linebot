import urllib.parse
import hashlib
from datetime import datetime

# 綠界測試環境測試用帳號
MERCHANT_ID = "2000132"
HASH_KEY = "5294y06JbISpM5x9"
HASH_IV = "v77hoKGq4kWxNNIS"

# 綠界 AIO Checkout API 網址 (測試機)
ECPAY_API_URL = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"

def generate_check_mac_value(params, hash_key, hash_iv):
    """
    計算綠界 CheckMacValue 演算法
    1. 將非 CheckMacValue 的欄位進行遞增排序
    2. 組合成 Query String 格式 (key1=value1&key2=value2...)
    3. 前後加上 HashKey 參數與 HashIV 參數
    4. 進行 URL encode，然後轉為小寫
    5. 取 SHA256 加密，再轉為大寫
    """
    # 綠界的排序有點特別，需要確保是按照字母順序
    sorted_params = sorted(params.items())
    
    # 組成查詢字串
    query_str = f"HashKey={hash_key}"
    for k, v in sorted_params:
        if k != "CheckMacValue":
            query_str += f"&{k}={v}"
    query_str += f"&HashIV={hash_iv}"
    
    # URL encode (需要注意 .NET 特有的 UrlEncode 邏輯)
    url_encoded = urllib.parse.quote_plus(query_str).lower()
    
    # 進行 SHA256 加密
    check_mac_value = hashlib.sha256(url_encoded.encode('utf-8')).hexdigest().upper()
    return check_mac_value

def create_order_params(order_id, user_id, amount, item_desc, return_url, client_back_url):
    """
    產生傳送給綠界的訂單參數
    """
    now = datetime.now()
    params = {
        "MerchantID": MERCHANT_ID,
        "MerchantTradeNo": order_id, # 必須唯一
        "MerchantTradeDate": now.strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(amount),
        "TradeDesc": "東方森煌館 AAD 文物鑑定服務",
        "ItemName": item_desc,
        "ReturnURL": return_url, # 綠界背景 Server To Server 回報網址
        "ClientBackURL": client_back_url, # 消費者成功後導回的網址
        "ChoosePayment": "Credit",
        "EncryptType": "1", # SHA256
        # 標記這是哪個使用者的訂單，可以利用 CustomField1 來傳遞 user_id
        "CustomField1": user_id 
    }
    
    mac_value = generate_check_mac_value(params, HASH_KEY, HASH_IV)
    params["CheckMacValue"] = mac_value
    
    return params

def generate_ecpay_html_form(order_id, user_id, amount, item_desc, return_url, client_back_url):
    """
    產生包含所有參數的 HTML Form，這個 Form 會自動送出 (auto-submit) 將用戶導向綠界
    """
    params = create_order_params(order_id, user_id, amount, item_desc, return_url, client_back_url)
    
    # 建立表單輸入框
    inputs_html = ""
    for key, value in params.items():
        inputs_html += f'<input type="hidden" name="{key}" value="{value}" />\n'
        
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>跳轉至安全結帳網頁 / Redirecting to Payment Gateway</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f8f9fa; margin: 0; }}
            .loader {{ border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 20px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            .container {{ text-align: center; color: #555; }}
        </style>
    </head>
    <body onload="document.getElementById('ecpay-form').submit();">
        <div class="container">
            <div class="loader"></div>
            <h3>正在導向綠界安全結帳畫⾯...</h3>
            <p>請勿關閉視窗，等候跳轉</p>
        </div>
        <form id="ecpay-form" action="{ECPAY_API_URL}" method="POST" style="display: none;">
            {inputs_html}
        </form>
    </body>
    </html>
    '''
    return html

def verify_ecpay_callback(request_form):
    """
    綠界 Webhook 回傳資料時，驗證 CheckMacValue 是否合法
    防範偽造資料
    """
    # 複製表單資料
    params = dict(request_form)
    
    # 取出並移除傳來的 CheckMacValue
    if 'CheckMacValue' not in params:
        return False
        
    received_mac = params.pop('CheckMacValue')
    
    # 自己重新計算一次
    calculated_mac = generate_check_mac_value(params, HASH_KEY, HASH_IV)
    
    # 如果相符，代表是合法的綠界請求
    return received_mac == calculated_mac
