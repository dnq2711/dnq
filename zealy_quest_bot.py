#!/usr/bin/env python3
"""
Zealy new-quest watcher for the Mame Inu community.

It checks the Mame Inu Zealy questboard for quests that weren't seen
on the previous run, and sends a Telegram message for each new one.

State (the list of already-seen quest IDs) is kept in seen_quests.json
so the GitHub Action can commit it back to the repo between runs.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests

SUBDOMAIN = "mameinu"
QUESTBOARD_URL = f"https://zealy.io/cw/{SUBDOMAIN}/questboard"
STATE_FILE = Path(__file__).parent / "seen_quests.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}


def load_seen():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_seen(ids):
    STATE_FILE.write_text(json.dumps(sorted(ids), indent=2))


def normalize_quest(q):
    """Pull out a stable id, a name and a category/module name from a raw quest dict."""
    qid = q.get("id") or q.get("_id") or q.get("questId")
    name = q.get("name") or q.get("title") or "Untitled quest"
    return qid, name


def fetch_via_frontend_api():
    """Try the same JSON endpoint the Zealy web app itself calls."""
    candidates = [
        f"https://api-v2.zealy.io/communities/{SUBDOMAIN}/quests",
        f"https://api-v2.zealy.io/communities/{SUBDOMAIN}/questboard",
        f"https://api-v2.zealy.io/public/communities/{SUBDOMAIN}/quests",
    ]
    for url in candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"[frontend-api] {url} -> request error: {e}")
            continue

        print(f"[frontend-api] {url} -> HTTP {r.status_code}")
        if r.status_code != 200:
            continue

        try:
            data = r.json()
        except ValueError:
            continue

        # The payload shape can vary: a plain list, or {"quests": [...]}, etc.
        if isinstance(data, list):
            quests = data
        elif isinstance(data, dict):
            quests = data.get("quests") or data.get("data") or []
        else:
            quests = []

        if quests:
            return quests

    return None


def fetch_via_page_scrape():
    """Fallback: pull the questboard HTML and dig the embedded JSON out of it."""
    try:
        r = requests.get(QUESTBOARD_URL, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"[scrape] request error: {e}")
        return None

    print(f"[scrape] {QUESTBOARD_URL} -> HTTP {r.status_code}")
    if r.status_code != 200:
        return None

    html = r.text

    # Next.js apps often embed page props as JSON in a <script> tag.
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if m:
        try:
            next_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            next_data = None

        if next_data:
            quests = _find_quests_in_json(next_data)
            if quests:
                return quests

    # Last resort: look for any JSON blob containing a "quests" array.
    for m in re.finditer(r'\{.*?"quests"\s*:\s*\[.*?\].*?\}', html, re.DOTALL):
        try:
            blob = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        quests = _find_quests_in_json(blob)
        if quests:
            return quests

    return None


def _find_quests_in_json(obj, depth=0):
    """Recursively search a parsed JSON object for a list that looks like quests."""
    if depth > 6:
        return None

    if isinstance(obj, dict):
        if "quests" in obj and isinstance(obj["quests"], list) and obj["quests"]:
            if isinstance(obj["quests"][0], dict) and (
                "name" in obj["quests"][0] or "title" in obj["quests"][0]
            ):
                return obj["quests"]
        for v in obj.values():
            found = _find_quests_in_json(v, depth + 1)
            if found:
                return found

    elif isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and (
            "name" in obj[0] or "title" in obj[0]
        ):
            return obj
        for item in obj:
            found = _find_quests_in_json(item, depth + 1)
            if found:
                return found

    return None


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing, skipping notification:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            print(f"Telegram error {r.status_code}: {r.text}")
    except requests.RequestException as e:
        print(f"Telegram request error: {e}")


def main():
    quests = fetch_via_frontend_api()
    source = "frontend-api"

    if not quests:
        quests = fetch_via_page_scrape()
        source = "page-scrape"

    if not quests:
        print(
            "Could not retrieve any quests from Zealy via the frontend API "
            "or by scraping the page. Zealy may have changed how the "
            "questboard is served. See README for how to adapt this script."
        )
        sys.exit(1)

    print(f"Fetched {len(quests)} quests via {source}")

    seen = load_seen()
    is_first_run = len(seen) == 0

    new_quests = []
    current_ids = set()

    for q in quests:
        qid, name = normalize_quest(q)
        if qid is None:
            continue
        current_ids.add(qid)
        if qid not in seen:
            new_quests.append((qid, name))

    if is_first_run:
        # Don't spam on the very first run: just record the baseline.
        print(f"First run: recording {len(current_ids)} existing quests as baseline.")
    else:
        for qid, name in new_quests:
            msg = (
                f"🆕 <b>New Mame Inu Zealy quest!</b>\n"
                f"{name}\n"
                f"{QUESTBOARD_URL}"
            )
            send_telegram(msg)
            print(f"Notified about new quest: {name} ({qid})")

    save_seen(current_ids)


if __name__ == "__main__":
    main()
