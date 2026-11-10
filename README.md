# ✈️ EasyTrip — AI-Powered Travel Assistant Bot

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%202.5%20Flash-orange.svg)
![Telegram](https://img.shields.io/badge/Telegram-Aiogram%203.x-blueviolet.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![Deploy](https://img.shields.io/badge/Hosted%20on-Render-black.svg)

**EasyTrip** is an intelligent Telegram bot designed to replace chaotic travel planning with structured, ready-to-use travel itineraries. Built on **Google Gemini 2.5 Flash**, it orchestrates multi-stage user interviews, maintains contextual dialogue memory across turns, and dynamically generates styled, downloadable PDF companion guides via a custom backend processing pipeline.

---

## ✨ Key Features

* **🎯 Multi-Stage Funnel Prompting:** Uses strict `SYSTEM_INSTRUCTION` constraints to guide users through a structured 3-phase funnel (Data Gathering ➡️ Validation & Review ➡️ Full Itinerary Compilation), eliminating hallucinated or missing parameters.
* **🧩 History-Stitching Engine:** Scans SQLite database logs across multi-turn user responses to seamlessly stitch fragmented LLM output chunks into a single unified context block for compilation.
* **📄 Automated PDF Generation:** Detects conditional LLM runtime markers (`[TRIGGER_PDF]`) to trigger backend parsing via **ReportLab**, delivering a styled, print-ready `.pdf` itinerary file directly to the chat.
* **🛡️ Asynchronous State Locking:** Implements an internal `processing_users` concurrency lock to shield the Gemini API from user message-spam and prevent `429 Rate Limit` / `RESOURCE_EXHAUSTED` exceptions.
* **🌍 Localized Pricing & Precision:** Hard-coded prompt parameters ensure granular cost breakdowns (down to individual meal estimates) without truncation.

---

## 🛠️ Tech Stack

* **Core Language:** Python 3.11 (Asyncio)
* **LLM Engine:** Google Gemini API (`gemini-2.5-flash`)
* **Bot Framework:** `aiogram` 3.x
* **Database / State:** SQLite3
* **Document Engine:** ReportLab (PDF Builder)
* **Containerization:** Docker
* **Hosting / CI/CD:** Render.com + GitHub Webhooks

---

## 🏗️ System Architecture & Workflow
[ Telegram User ] 
       │
       ▼
[ Aiogram Bot Engine ] ──(State Lock: processing_users)──► [ Intercept Double-Submit ]
       │
       ▼
[ SQLite Chat Logs ] ──(Fetch History)──► [ History-Stitching Engine ]
       │                                             │
       ▼                                             ▼
[ Gemini 2.5 Flash ] ──(Response Stream)──► [ Check Trigger: [TRIGGER_PDF] ]
                                                     │
                                       ┌─────────────┴─────────────┐
                                       ▼                           ▼
                             [ Standard Text Reply ]     [ ReportLab PDF Engine ]
                                                                   │
                                                                   ▼
                                                         [ EasyTrip_Itinerary.pdf ]
🚀 Quick Start & Local Setup

Prerequisites
Python 3.11+
Docker (optional, for containerized run)
Telegram Bot Token (from @BotFather)
Google AI Studio API Key

Installation Steps
Clone the repository:

git clone [https://github.com/your-username/EasyTrip.git](https://github.com/your-username/EasyTrip.git)
cd EasyTrip

Set up virtual environment:

Linux/macOS: python -m venv venv && source venv/bin/activate
Windows: python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

Configure Environment Variables:

Create a .env file in the root directory:

TELEGRAM_BOT_TOKEN=telegram_bot_token_here
GEMINI_API_KEY=gemini_api_key_here

Run the bot locally:

python app.py

🐳 Running with Docker
Build Image: docker build -t easytrip-bot .
Run Container: docker run -d --name easytrip --env-file .env easytrip-bot

⚙️ Environment & Production Setup

When deploying to platforms like Render.com:
Build Command: pip install -r requirements.txt
Start Command: python app.py
Environment Variables: Ensure TELEGRAM_BOT_TOKEN and GEMINI_API_KEY are configured in settings.

📜 License
Distributed under the MIT License. See LICENSE for more information.
