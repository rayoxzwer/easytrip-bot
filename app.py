import os
import sys
import json
import asyncio
import sqlite3
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai
from google.genai import types as genai_types

# Setup Logging Metrics
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Extract secrets securely from Hugging Face / Render environment injections
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logging.critical("Deployment failed: Environment variables are missing!")
    sys.exit(1)

# Initialize Engine Singletons
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
DB_FILE = "easy_trip.db"

# Global set to maintain strong references to running background processes
# This explicitly prevents Python's Garbage Collector from killing our bot loop
active_background_tasks = set()

# =====================================================================
# CORE ENGINE DATABASE LOGIC
# =====================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS final_intakes (
            user_id INTEGER PRIMARY KEY, username TEXT, structured_data TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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

def save_final_intake(user_id: int, username: str, structured_data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO final_intakes (user_id, username, structured_data) VALUES (?, ?, ?)", 
                   (user_id, username, json.dumps(structured_data, ensure_ascii=False)))
    cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# =====================================================================
# AI CORE ROUTINES
# =====================================================================
def submit_travel_intake(destination: str, budget_min: int, budget_max: int, duration_days: int, vibe: str, dietary_restrictions: str = "None", extra_notes: str = ""):
    """Invoke when target destination, explicit budget constraints, total days, specific vibe, and custom notes are gathered."""
    return {"status": "processed"}

SYSTEM_INSTRUCTION = """
You are an empathetic, natural, and efficient travel intake assistant for EasyTrip agency.
Ask only 1-2 short questions at a time. Show empathy if the user complains about stress or tiredness.
Once you capture Destination, Budget boundaries, Duration, Vibe, and Diet notes, execute 'submit_travel_intake' immediately.
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
    save_message(user_id, "model", welcome)
    await message.answer(welcome)

@dp.message()
try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=message.text
        )
        await message.answer(response.text)

    except Exception as e:
        logging.error(f"Engine Exception: {e}")
        # SWAP THE FALLBACK STRING FOR THIS LIVE DEBUG LINE:
        await message.answer(f"❌ Debug Error: {str(e)}")
# =====================================================================
# RESILIENT BACKGROUND SUPERVISOR
# =====================================================================
async def run_bot_resiliently():
    """
    Supervises the Telegram polling engine. If an unhandled network or proxy 
    exception escapes aiogram (common in cloud instances), this catches it, 
    prints the traceback to the logs, and forces an automatic restart.
    """
    while True:
        try:
            logging.info("Launching aiogram polling engine...")
            # Enforce an explicit 30-second long-polling timeout
            await dp.start_polling(bot, handle_signals=False, polling_timeout=30)
        except asyncio.CancelledError:
            logging.info("Polling worker received cancellation signal. Exiting clean.")
            break
        except Exception as proxy_error:
            logging.exception("CRITICAL: Internal polling loop caught an escaping exception!")
            logging.info("Re-establishing connection to Telegram API in 5 seconds...")
            await asyncio.sleep(5)

# =====================================================================
# CONCURRENT LIFECYCLE MANAGEMENT (FastAPI + Telegram)
# =====================================================================
@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # Startup Initialization
    init_db()
    
    # Spin up our resilient background supervisor task
    supervisor_task = asyncio.create_task(run_bot_resiliently())
    active_background_tasks.add(supervisor_task)
    supervisor_task.add_done_callback(active_background_tasks.discard)
    
    yield
    # Clean Shutdown
    logging.info("Shutting down application layers gracefully...")
    await dp.stop_polling()
    supervisor_task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "EasyTrip Core Engine is online 24/7", "framework": "aiogram+FastAPI"}
