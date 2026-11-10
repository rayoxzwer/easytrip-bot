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
