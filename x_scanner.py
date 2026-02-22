#!/usr/bin/env python3
"""
X Trend Scanner — runs on cron, scans X for AI video business opportunities,
sends findings to Telegram.

Setup: crontab -e → 0 */4 * * * /root/videobot/venv/bin/python /root/videobot/x_scanner.py

Runs every 4 hours, scans X via Grok for trending topics in target niches,
generates video ideas, sends digest to Telegram.
"""

import logging
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # Your personal chat ID
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("x_scanner")

# Niches to scan (high CPM / high potential)
NICHES = [
    {
        "name": "AI & Tech",
        "query": "Search X/Twitter for the most viral and engaging tweets from the last 6 hours about AI tools, AI video generation, AI business opportunities, new AI products launching. Focus on tweets with high engagement (likes, retweets, quotes). Include tweets about Sora, Veo, Runway, Kling, ElevenLabs, Midjourney, or any AI creative tools.",
    },
    {
        "name": "Finance & Business",
        "query": "Search X/Twitter for the most viral tweets from the last 6 hours about money, investing, startups, entrepreneurship, side hustles, passive income, crypto, stock market moves, financial news. Focus on controversial takes, surprising data, or stories that would make great explainer videos.",
    },
    {
        "name": "Viral Debates & Culture",
        "query": "Search X/Twitter for the most heated debates and viral discussions from the last 6 hours. Topics that are polarizing, thought-provoking, or trending. Culture war topics, political controversies, social media drama, celebrity takes. Focus on threads with thousands of replies and quote tweets.",
    },
    {
        "name": "Science & Education",
        "query": "Search X/Twitter for the most interesting science discoveries, research papers, educational content, or mind-blowing facts shared in the last 6 hours. Focus on tweets that would make great educational YouTube explainer videos.",
    },
]

HISTORY_FILE = "/tmp/videobot/scanner_history.json"


def _load_history() -> set:
    """Load previously sent topic hashes to avoid duplicates."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                # Keep only last 200 entries
                return set(data[-200:])
    except Exception:
        pass
    return set()


def _save_history(history: set):
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(history)[-200:], f)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


def _grok_scan(query: str) -> str:
    """Use Grok to scan X with native access."""
    if not XAI_API_KEY:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

        response = client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": query}],
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok scan error: {e}")
        return None


def _haiku_analyze(niche_results: dict) -> str:
    """Use Haiku to analyze Grok findings and generate video ideas."""
    if not ANTHROPIC_API_KEY:
        return None

    try:
        context = ""
        for niche, result in niche_results.items():
            if result:
                context += f"\n\n--- {niche} ---\n{result}"

        prompt = (
            f"You are a YouTube content strategist. Analyze these trending X/Twitter topics "
            f"and generate the TOP 5 video ideas that would perform best on YouTube right now.\n\n"
            f"TRENDING ON X RIGHT NOW:{context}\n\n"
            f"For each idea, provide:\n"
            f"1. TITLE: A clickable YouTube title (under 70 chars)\n"
            f"2. FORMAT: Short (~30s animated) or Long (5-10min explainer)\n"
            f"3. NICHE: Which niche category\n"
            f"4. WHY: Why this would get views right now (1 sentence)\n"
            f"5. TWEET: The specific tweet/topic to use as source\n"
            f"6. CPM ESTIMATE: Expected CPM range for this niche\n\n"
            f"Rank by potential. Focus on ideas that are:\n"
            f"- Timely (happening right now)\n"
            f"- Controversial or surprising (drives engagement)\n"
            f"- In high-CPM niches (finance, tech, education)\n"
            f"- Suitable for AI video generation\n\n"
            f"Format as a clean numbered list. Be specific, not generic."
        )

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )

        if response.status_code == 200:
            return response.json()["content"][0]["text"]
        logger.error(f"Haiku error: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Haiku analysis error: {e}")
        return None


def _send_telegram(message: str):
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return

    try:
        # Split long messages (Telegram limit is 4096 chars)
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


def main():
    logger.info("X Trend Scanner starting...")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    if not XAI_API_KEY:
        logger.error("No XAI_API_KEY set")
        return

    # Scan each niche via Grok
    niche_results = {}
    for niche in NICHES:
        logger.info(f"Scanning: {niche['name']}...")
        result = _grok_scan(niche["query"])
        if result:
            niche_results[niche["name"]] = result
            logger.info(f"  Got {len(result)} chars")
        else:
            logger.warning(f"  No results for {niche['name']}")

    if not niche_results:
        logger.error("No scan results from any niche")
        return

    # Analyze with Haiku and generate video ideas
    logger.info("Analyzing trends with Haiku...")
    analysis = _haiku_analyze(niche_results)

    if not analysis:
        logger.error("Haiku analysis failed")
        return

    # Build Telegram message
    message = (
        f"*🔍 X Trend Scanner — {now}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Paste any tweet URL to OpenClaw bot to create a video!_"
    )

    # Send to Telegram
    _send_telegram(message)
    logger.info("Scan complete, sent to Telegram!")


if __name__ == "__main__":
    main()
