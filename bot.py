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

# --- UPDATE THIS FUNCTION IN YOUR CODE ---

async def solve_doubt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GOOGLE_API_KEY:
        await update.message.reply_text("❌ API Key missing.")
        return

    user_msg = update.message.text
    user_name = update.effective_user.first_name
    
    # ... (Is_Doubt logic same rahega) ...
    # Agar message me keywords hain ya photo hai to 'is_doubt = True'

    # === Logic for Doubts ===
    # Yahan humne Safety Settings add ki hain taaki block na ho
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    if is_doubt:
        waiting_msg = await update.message.reply_text(f"Ruk {user_name}, solve kar raha hu... ✍️")
        
        try:
            # TEACHER PROMPT (Thoda aur strong banaya hai)
            system_prompt = (
                "You are an expert JEE Tutor. Your task is to solve physics/math/chemistry problems. "
                "Analyze the image or text carefully. "
                "Provide a step-by-step solution in simple Hinglish/English. "
                "Do NOT use complex LaTeX. Write as if writing in a notebook."
            )

            response = None

            # CASE 1: Photo
            if update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                user_image = Image.open(io.BytesIO(image_bytes))
                caption = update.message.caption if update.message.caption else "Solve this question detailed."
                
                # Image ke liye 'gemini-1.5-flash' use karein (Flash models vision ke liye fast hote hain)
                # Note: 'stream=False' zaroori hai
                response = model.generate_content(
                    [system_prompt, caption, user_image],
                    safety_settings=safety_settings
                )

            # CASE 2: Text
            else:
                response = model.generate_content(
                    f"{system_prompt}\n\nQuestion: {user_msg}",
                    safety_settings=safety_settings
                )
            
            # Response Check
            if not response.text:
                raise ValueError("Empty response from AI")

            # Image Conversion
            img_bytes = text_to_handwriting_image(response.text)
            await update.message.reply_photo(photo=img_bytes, caption=f"Ye le solution! @{user_name}")
            await waiting_msg.delete()

        except Exception as e:
            # Agar ab bhi error aaye, to exact error print karo logs me
            logging.error(f"GEMINI ERROR: {e}")
            
            # User ko batao ki shayad image issue hai
            await waiting_msg.edit_text(
                "Yaar AI ko ye photo samajh nahi aayi. 😕\n"
                "Try karo:\n"
                "1. Photo thodi crop karke bhejo (sirf question dikhe).\n"
                "2. Ya question text mein likh do."
            )
    
    # ... (Chat logic same rahega) ...

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
