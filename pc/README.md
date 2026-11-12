# PC watcher

Checks the Reels tab of the Instagram accounts in `handles.txt` (public pages, no login) and sends
new reel shortcodes to the bot on the server, which summarizes them and posts a digest to Telegram.

Setup (once):
1. `pip install playwright` (uses the Edge or Chrome you already have; nothing else to download).
2. Copy `handles.example.txt` to `handles.txt` and list the accounts. Create `config.local.json`
   with `ssh_target`, `inbox_dir` and `bot_user` (see the example in the main README). Both files are git-ignored.
3. Run `python ig_watch.py --dry-run` to see what it finds, then `python ig_watch.py`.

First run per account sends up to 12 reels; the bot ignores anything older than 7 days and collapses
near-duplicate reels. Later runs only send reels it has not seen.
