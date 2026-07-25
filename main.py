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
MARKET_STATE_FILE = "market_state.json"

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {} if "state" in filepath else []
    return {} if "state" in filepath else []

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_rule(rule_text):
    rules = load_json(RULES_FILE)
    if isinstance(rules, list):
        rules.append(rule_text)
        save_json(RULES_FILE, rules)

def update_market_state(symbol, data):
    states = load_json(MARKET_STATE_FILE)
    if not isinstance(states, dict):
        states = {}
    states[symbol] = data
    save_json(MARKET_STATE_FILE, states)

def send_telegram_msg(target_chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": target_chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def call_groq_api(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system", 
                "content": "Bạn là Trợ lý AI Phân tích Kỹ thuật Chuyên nghiệp thuộc Middle House Trading. Hãy phân tích ngắn gọn, quyết đoán xu hướng (BUY/SELL/NEUTRAL) dựa trên dữ liệu thị trường và logic được cung cấp."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code == 200:
        res_data = response.json()
        return res_data['choices'][0]['message']['content']
    else:
        raise Exception(f"HTTP {response.status_code}: {response.text}")

# 2. XỬ LÝ NHẬN CẬP NHẬT TỪ TRADINGVIEW (WEBHOOK)
@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON"}

    symbol = data.get("symbol", "XAUUSD")
    update_market_state(symbol, data)

    event = data.get("event", "UPDATE")
    if event in ["ENTRY_BUY", "ENTRY_SELL", "REVERSAL_WARNING"]:
        rules = load_json(RULES_FILE)
        rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có quy tắc."
        prompt = f"TÍN HIỆU TỪ TRADINGVIEW: {data}\nLOGIC DẠY: {rules_text}\nHãy phân tích và đưa ra khuyến nghị vào lệnh ngắn gọn."
        
        try:
            ai_reply = call_groq_api(prompt)
            send_telegram_msg(TELEGRAM_CHAT_ID, ai_reply)
        except Exception as e:
            send_telegram_msg(TELEGRAM_CHAT_ID, f"🟢 Tín hiệu {event} - {symbol}")

    return {"status": "ok"}

# 3. XỬ LÝ CHAT VÀ PHÂN TÍCH THEO YÊU CẦU TRÊN TELEGRAM
@app.post("/telegram")
async def receive_telegram(request: Request):
    try:
        data = await request.json()
        msg = data.get("message", {})
        chat_id = msg.get("chat", {}).get("id", TELEGRAM_CHAT_ID)
        text = msg.get("text", "")

        if text:
            # Học quy tắc logic mới
            if text.lower().startswith("học:") or text.lower().startswith("dạy:"):
                rule_content = text.split(":", 1)[1].strip()
                save_rule(rule_content)
                send_telegram_msg(chat_id, f"✅ Đã ghi nhớ logic giao dịch mới:\n\"{rule_content}\"")
            
            # Trả lời câu hỏi xu hướng thị trường
            else:
                rules = load_json(RULES_FILE)
                rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có quy tắc cụ thể."
                
                market_data = load_json(MARKET_STATE_FILE)
                gold_data = market_data.get("XAUUSD", "Chưa có dữ liệu cập nhật gần đây từ TradingView.")

                prompt = f"""
                NGƯỜI DÙNG HỎI: "{text}"
                
                DỮ LIỆU THỊ TRƯỜNG CẬP NHẬT MỚI NHẤT (XAUUSD):
                {gold_data}

                LOGIC GIAO DỊCH ĐÃ DẠY:
                {rules_text}

                YÊU CẦU TRẢ LỜI:
                - Dựa vào Dữ liệu thị trường và Logic giao dịch trên để nhận định xu hướng (BUY hay SELL hay ĐỜI SIGNAL).
                - Trả lời thẳng vào vấn đề, ngắn gọn, chuẩn kỹ thuật trading.
                - Nếu chưa có dữ liệu biểu đồ, hướng dẫn người dùng chụp gửi ảnh màn hình chart để soi ngay.
                """
                
                try:
                    ai_reply = call_groq_api(prompt)
                    send_telegram_msg(chat_id, ai_reply)
                except Exception as err:
                    send_telegram_msg(chat_id, f"⚠️ Lỗi kết nối Groq API: {err}")

    except Exception as e:
        print("Lỗi xử lý Telegram:", e)

    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    welcome_msg = "🚀 [MIDDLE HOUSE TRADING AI]\nHệ thống AI Trợ lý đã sẵn sàng phân tích biểu đồ & xu hướng 24/7!"
    if TELEGRAM_CHAT_ID:
        send_telegram_msg(TELEGRAM_CHAT_ID, welcome_msg)

@app.get("/")
def root():
    return {"status": "Doanh AI Server Running"}
