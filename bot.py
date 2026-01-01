import os
import logging
import textwrap
import io
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

# --- 3. GEMINI AI SETUP ---
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    # Model name updated to avoid 404 error
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    logging.error("⚠️ GOOGLE_API_KEY nahi mila! Render Environment Variables check karein.")

# --- 4. FLASK SERVER (For Render Keep-Alive) ---
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
    
    try:
        font = ImageFont.truetype("handwriting.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    
    # Calculate layout
    chars_per_line = int((width - 2 * margin) / (font_size * 0.6))
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    
    lines = []
    for paragraph in text.split('\n'):
        lines.extend(wrapper.wrap(paragraph))
        lines.append('') 

    total_text_height = len(lines) * (font_size + line_spacing)
    height = max(1000, total_text_height + 2 * margin)

    # Create Image
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

# --- 6. BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Aur Bhai! JEE ki taiyari kaisi chal rahi hai?\n"
        "Mujhe koi bhi question bhejo (Photo ya Text), main solve karke dunga.\n"
        "Baki gapp-shapp bhi kar sakte ho!"
    )

async def solve_doubt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GOOGLE_API_KEY:
        await update.message.reply_text("❌ API Key missing. Owner se bolo settings check kare.")
        return

    user_msg = update.message.text
    user_name = update.effective_user.first_name
    
    # === DECISION: Doubt hai ya Chat? ===
    is_doubt = False
    
    if update.message.photo:
        is_doubt = True # Photo matlab pakka doubt
    elif user_msg:
        # Padhai wale words check karo
        keywords = ['solve', 'doubt', 'explain', 'question', 'math', 'physics', 'chemistry', 'answer', 'integration', 'derivative', 'reaction', 'meaning']
        if any(word in user_msg.lower() for word in keywords):
            is_doubt = True
        elif len(user_msg.split()) > 6: # Lamba message = shayad question hai
            is_doubt = True

    # === EXECUTION ===
    if is_doubt:
        # --- DOUBT MODE (Handwriting) ---
        waiting_msg = await update.message.reply_text(f"Ruk {user_name}, solve kar raha hu... ✍️")
        
        try:
            system_prompt = (
                "You are a smart JEE student. Solve this problem step-by-step clearly. "
                "Write in plain text (Hinglish/English). "
                "Do NOT use LaTeX (like \\frac or $$). Use simple format like (a/b). "
                "Keep explanation to the point."
            )

            if update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                user_image = Image.open(io.BytesIO(image_bytes))
                caption = update.message.caption if update.message.caption else "Solve this"
                response = model.generate_content([system_prompt, caption, user_image])
            else:
                response = model.generate_content(f"{system_prompt}\n\nQuestion: {user_msg}")

            # Image banao aur bhejo
            img_bytes = text_to_handwriting_image(response.text)
            await update.message.reply_photo(photo=img_bytes, caption=f"Ye le solution! @{user_name}")
            await waiting_msg.delete()

        except Exception as e:
            logging.error(f"Error: {e}")
            await waiting_msg.edit_text("Yaar ye sawal samajh nahi aa raha. Thodi saaf photo bhejo ya clear text likho. 🤔")

    else:
        # --- CHAT MODE (Normal Text) ---
        try:
            chat_prompt = (
                f"You are a friendly JEE aspirant friend. User said: '{user_msg}'. "
                "Reply in very short, casual Hinglish (Indian slang allowed like bhai, yaar). "
                "Be funny or motivating. Max 20 words."
            )
            response = model.generate_content(chat_prompt)
            await update.message.reply_text(response.text)
        except:
            pass # Ignore errors in chat mode

# --- 7. MAIN ---
if __name__ == '__main__':
    # Server start (Background)
    t = Thread(target=run_http)
    t.start()
    
    # Bot start
    if not TELEGRAM_TOKEN:
        print("❌ Error: TELEGRAM_TOKEN missing.")
    else:
        app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app_bot.add_handler(CommandHandler('start', start))
        app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, solve_doubt))
        
        print("✅ Bot is running...")
        app_bot.run_polling()
