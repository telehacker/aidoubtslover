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

# --- 1. CONFIGURATION (Environment Variables se uthayega) ---
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
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    logging.error("⚠️ GOOGLE_API_KEY nahi mila! Render Environment Variables check karein.")

# --- 4. FLASK SERVER (Render ko zinda rakhne ke liye) ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive! JEE Bot is running."

def run_http():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 5. HANDWRITING GENERATOR FUNCTION ---
def text_to_handwriting_image(text):
    # Setup Page
    width = 1000
    font_size = 40
    line_spacing = 10
    margin = 50
    
    # Font Load (GitHub par 'handwriting.ttf' hona zaroori hai)
    try:
        font = ImageFont.truetype("handwriting.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        logging.warning("⚠️ 'handwriting.ttf' nahi mila. Default font use ho raha hai.")

    # Text Wrapping
    chars_per_line = int((width - 2 * margin) / (font_size * 0.6))
    wrapper = textwrap.TextWrapper(width=chars_per_line)
    
    lines = []
    for paragraph in text.split('\n'):
        lines.extend(wrapper.wrap(paragraph))
        lines.append('') # Paragraph gap

    # Height Calculation
    total_text_height = len(lines) * (font_size + line_spacing)
    height = max(1000, total_text_height + 2 * margin)

    # Create Image (White Paper)
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Draw Text (Blue Ink Color)
    y_text = margin
    text_color = (0, 0, 150)

    for line in lines:
        draw.text((margin, y_text), line, font=font, fill=text_color)
        y_text += font_size + line_spacing

    # Save to Memory
    bio = io.BytesIO()
    image.save(bio, 'JPEG', quality=85)
    bio.seek(0)
    return bio

# --- 6. BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Hello {user}!\n\n"
        "Main JEE Doubt Solver hu. 🤖\n"
        "Mujhe question ki photo bhejo ya text likho.\n"
        "Main handwritten format mein solution dunga!"
    )

async def solve_doubt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GOOGLE_API_KEY:
        await update.message.reply_text("⚠️ Server Error: API Key missing.")
        return

    user_name = update.effective_user.first_name
    waiting_msg = await update.message.reply_text(f"⏳ Soch raha hu {user_name}... (Processing)")

    try:
        # Prompt Engineering for simple text output (LaTeX avoid karein)
        system_instruction = (
            "You are a JEE expert. Solve this problem step-by-step. "
            "IMPORTANT: Do not use complex LaTeX or Markdown formatting. "
            "Write in plain text as if writing in a notebook. "
            "Use words like 'integral' instead of symbols if possible. Keep it clean."
        )

        response_text = ""

        # CASE 1: Photo Input
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            image_bytes = await photo_file.download_as_bytearray()
            user_image = Image.open(io.BytesIO(image_bytes))
            
            caption = update.message.caption if update.message.caption else "Solve this."
            full_prompt = [system_instruction, caption, user_image]
            
            response = model.generate_content(full_prompt)
            response_text = response.text

        # CASE 2: Text Input
        elif update.message.text:
            full_prompt = f"{system_instruction}\n\nQuestion: {update.message.text}"
            response = model.generate_content(full_prompt)
            response_text = response.text
        
        else:
            await waiting_msg.edit_text("❌ Please photo ya text bhejein.")
            return

        # Convert AI Text to Handwriting Image
        img_bytes = text_to_handwriting_image(response_text)
        
        # Send Photo back to user
        await update.message.reply_photo(
            photo=img_bytes,
            caption=f"📝 Solution for {user_name}"
        )
        
        # Purana 'waiting' message delete karein
        await waiting_msg.delete()

    except Exception as e:
        logging.error(f"Error: {e}")
        await waiting_msg.edit_text("⚠️ Error aa gaya. Shayad question samajh nahi aaya. Dubara try karein.")

# --- 7. MAIN EXECUTION ---
if __name__ == '__main__':
    # Flask Server start karein (Background thread)
    t = Thread(target=run_http)
    t.start()
    
    # Bot start karein
    if not TELEGRAM_TOKEN:
        print("❌ Error: TELEGRAM_TOKEN nahi mila. Environment Variables check karein.")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, solve_doubt))
        
        print("✅ Bot is running...")
        application.run_polling()
