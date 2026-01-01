import os
import logging
import textwrap
import io
import time
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- 2. LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- 3. GEMINI AI SETUP & SAFETY ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    # Model name fix: 'gemini-1.5-flash-latest' sabse stable hai abhi
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    logging.error("⚠️ GOOGLE_API_KEY Missing! Render settings check karo.")

# Safety Settings: Taaki 'Samajh nahi aaya' wala error na aaye
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- 4. FLASK SERVER (Render Alive Rakhne Ke Liye) ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive! JEE Bot is running."

def run_http():
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host='0.0.0.0', port=port)
    except:
        pass

# --- 5. HANDWRITING GENERATOR ---
def text_to_handwriting_image(text):
    width = 1000
    font_size = 40
    line_spacing = 10
    margin = 50
    
    # Font Loader
    try:
        font = ImageFont.truetype("handwriting.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    
    # Text Wrapping logic
    chars_per_line = int((width - 2 * margin) / (font_size * 0.6))
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    
    lines = []
    for paragraph in text.split('\n'):
        lines.extend(wrapper.wrap(paragraph))
        lines.append('') 

    total_text_height = len(lines) * (font_size + line_spacing)
    height = max(1000, total_text_height + 2 * margin)

    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    y_text = margin
    text_color = (0, 0, 150) # Blue Ink

    for line in lines:
        draw.text((margin, y_text), line, font=font, fill=text_color)
        y_text += font_size + line_spacing

    bio = io.BytesIO()
    image.save(bio, 'JPEG', quality=85)
    bio.seek(0)
    return bio

# --- 6. MAIN BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Aur Bhai! JEE ki taiyari kaisi chal rahi hai?\n"
        "Question bhejo (Photo ya Text), main solve karke dunga.\n"
        "Handwritten notes ki tarah answer milega! 📝"
    )

async def solve_doubt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GOOGLE_API_KEY:
        await update.message.reply_text("❌ API Key missing.")
        return

    user_msg = update.message.text
    user_name = update.effective_user.first_name
    
    # === DECISION: Doubt hai ya Chat? ===
    is_doubt = False
    if update.message.photo:
        is_doubt = True 
    elif user_msg:
        keywords = ['solve', 'doubt', 'explain', 'question', 'math', 'physics', 'chemistry', 'answer', 'integration', 'derivative', 'reaction']
        if any(word in user_msg.lower() for word in keywords) or len(user_msg.split()) > 5:
            is_doubt = True

    # === EXECUTION ===
    if is_doubt:
        # --- DOUBT MODE ---
        waiting_msg = await update.message.reply_text(f"Ruk {user_name}, solve kar raha hu... ✍️")
        
        try:
            system_prompt = (
                "You are an expert JEE Tutor. Solve this problem step-by-step. "
                "Write in plain Hinglish/English. "
                "Do NOT use complex LaTeX. Write like a student notebook."
            )

            # Generate Content
            if update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                user_image = Image.open(io.BytesIO(image_bytes))
                caption = update.message.caption if update.message.caption else "Solve this"
                
                response = model.generate_content(
                    [system_prompt, caption, user_image],
                    safety_settings=SAFETY_SETTINGS
                )
            else:
                response = model.generate_content(
                    f"{system_prompt}\n\nQuestion: {user_msg}",
                    safety_settings=SAFETY_SETTINGS
                )

            # Check for empty response
            if not response.text:
                await waiting_msg.edit_text("Yaar answer generate nahi hua. Dobara bhejo.")
                return

            # Convert to Handwriting Image
            img_bytes = text_to_handwriting_image(response.text)
            
            # Send Image
            await update.message.reply_photo(photo=img_bytes, caption=f"Ye le solution! @{user_name}")
            await waiting_msg.delete()

        except Exception as e:
            logging.error(f"Error: {e}")
            await waiting_msg.edit_text("⚠️ Yaar ye sawal samajh nahi aa raha. Thodi saaf photo bhejo. (Technical Error)")

    else:
        # --- CHAT MODE ---
        try:
            chat_prompt = (
                f"You are a friendly JEE aspirant. User said: '{user_msg}'. "
                "Reply in short, casual Hinglish slang. Be funny. Max 1 sentence."
            )
            response = model.generate_content(chat_prompt)
            await update.message.reply_text(response.text)
        except:
            pass 

# --- 7. START APP ---
if __name__ == '__main__':
    # Start Flask Server
    t = Thread(target=run_http)
    t.start()
    
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN nahi mila.")
    else:
        app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app_bot.add_handler(CommandHandler('start', start))
        app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, solve_doubt))
        
        print("✅ Bot is running...")
        app_bot.run_polling(drop_pending_updates=True) 
        # 'drop_pending_updates=True' se conflict kam hote hain
