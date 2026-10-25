# 🎨 Pixel Fraction — Daily Color Quest Telegram Bot
> **API After Hours (OpenCode / NIT Rourkela) — Playful Track**

Pixel Fraction is an interactive Telegram community bot that gamifies everyday surroundings! Every day, it serves an inspiring, color-themed photography quest using the **Unsplash API**. Group members snap real-world photos, the bot's computer vision engine calculates the exact percentage of matching colored pixels, detects anti-cheat duplicates, and lets the community vote on the most creative submissions.

---

## 🌟 Key Features

1. **Daily Color Quests powered by Unsplash**:
   - Generates one synchronized quest per day for all groups.
   - Preserves API limits by caching daily quests (Unsplash rate-limit friendly).
   - Graceful fallback quest system if offline or rate-limited.
   - Compliant photo attribution with photographer credits.

2. **Pixel Fraction Computer Vision Engine**:
   - Analyzes photos in HSV color space to withstand varying indoor/outdoor lighting conditions.
   - **Pass:** ≥ 15% color fraction (+10 points).
   - **Critical Hit:** ≥ 40% color fraction (+25 points).

3. **Anti-Cheat Perceptual Hashing (dHash)**:
   - Computes a 64-bit difference hash to compare player uploads against the Unsplash reference photo.
   - Prevents players from simply re-uploading the daily inspiration photo!

4. **Community Engagement & Streaks**:
   - Inline interactive voting buttons (`🔥 Creative` and `🎨 Nice Find`).
   - Group leaderboards and consecutive day streak tracking.
   - Admin demo controls (`/forcequest`) for live presentations.

---

## 📐 Architecture Flow

```
+-------------------------------------------------------------+
|                      TELEGRAM USER                          |
|             (Snaps photo in DM or Group Chat)               |
+------------------------------+------------------------------+
                               |
                               | (Photo Upload / Command)
                               v
+-------------------------------------------------------------+
|               PIXEL FRACTION BOT (bot.py)                   |
|           [Render Webhook / Local Polling Engine]           |
+--------------+-------------------------------+--------------+
               |                               |
               | (1. Fetch Quest)              | (2. Anti-Cheat Check)
               v                               v
+-------------------------------+  +--------------------------+
|      UNSPLASH API CLIENT      |  |  ANTI-CHEAT ENGINE (dHash)|
|  (Random query by color name, |  |  (Similarity < 85% check)|
|   attribution & cache)        |  +--------------------------+
+-------------------------------+              |
                                               | (3. Pixel Scoring)
                                               v
                                   +--------------------------+
                                   |    COLOR SCORING ENGINE  |
                                   | (HSV Color Mask Analysis)|
                                   +--------------------------+
                                               |
                                               v
                                   +--------------------------+
                                   | DATABASE & VOTING ENGINE |
                                   | (Streaks & Leaderboard)  |
                                   +--------------------------+
```

---

## 🚀 Commands

| Command | Description |
|---|---|
| `/quest` | Displays today's color quest, target fraction, and Unsplash inspiration photo. |
| `/leaderboard` | Shows the top players and active streaks in the chat. |
| `/myid` | Shows your Telegram numeric user ID. |
| `/forcequest` | *(Admin only)* Force triggers a new color quest on the fly for live demos. |
| `/help` | Explains rules and scoring breakdown. |

---

## 🛠️ Local Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/vardhan-U/pixel-fraction.git
   cd pixel-fraction
   ```

2. **Set up virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure `.env` file:**
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   UNSPLASH_ACCESS_KEY=your_unsplash_access_key
   ADMIN_USER_ID=your_telegram_numeric_id
   ```

4. **Run Unit Tests:**
   ```bash
   python -m unittest test_engine.py -v
   ```

5. **Start Bot locally (Polling Mode):**
   ```bash
   python bot.py
   ```

---

## ☁️ Deployment on Render (Free Tier)

1. Fork or push this repository to your GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** -> **Web Service**.
3. Connect your GitHub repository `vardhan-U/pixel-fraction`.
4. Configure:
   * **Runtime:** Python
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python bot.py`
5. Under **Environment Variables**, add:
   * `TELEGRAM_BOT_TOKEN` = `your_token`
   * `UNSPLASH_ACCESS_KEY` = `your_access_key`
   * `ADMIN_USER_ID` = `your_numeric_id`
   * `WEBHOOK_URL` = `https://<your-service-name>.onrender.com`
   * `PORT` = `10000`
6. Click **Create Web Service**. Render will deploy and connect to Telegram automatically!

---

## 🎤 3-Minute Demo Pitch (Playful Track)

* **Hook (20s):** "Most chat groups suffer from passive scrolling. Pixel Fraction turns any Telegram group into a real-world scavenger hunt where your surroundings become the game board."
* **API Integration (60s):** "We combine the Unsplash API to source curated, high-aesthetic color references with custom computer vision that parses the raw pixel fraction in HSV space to score real photos fairly regardless of indoor lighting."
* **Live Walkthrough (100s):**
  1. Trigger `/quest` to reveal today's color and Unsplash inspiration photo.
  2. Take a photo of a nearby object (e.g. coffee mug, notebook, clothing).
  3. Submit it to the group: watch the bot detect the exact pixel fraction, award points, and add streak bonuses!
  4. Peers tap `🔥 Creative` or `🎨 Nice Find` buttons to vote in real-time.
