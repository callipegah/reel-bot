#!/usr/bin/env python3
"""Runs on YOUR PC (not the server). For each Instagram account in handles.txt it opens the public
Reels tab in a real headless browser (no login), collects the newest reel shortcodes, and sends the
ones it has not seen before to the bot's inbox on the server over SSH. The bot then summarizes them
and sends a digest to Telegram.

Setup: see pc/README.md. Needs: pip install playwright, Microsoft Edge or Chrome, an SSH key on the server.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CODE_RE = re.compile(r"/reel/([A-Za-z0-9_-]+)/")
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
KEEP_SEEN = 300


def read_handles(only: str | None) -> list[str]:
    out = []
    for line in (HERE / "handles.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", line)
        h = (m.group(1) if m else line).lstrip("@").strip("/")
        if HANDLE_RE.match(h) and h not in out:
            out.append(h)
    return [h for h in out if h == only] if only else out


def scrape(page, handle: str) -> list[str] | None:
    page.goto(f"https://www.instagram.com/{handle}/reels/", wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_selector('a[href*="/reel/"]', timeout=20000)
    except PWTimeout:
        return None
    page.wait_for_timeout(1500)
    page.mouse.wheel(0, 2500)
    page.wait_for_timeout(1200)
    hrefs = page.eval_on_selector_all('a[href*="/reel/"]', "els => els.map(e => e.getAttribute('href'))")
    codes = []
    for h in hrefs:
        m = CODE_RE.search(h or "")
        if m and m.group(1) not in codes:
            codes.append(m.group(1))
    return codes


def submit(cfg: dict, handle: str, codes: list[str]) -> bool:
    name = f"{int(time.time())}-{handle}.json"
    inbox = cfg["inbox_dir"].rstrip("/")
    remote = (f"cat > {inbox}/{name}.tmp && chown {cfg.get('bot_user', 'reelbot')}:{cfg.get('bot_user', 'reelbot')} "
              f"{inbox}/{name}.tmp && mv {inbox}/{name}.tmp {inbox}/{name}")
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", cfg["ssh_target"], remote],
                       input=json.dumps({"handle": handle, "codes": codes}), text=True, capture_output=True, timeout=60)
    if r.returncode != 0:
        print(f"  ! could not send to server: {r.stderr.strip()[:200]}")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="scrape and print, send nothing, save nothing")
    ap.add_argument("--only", help="check just this handle")
    args = ap.parse_args()

    cfg = json.loads((HERE / "config.local.json").read_text(encoding="utf-8"))
    state_path = HERE / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    handles = read_handles(args.only)
    if not handles:
        print("No handles in handles.txt")
        return 1

    sent = failed = 0
    with sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome"):
            try:
                browser = p.chromium.launch(channel=channel, headless=True)
                break
            except Exception:
                continue
        if not browser:
            print("Could not start Edge or Chrome.")
            return 2
        ctx = browser.new_context(viewport={"width": 1280, "height": 1600}, locale="en-US")
        for i, handle in enumerate(handles):
            if i:
                time.sleep(random.uniform(6, 12))
            page = ctx.new_page()
            try:
                codes = scrape(page, handle)
            except Exception as e:
                codes = None
                print(f"@{handle}: error {type(e).__name__}: {str(e)[:100]}")
            finally:
                page.close()
            if codes is None:
                print(f"@{handle}: could not load reels (private, renamed, or blocked)")
                failed += 1
                continue
            seen = set(state.get(handle, []))
            new = [c for c in codes if c not in seen]
            print(f"@{handle}: {len(codes)} reels on the page, {len(new)} new")
            if args.dry_run:
                print("   ", ", ".join(new[:12]))
                continue
            if new and not submit(cfg, handle, new):
                failed += 1
                continue
            sent += bool(new)
            state[handle] = (codes + [c for c in state.get(handle, []) if c not in codes])[:KEEP_SEEN]
        browser.close()
    if not args.dry_run:
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print(f"done: {sent} account(s) sent, {failed} problem(s)")
    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main())
