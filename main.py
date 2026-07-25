import os
import json
import requests
from fastapi import FastAPI, Request

app = FastAPI()

# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

RULES_FILE = "trading_rules.json"

def load_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_rule(rule_text):
    rules = load_rules()
    rules.append(rule_text)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def send_telegram_msg(target_chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": target_chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

# HÀM GỌI GROQ AI (TỐC ĐỘ SIÊU NHANH)
def call_groq_api(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Bạn là Trợ lý AI Trading cao cấp thuộc hệ thống Middle House Trading."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code == 200:
        res_data = response.json()
        return res_data['choices'][0]['message']['content']
    else:
        raise Exception(f"HTTP {response.status_code}: {response.text}")

# 2. XỬ LÝ NHẬN TÍN HIỆU TỪ TRADINGVIEW (WEBHOOK)
@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON"}

    event = data.get("event", "UNKNOWN")
    symbol = data.get("symbol", "N/A")
    tf = data.get("timeframe", "N/A")
    price = data.get("price", "N/A")
    rsi = data.get("rsi", "N/A")

    rules = load_rules()
    rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có quy tắc cụ thể."

    prompt = f"""
    TÍN HIỆU TRADINGVIEW VỪA BẮN VỀ:
    - Sự kiện: {event}
    - Mã tài sản: {symbol}
    - Khung thời gian: {tf}
    - Giá hiện tại: {price}
    - Chỉ số RSI: {rsi}

    DANH SÁCH QUY TẮC ĐÃ DẠY:
    {rules_text}

    YÊU CẦU:
    1. Phân tích tín hiệu trên dựa trên quy tắc đã học.
    2. Nếu là ENTRY, thông báo điểm vào rõ ràng.
    3. Nếu là REVERSAL_WARNING (M5), cảnh báo xem xét thoát lệnh/chốt lời.
    4. Trả lời ngắn gọn, chuẩn kỹ thuật trading.
    """

    try:
        ai_reply = call_groq_api(prompt)
        send_telegram_msg(TELEGRAM_CHAT_ID, ai_reply)
    except Exception as e:
        send_telegram_msg(TELEGRAM_CHAT_ID, f"🟢 Tín hiệu {event} - {symbol} (Giá: {price}, RSI: {rsi})")

    return {"status": "ok"}

# 3. XỬ LÝ CHAT VÀ DẠY BOT QUA TELEGRAM WEBHOOK
@app.post("/telegram")
async def receive_telegram(request: Request):
    try:
        data = await request.json()
        msg = data.get("message", {})
        
        chat_id = msg.get("chat", {}).get("id", TELEGRAM_CHAT_ID)

        text = msg.get("text", "")
        caption = msg.get("caption", "")

        # Xử lý dạy/chat văn bản
        if text:
            if text.lower().startswith("học:") or text.lower().startswith("dạy:"):
                rule_content = text.split(":", 1)[1].strip()
                save_rule(rule_content)
                send_telegram_msg(chat_id, f"✅ Hệ thống đã ghi nhớ quy tắc mới:\n\"{rule_content}\"")
            else:
                rules = load_rules()
                rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có."
                prompt = f"Quy tắc trading đã học: {rules_text}\n\nTin nhắn từ người dùng: '{text}'\nHãy trả lời ngắn gọn, phân tích chuẩn kỹ thuật."
                
                try:
                    ai_reply = call_groq_api(prompt)
                    send_telegram_msg(chat_id, ai_reply)
                except Exception as err:
                    send_telegram_msg(chat_id, f"⚠️ Lỗi kết nối Groq API: {err}")

    except Exception as e:
        print("Lỗi xử lý Telegram:", e)

    return {"status": "ok"}

# 4. THÔNG BÁO TỰ ĐỘNG KHI KẾT NỐI SERVER THÀNH CÔNG
@app.on_event("startup")
async def startup_event():
    welcome_msg = "🚀 [MIDDLE HOUSE TRADING AI]\nHệ thống AI Trợ lý (Groq Engine) đã kết nối thành công và sẵn sàng hoạt động 24/7!"
    if TELEGRAM_CHAT_ID:
        send_telegram_msg(TELEGRAM_CHAT_ID, welcome_msg)

@app.get("/")
def root():
    return {"status": "Doanh AI Server Running"}
