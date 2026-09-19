# Winston

Winston is a python-based Zulip bot. 

## How it works

Winston is a *generic bot* in Zulip terms: a bot user whose API key is used by this program. The program long-polls Zulip's event API, so it sees every message in the channels it is subscribed to plus every direct message and @-mention, and replies through the REST API. 

Winston is hosted on a local machine that has outbound HTTPS to the Zulip server. A laptop is fine: on restart Winston re-reads the messages it missed (up to `catch_up_hours` old) and answers those it has not answered yet.

Features live in `winston/features/`. Each one is a class with

- `wants(msg)` / `handle(msg, bot)` for message-driven behaviour; `msg.command` holds the text of a direct message or @-mention with the mention removed, and is `None` otherwise;
- `at` (from its `[features.<name>]` settings) and `run(bot)` for scheduled behaviour;
- `bot.feature_state(name)` plus `bot.save_state()` for anything that must survive a restart;
- `channels` in its settings for the channels it must see every message of.

Register a new feature in `FEATURES` in `winston/features/__init__.py`.

## Daily arXiv digest

Every announcement day Winston reads the arXiv listing for the configured categories (default `astro-ph`), keeps the new and cross-listed papers with an author from `authors.txt`, and posts one message in `#papers`. The list of `authors.txt` lives next to `winston.toml` and is re-read on every run, so editing it needs no restart. One name per line, surname first.

The scheduled time is `at` under `[features.digest]`. A morning missed because the laptop was asleep is caught up within the grace window, and `@Winston digest` (or a direct message `digest`, or `winston run-feature digest` from a shell) runs it at any time.

## arXiv info

When someone posts an arXiv link in a watched channel (`channels` under `[features.arxiv]`, default `#papers`), Winston replies in the same topic with a card: title, a line with the arXiv id, primary category and date, the authors (first ten, then *et al.*), and the abstract folded into a spoiler so the topic stays readable. 

`@Winston arxiv <id or link>` (or a direct message `arxiv …`) asks for a card explicitly, in any channel; here an unknown id gets a reply saying so. `winston check <id or link>` prints the card to the terminal without Zulip, which is the quickest way to see what a card looks like.


# Setup

## Zulip side (once, by an organization administrator)

1. Personal settings → Bots → *Add a new bot*. Bot type **Generic bot**, name *Winston*, upload the mascot as avatar.
2. Download the bot's `zuliprc` file. It holds the API key, so treat it like a password.
3. Subscribe Winston to `#papers` (Winston also subscribes itself to public channels on start).

## Local setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest

./setup.sh                                # copies winston.toml and authors.txt to ~/.config/winston
mv ~/Downloads/zuliprc ~/.config/winston/zuliprc && chmod 600 ~/.config/winston/zuliprc

.venv/bin/winston check 2406.01234        # prints a paper card, no Zulip needed
.venv/bin/winston run                     # runs in the foreground, Ctrl-C to stop
.venv/bin/winston run-feature menu        # runs one scheduled feature once (for an external cron)
```

## Running it in the background

### macOS laptop (launchd)

```sh
mkdir -p ~/Library/Logs/winston
cp deploy/com.winston.bot.plist ~/Library/LaunchAgents/     # edit the absolute paths first
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.winston.bot.plist
launchctl list | grep winston                               # running?
tail -f ~/Library/Logs/winston/winston.log
launchctl bootout gui/$(id -u)/com.winston.bot              # stop and unload
```

Winston starts at login and is restarted if it exits. While the laptop sleeps Zulip drops the event queue; on wake Winston reconnects and the catch-up handles what it missed.

### Linux host (systemd)

```sh
sudo useradd --system --home /opt/winston winston
sudo python3 -m venv /opt/winston/.venv && sudo /opt/winston/.venv/bin/pip install .
sudo install -d -o winston -m 700 /etc/winston            # put winston.toml and zuliprc here
sudo cp deploy/winston.service /etc/systemd/system/
sudo systemctl enable --now winston
journalctl -u winston -f
```

### Docker

```sh
docker build -f deploy/Dockerfile -t winston .
docker run -d --restart unless-stopped -v /etc/winston:/etc/winston winston
```

### Scheduled posts when the laptop may be asleep

`winston run-feature <name>` runs one scheduled feature and exits, so any cron can trigger it. A GitHub Actions workflow with a `schedule:` trigger (cron times are UTC, and may run a few minutes late) that installs the package and runs it with `ZULIP_CONFIG` pointing at a `zuliprc` written from a repository secret gives a schedule that does not depend on any of our machines being awake.
