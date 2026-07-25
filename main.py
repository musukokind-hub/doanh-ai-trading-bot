import os
import json
import requests
from io import BytesIO
from fastapi import FastAPI, Request
from PIL import Image
import google.generativeai as genai

app = FastAPI()

# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

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
    Bạn là Trợ lý AI Trading riêng thuộc hệ thống Middle House Trading.
    
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
        response = model.generate_content(prompt)
        send_telegram_msg(TELEGRAM_CHAT_ID, response.text)
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
        photos = msg.get("photo", [])

        # Xử lý dạy/chat văn bản
        if text:
            if text.lower().startswith("học:") or text.lower().startswith("dạy:"):
                rule_content = text.split(":", 1)[1].strip()
                save_rule(rule_content)
                send_telegram_msg(chat_id, f"✅ Hệ thống đã ghi nhớ quy tắc mới:\n\"{rule_content}\"")
            else:
                rules = load_rules()
                rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có."
                prompt = f"Bạn là Trợ lý Trading AI thuộc Middle House Trading.\nQuy tắc đã học: {rules_text}\n\nTin nhắn nhận được: '{text}'\nHãy trả lời ngắn gọn, chuẩn kỹ thuật."
                
                try:
                    res_ai = model.generate_content(prompt)
                    send_telegram_msg(chat_id, res_ai.text)
                except Exception as err:
                    send_telegram_msg(chat_id, f"🤖 Đã nhận tin nhắn: '{text}'\n⚠️ Lỗi gọi Gemini AI: {err}")

        # Xử lý dạy/soi hình ảnh biểu đồ
        elif photos:
            file_id = photos[-1]["file_id"]
            file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            img_bytes = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}").content
            image = Image.open(BytesIO(img_bytes))

            if caption.lower().startswith("học:") or caption.lower().startswith("dạy:"):
                rule_content = caption.split(":", 1)[1].strip()
                prompt_learn = f"Tóm tắt ngắn gọn quy tắc trading từ hình ảnh này kết hợp mô tả: {rule_content}"
                try:
                    res_ai = model.generate_content([prompt_learn, image])
                    save_rule(f"Mẫu biểu đồ ({rule_content}): {res_ai.text}")
                    send_telegram_msg(chat_id, "📸 ✅ Em đã soi ảnh và ghi nhớ mẫu biểu đồ mới!")
                except Exception as err:
                    send_telegram_msg(chat_id, f"⚠️ Lỗi xử lý hình ảnh AI: {err}")
            else:
                prompt = f"Phân tích biểu đồ kỹ thuật này giúp tôi. Gợi ý thêm: {caption}"
                try:
                    res_ai = model.generate_content([prompt, image])
                    send_telegram_msg(chat_id, res_ai.text)
                except Exception as err:
                    send_telegram_msg(chat_id, f"⚠️ Lỗi phân tích ảnh AI: {err}")

    except Exception as e:
        print("Lỗi xử lý Telegram:", e)

    return {"status": "ok"}

# 4. THÔNG BÁO TỰ ĐỘNG KHI KẾT NỐI SERVER THÀNH CÔNG
@app.on_event("startup")
async def startup_event():
    welcome_msg = "🚀 [MIDDLE HOUSE TRADING AI]\nHệ thống AI Trợ lý đã kết nối thành công và sẵn sàng hoạt động 24/7!"
    if TELEGRAM_CHAT_ID:
        send_telegram_msg(TELEGRAM_CHAT_ID, welcome_msg)

@app.get("/")
def root():
    return {"status": "Doanh AI Server Running"}
