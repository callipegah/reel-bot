import asyncio, os, sys, tempfile
os.environ.update(TELEGRAM_BOT_TOKEN="x", STT_API_KEY="x", LLM_API_KEY="x",
                  ALLOWED_USER_ID="42", DATA_DIR=tempfile.mkdtemp())
import bot
_real_summarize = bot.summarize

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
r = asyncio.run(bot.process("AAA", "https://www.instagram.com/reel/AAA/", "fa", 42))
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

# summarize() response parsing (OpenAI-compatible), network mocked
import httpx
def _mock(payload, status=200):
    def h(request):
        assert request.url.path.endswith("/chat/completions") and request.headers["authorization"] == "Bearer x"
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(h)
_Real = httpx.AsyncClient
def _patch(payload, status=200):
    bot.httpx.AsyncClient = lambda **kw: _Real(transport=_mock(payload, status), **kw)
ok = {"choices": [{"message": {"role": "assistant", "content": " خلاصه "}}]}
_patch(ok); assert asyncio.run(_real_summarize("c", "t", "fa")) == "خلاصه"
_patch({"choices": [{"message": {"content": ""}}]})
try: asyncio.run(_real_summarize("c", "t", "fa")); raise SystemExit("should fail")
except bot.BotError: pass
_patch({"error": "x"}, 401)
try: asyncio.run(_real_summarize("c", "t", "fa")); raise SystemExit("should fail")
except bot.BotError as e: assert "401" in str(e)
print("LLM PARSING OK")

# follow-up chat: context + history, LLM mocked
ctx = bot.get_context(42)
assert ctx and ctx["code"] == "AAA" and ctx["summary"] == "summary text", ctx
seen = {}
async def fake_llm(system, messages):
    seen["system"], seen["messages"] = system, messages
    return "shorter version"
bot.llm = fake_llm
assert asyncio.run(bot.chat(42, "make it shorter")) == "shorter version"
assert "this is a long enough transcript" in seen["system"] and "summary text" in seen["system"]
assert seen["messages"] == [{"role": "user", "content": "make it shorter"}]
asyncio.run(bot.chat(42, "and now longer"))
assert [m["content"] for m in seen["messages"]] == ["make it shorter", "shorter version", "and now longer"]
assert asyncio.run(bot.chat(999, "hi")) is None          # no reel yet for this user
for i in range(30): bot.add_history(42, "user", f"m{i}")
assert len(bot.get_history(42)) == bot.HISTORY_LIMIT
# a new reel resets the conversation; a cached reel also restores its context
bot.set_context(42, "ZZZ", "c", "t", "s"); assert bot.get_history(42) == []
r3 = asyncio.run(bot.process("AAA", "https://www.instagram.com/reel/AAA/", "fa", 42))
assert r3 == r and bot.get_context(42)["code"] == "AAA"
print("CHAT OK")

# radar: inbox submission -> dedupe, age filter, digest
assert bot.is_duplicate('Comment "47" and I send the setup', ['Comment "47" and I will DM you'])
assert not bot.is_duplicate("Totally different caption about MCP servers", ['Comment "47" and I send the setup'])
now = bot.time.time()
metas = {
    "RAD1AAAAA": {"timestamp": now - 3600, "description": 'Comment "47" and I\'ll send you the system', "uploader": "acct", "duration": 40},
    "RAD2BBBBB": {"timestamp": now - 7200, "description": 'Comment "47" and I\'ll DM you the setup', "uploader": "acct", "duration": 40},
    "RAD3CCCCC": {"timestamp": now - 30 * 86400, "description": "old reel from last month", "uploader": "acct", "duration": 30},
    "RAD4DDDDD": {"timestamp": now - 86400, "description": "Claude Code now supports hooks for agents", "uploader": "acct", "duration": 50},
}
bot.fetch_meta = lambda url: metas[url.split("/reel/")[1].strip("/")]
bot.transcribe = fake_tr
async def fake_su2(c, t, l): return "radar summary"
bot.summarize = fake_su2
sent = []
class FakeBot:
    async def send_message(self, chat_id, text, **kw): sent.append((chat_id, text))
class FakeApp: bot = FakeBot()
sub = bot.INBOX / "t.json"
sub.write_text(bot.json.dumps({"handle": "acct", "codes": list(metas)}), encoding="utf-8")
asyncio.run(bot.process_submission(FakeApp(), sub))
texts = [x[1] for x in sent]
assert all(cid == 42 for cid, _ in sent)
assert "2 new reel(s)" in texts[0] and "1 near-duplicate" in texts[0] and "1 older than" in texts[0], texts[0]
assert sum("radar summary" in x for x in texts) == 2 and "RAD1AAAAA" in " ".join(texts) and "RAD4DDDDD" in " ".join(texts)
assert "RAD2BBBBB" not in " ".join(texts) and "RAD3CCCCC" not in " ".join(texts)
sent.clear()
asyncio.run(bot.process_submission(FakeApp(), sub))   # same codes again -> nothing new, silent
assert sent == [], sent
print("RADAR OK")

# radar: the most-liked reel represents a group of near-duplicates
metas2 = {
    "PICK1AAAAA": {"timestamp": now - 1000, "description": 'Comment "ZED" and I will send the build', "uploader": "acct2", "duration": 40, "like_count": 3},
    "PICK2BBBBB": {"timestamp": now - 90000, "description": 'Comment "ZED" and I will DM you the build', "uploader": "acct2", "duration": 40, "like_count": 787, "comment_count": 20},
}
bot.fetch_meta = lambda url: metas2[url.split("/reel/")[1].strip("/")]
sent.clear()
sub2 = bot.INBOX / "t2.json"
sub2.write_text(bot.json.dumps({"handle": "acct2", "codes": list(metas2)}), encoding="utf-8")
asyncio.run(bot.process_submission(FakeApp(), sub2))
joined = " ".join(x[1] for x in sent)
assert "PICK2BBBBB" in joined and "PICK1AAAAA" not in joined and "1 near-duplicate" in joined, joined
print("PICK OK")
