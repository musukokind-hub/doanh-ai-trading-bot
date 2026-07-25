import os
import json
from io import BytesIO
from fastapi import FastAPI, Request
from PIL import Image
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

app = FastAPI()

# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# File lưu quy tắc bạn dạy
RULES_FILE = "trading_rules.json"

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_rule(rule_text):
    rules = load_rules()
    rules.append(rule_text)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

# Khởi tạo Telegram App
telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# 2. XỬ LÝ NHẬN TÍN HIỆU TỪ TRADINGVIEW (WEBHOOK)
@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    event = data.get("event")
    symbol = data.get("symbol")
    tf = data.get("timeframe")
    price = data.get("price")
    rsi = data.get("rsi")

    rules = load_rules()
    rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có quy tắc cụ thể."

    prompt = f"""
    Bạn là Trợ lý AI Trading riêng của anh Doanh.
    
    TÍN HIỆU TRADINGVIEW VỪA BẮN VỀ:
    - Sự kiện: {event}
    - Mã tài sản: {symbol}
    - Khung thời gian: {tf}
    - Giá hiện tại: {price}
    - Chỉ số RSI: {rsi}

    DANH SÁCH QUY TẮC ANH DOANH ĐÃ DẠY BẠN:
    {rules_text}

    YÊU CẦU:
    1. Phân tích tín hiệu trên dựa trên quy tắc đã học.
    2. Nếu là ENTRY, thông báo rõ ràng điểm vào.
    3. Nếu là REVERSAL_WARNING (M5), cảnh báo anh Doanh xem xét thoát lệnh/chốt lời theo quy tắc.
    4. Giọng văn ngắn gọn, tôn trọng, chuyên nghiệp.
    """

    response = model.generate_content(prompt)
    bot_msg = response.text

    # Bắn tin nhắn qua Telegram
    await telegram_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=bot_msg)
    return {"status": "ok"}

# 3. XỬ LÝ CHAT & DẠY HỌC QUA TELEGRAM
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = str(update.message.chat_id)

    if chat_id != str(TELEGRAM_CHAT_ID):
        return

    # Nếu câu lệnh bắt đầu bằng "Học:" hoặc "Dạy:" -> Lưu vào quy tắc
    if user_text.lower().startswith("học:") or user_text.lower().startswith("dạy:"):
        rule_content = user_text.split(":", 1)[1].strip()
        save_rule(rule_content)
        await update.message.reply_text(f"✅ Anh Doanh yên tâm, em đã ghi nhớ quy tắc mới:\n\"{rule_content}\"")
        return

    # Trò chuyện bình thường với AI
    rules = load_rules()
    rules_text = "\n".join([f"- {r}" for r in rules]) if rules else "Chưa có."

    prompt = f"""
    Bạn là Trợ lý Trading AI của anh Doanh.
    Quy tắc đã học từ anh Doanh:
    {rules_text}

    Anh Doanh vừa nhắn: "{user_text}"
    Hãy trả lời ngắn gọn, chuẩn kỹ thuật trading và đúng tinh thần các quy tắc đã học.
    """
    response = model.generate_content(prompt)
    await update.message.reply_text(response.text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != str(TELEGRAM_CHAT_ID):
        return

    caption = update.message.caption or "Phân tích ảnh này giúp anh."
    photo_file = await update.message.photo[-1].get_file()
    
    photo_bytes = BytesIO()
    await photo_file.download_to_memory(photo_bytes)
    image = Image.open(photo_bytes)

    # Nếu nhắn học qua ảnh: "Học: [nội dung]"
    if caption.lower().startswith("học:") or caption.lower().startswith("dạy:"):
        rule_content = caption.split(":", 1)[1].strip()
        prompt_learn = f"Tóm tắt ngắn gọn quy tắc trading từ hình ảnh này kết hợp với mô tả: {rule_content}"
        response_learn = model.generate_content([prompt_learn, image])
        
        saved_rule = f"Mẫu biểu đồ ({rule_content}): {response_learn.text}"
        save_rule(saved_rule)
        await update.message.reply_text(f"📸 ✅ Em đã soi ảnh và ghi nhớ bài học hình ảnh mới của anh Doanh!")
        return

    # Soi ảnh bình thường
    prompt = f"Phân tích biểu đồ kỹ thuật này cho anh Doanh. Gợi ý thêm: {caption}"
    response = model.generate_content([prompt, image])
    await update.message.reply_text(response.text)

# Thêm handler cho Telegram
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

@app.on_event("startup")
async def startup_event():
    await telegram_app.initialize()
    await telegram_app.start()

@app.get("/")
def root():
    return {"status": "Doanh AI Server Running"}
