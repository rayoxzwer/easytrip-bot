import os
import sys
import json
import io
import html
import asyncio
import sqlite3
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile
from google import genai
from google.genai import types as genai_types

# ReportLab Layout Tools
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Setup Logging Metrics
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logging.critical("Deployment failed: Environment variables are missing!")
    sys.exit(1)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
DB_FILE = "easy_trip.db"

# Global sets to manage thread contexts and state configurations
active_background_tasks = set()
processing_users = set()  # Tracks users currently running an active AI generation thread

# =====================================================================
# CORE ENGINE DATABASE LOGIC
# =====================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.commit()
    conn.close()

def get_history(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chat_history WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r, "parts": [c]} for r, c in rows]

def save_message(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()

# =====================================================================
# SANITIZED PDF GENERATOR SERVICE
# =====================================================================
def create_itinerary_pdf(itinerary_text: str) -> io.BytesIO:
    """Compiles AI markdown strings safely into a print-ready PDF using XML sanitization."""
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, leading=26, spaceAfter=15)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=11, leading=16, spaceAfter=8)
    bullet_style = ParagraphStyle('BulletStyle', parent=styles['Normal'], fontSize=11, leading=16, leftIndent=15, spaceAfter=6)
    
    story.append(Paragraph("✈️ EasyTrip — Your Custom Handmap Plan", title_style))
    story.append(Spacer(1, 10))
    
    raw_lines = itinerary_text.split('\n')
    for line in raw_lines:
        clean_line = line.strip()
        if not clean_line:
            story.append(Spacer(1, 6))
            continue
            
        # Identify bullet points dynamically
        is_bullet = False
        if clean_line.startswith('- ') or clean_line.startswith('* '):
            is_bullet = True
            clean_line = clean_line[2:]
            
        # Format heading tags cleanly
        is_heading = False
        if clean_line.startswith('### ') or clean_line.startswith('## '):
            is_heading = True
            clean_line = clean_line.lstrip('#').strip()

        # FIX: Explicit XML Escaping keeps special characters from erasing paragraphs
        escaped_line = html.escape(clean_line)
        
        # Safe translation of markdown bold tags to native ReportLab paragraph syntax
        while "**" in escaped_line:
            escaped_line = escaped_line.replace("**", "<b>", 1).replace("**", "</b>", 1)
            
        if is_heading:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>{escaped_line}</b>", body_style))
            story.append(Spacer(1, 2))
        elif is_bullet:
            story.append(Paragraph(f"• {escaped_line}", bullet_style))
        else:
            story.append(Paragraph(escaped_line, body_style))
        
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer

# =====================================================================
# SYSTEM PROMPT ALIGNMENT
# =====================================================================
SYSTEM_INSTRUCTION = """
You are an empathetic, natural, and efficient travel intake assistant for EasyTrip agency.

STAGE 1: GATHERING INFORMATION
Ask 1-2 short questions at a time to gather exactly these 5 elements:
1. Destination
2. Budget boundaries (budget, mid-range, luxury)
3. Duration of stay
4. Vibe or specific interests
5. Dietary preferences or restrictions

STAGE 2: PRESENTING THE SUMMARY
The absolute second you have collected all 5 pieces of information, immediately present a clean text-based review summary titled exactly: "✨ **Final Plan Review**".
List out all 5 gathered details cleanly using bullet points. Conclude the message by asking: "Do you want to make any changes? If it looks good, let me know and I will build your detailed handmap plan PDF file!"

STAGE 3: DETAILED ITINERARY & PDF TRIGGER
ONLY after the user confirms everything looks good (e.g., says "yes", "looks great", "no changes", "finalize"):
Generate a comprehensive, highly specific breakdown for their destination matching their budget tier. You MUST include:
- Transit tips: Specific transit modes with real approximate local costs (e.g., Metro ticket - $3).
- Lodging/Accommodations: Estimated nightly rates for their specific budget tier in suggested neighborhoods.
- Food & Dining: Specific local dishes or street food examples with real pricing, try to include at least 5-6 most popular dishes of Turkey (e.g., Doner Kebab - $2, Balik Ekmek - $3, popular ice-cream, don't limit yourself with this examples.).
- Historical/Sightseeing Routes: Name specific attractions, how to get there, and approximate entry ticket fees.

Format this plan beautifully using bullet points and bold text headers. At the absolute end of your detailed response text, append the exact token: [TRIGGER_PDF]
"""

# =====================================================================
# TELEGRAM DISPATCH HANDLERS
# =====================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    welcome = "👋 Welcome to EasyTrip! I'm your AI partner. Where are we traveling next?"
    await message.answer(welcome)

@dp.message()
async def handle_chat_turn(message: types.Message):
    user_id = message.from_user.id
    if not message.text:
        return

    # Anti-Spam state tracking intercepts impatient double-typing instantly
    if user_id in processing_users:
        await message.answer("⏳ *I'm already working on it! Just a few more adjustments to your itinerary, give me a brief moment...* ✈️", parse_mode="Markdown")
        return

    history_rows = get_history(user_id)
    
    # Proactive check to see if the user is confirming the summary layout
    is_confirming_final_plan = False
    for row in reversed(history_rows):
        if row['role'] == 'model' and "Final Plan Review" in row['parts'][0]:
            is_confirming_final_plan = True
            break
            
    confirm_keywords = ["yes", "good", "great", "ok", "fine", "perfect", "finalize", "sure", "yep", "no changes", "looks good"]
    
    if is_confirming_final_plan and any(kw in message.text.lower() for kw in confirm_keywords):
        await message.answer("🚀 *Got your confirmation! Building your detailed itinerary right now. Just a few final adjustments...* ✈️", parse_mode="Markdown")

    # Lock down the processing pipeline for this user ID
    processing_users.add(user_id)
    save_message(user_id, "user", message.text)
    
    # Rehydrate the chat history log
    updated_history = get_history(user_id)
    contents_payload = []
    for row in updated_history:
        contents_payload.append(
            genai_types.Content(role=row["role"], parts=[genai_types.Part.from_text(text=row["parts"][0])])
        )

    try:
        response = await ai_client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents_payload,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                max_output_tokens=2000, # Clean headroom allocation
                temperature=0.3
            )
        )
        
        ai_response_text = response.text if response.text else ""

        if "[TRIGGER_PDF]" in ai_response_text:
            clean_itinerary = ai_response_text.replace("[TRIGGER_PDF]", "").strip()
            
            # FIX: Stitch together all itinerary parts generated across separate turns
            full_itinerary_chunks = []
            found_summary = False
            
            for row in history_rows:  # Scan the database history rows
                if row["role"] == "model":
                    text = row["parts"][0]
                    if "Final Plan Review" in text:
                        found_summary = True
                        continue  # Skip the summary block itself
                    if found_summary:
                        full_itinerary_chunks.append(text)
            
            # Append the fresh incoming final chunk (with trigger tag stripped)
            full_itinerary_chunks.append(clean_itinerary)
            
            # Create the definitive comprehensive master text block
            master_itinerary_text = "\n\n".join(full_itinerary_chunks)
            
            # Send the text breakdown gracefully to the Telegram interface
            if clean_itinerary:
                if len(clean_itinerary) > 4000:
                    for chunk in [clean_itinerary[i:i+4000] for i in range(0, len(clean_itinerary), 4000)]:
                        await message.answer(chunk)
                else:
                    await message.answer(clean_itinerary)
            
            await message.answer("⚙️ *Compiling your complete multi-turn itinerary details into a PDF document...*", parse_mode="Markdown")
            
            # Pass the complete multi-message master text block directly to your ReportLab generator
            pdf_data = create_itinerary_pdf(master_itinerary_text)
            input_file = BufferedInputFile(pdf_data.read(), filename="EasyTrip_Itinerary.pdf")
            
            await message.answer_document(document=input_file, caption="✈️ Your complete printable travel companion document is ready! Safe travels!")
            
            # Clear historical context so they can plan a fresh trip next time
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        else:
            if ai_response_text:
                save_message(user_id, "model", ai_response_text)
                await message.answer(ai_response_text)
            else:
                await message.answer("Let's make sure I have that down correctly. Could you repeat your last response?")

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Engine Exception: {error_msg}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await message.answer("⏳ *EasyTrip is taking a brief 60-second breather due to high traffic. Please wait one minute before sending your next message!*", parse_mode="Markdown")
        else:
            await message.answer(f"❌ Debug Error: {error_msg}")
            
    finally:
        # ALWAYS unlock the user context so they can continue sending messages
        processing_users.discard(user_id)

# =====================================================================
# LIFECYCLE MANAGEMENT & WEB SYSTEM
# =====================================================================
async def run_bot_resiliently():
    while True:
        try:
            logging.info("Launching aiogram polling engine...")
            await dp.start_polling(bot, handle_signals=False, polling_timeout=30)
        except asyncio.CancelledError:
            break
        except Exception as proxy_error:
            logging.exception("CRITICAL Polling loop failure!")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    init_db()
    supervisor_task = asyncio.create_task(run_bot_resiliently())
    active_background_tasks.add(supervisor_task)
    supervisor_task.add_done_callback(active_background_tasks.discard)
    yield
    await dp.stop_polling()
    supervisor_task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "EasyTrip Core Engine is online 24/7"}
