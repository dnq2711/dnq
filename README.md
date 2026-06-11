# Mame Inu Zealy Quest Watcher

Checks https://zealy.io/cw/mameinu/questboard every 15 minutes and
sends you a Telegram message whenever a new quest appears.

## 1. Create a Telegram bot

1. Open Telegram, message **@BotFather**, send `/newbot`, follow the
   prompts. You'll get a **bot token** like `123456789:AAExample-Token`.
2. Start a chat with your new bot (search its username, hit Start) so
   it's allowed to message you.
3. Get your **chat ID**:
   - Send any message to your bot.
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a
     browser.
   - Find `"chat":{"id": ...}` in the JSON — that number is your chat ID.

## 2. Put the code in a GitHub repo

1. Create a new (can be private) GitHub repository.
2. Add these files to it:
   - `zealy_quest_bot.py`
   - `requirements.txt`
   - `seen_quests.json`
   - `.github/workflows/zealy-quest-watch.yml`

## 3. Add your secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**

- `TELEGRAM_BOT_TOKEN` = your bot token
- `TELEGRAM_CHAT_ID` = your chat ID

## 4. Run it

- Go to the **Actions** tab, open "Zealy Mame Inu Quest Watcher", and
  click **Run workflow** to test it manually first.
- The first run only records the current quests as a baseline (no
  notification spam). Every run after that, any new quest triggers a
  Telegram message.
- After that it runs automatically every 15 minutes (edit the cron
  schedule in the workflow file to change frequency).

## How it works / notes

- The script first tries Zealy's own front-end JSON endpoint for the
  questboard (no login/API key needed). If Zealy changes that, it
  falls back to scraping the questboard page's embedded data.
- If both methods fail, the Action run will show an error in its logs
  — that means Zealy changed something and the script needs a small
  update (the relevant code is `fetch_via_frontend_api` and
  `fetch_via_page_scrape` in `zealy_quest_bot.py`).
- State (`seen_quests.json`) is committed back to the repo by the
  workflow so the bot remembers what it already announced.
