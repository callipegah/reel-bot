import asyncio, os, sys, tempfile
os.environ.update(TELEGRAM_BOT_TOKEN="x", GROQ_API_KEY="x", ANTHROPIC_API_KEY="x",
                  ALLOWED_USER_ID="42", DATA_DIR=tempfile.mkdtemp())
import bot

# links
t = ("see https://www.instagram.com/reel/DAbC_123-x/?igsh=abc and "
     "https://instagram.com/someuser/reel/ZZZ999/ and https://www.instagram.com/p/POST1/ "
     "and again https://www.instagram.com/reel/DAbC_123-x/")
assert [c for c, _ in bot.find_reels(t)] == ["DAbC_123-x", "ZZZ999", "POST1"], bot.find_reels(t)
assert bot.find_reels("https://www.instagram.com/someuser/") == []
assert bot.ANY_IG_RE.search("https://www.instagram.com/someuser/")
assert bot.find_reels("no link here") == []

# chunking
long = "\n".join(["line " * 20] * 200)
parts = bot.chunks(long)
assert all(len(p) <= 3900 for p in parts) and "".join(parts).count("line") == 200 * 20

# prefs + cache
assert bot.get_lang(1) == "fa"; bot.set_lang(1, "en"); assert bot.get_lang(1) == "en"
bot.cache_put("k", "v"); assert bot.cache_get("k") == "v" and bot.cache_get("zz") is None

# error messages
assert "private" in bot.explain_ytdlp_error("ERROR: login required")
assert "rate-limiting" in bot.explain_ytdlp_error("HTTP Error 429")

# full pipeline with the network parts mocked
calls = {}
bot.fetch_meta = lambda url: {"duration": 42, "uploader": "someone", "description": "cap"}
def fake_dl(url, d): p = d / "audio.mp3"; p.write_bytes(b"x"); return p
bot.download_audio = fake_dl
async def fake_tr(p): return "this is a long enough transcript about agents and tools"
async def fake_su(c, t, l): calls["args"] = (c, t, l); return "summary text"
bot.transcribe, bot.summarize = fake_tr, fake_su
r = asyncio.run(bot.process("AAA", "https://www.instagram.com/reel/AAA/", "fa"))
assert r.startswith("@someone · 0:42") and r.endswith("summary text"), r
assert calls["args"][2] == "fa"
calls.clear()
r2 = asyncio.run(bot.process("AAA", "https://www.instagram.com/reel/AAA/", "fa"))  # cached
assert r2 == r and not calls
# too long
bot.fetch_meta = lambda url: {"duration": 99999}
try: asyncio.run(bot.process("BBB", "u", "fa")); raise SystemExit("should fail")
except bot.BotError as e: assert "limit" in str(e)
# tiny transcript treated as empty
bot.fetch_meta = lambda url: {"duration": 10, "uploader": "u", "description": "cap"}
async def tiny(p): return "Thank you."
bot.transcribe = tiny
asyncio.run(bot.process("CCC", "u", "en")); assert calls["args"][1] == ""
print("ALL TESTS PASSED")
