# reel-bot

Telegram bot: send an Instagram reel link, get a summary back.

Flow: link -> yt-dlp (public reels only, no Instagram login) -> ffmpeg -> Groq Whisper -> Claude summary -> Telegram.

- Polling, no webhook. Replies only to the user ID in `ALLOWED_USER_ID`.
- Config: copy `.env.example` to `.env`, fill it in, `chmod 600 .env`. Never commit `.env`.
- Run as a separate systemd service: see `reel-bot.service`.
- Tests: `python test_bot.py`
