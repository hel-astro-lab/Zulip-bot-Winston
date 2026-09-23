# Winston

Winston is a Zulip *generic bot*. The bot long-polls the Zulip event API, so it sees every message in the channels it is subscribed to plus every direct message and @-mention, and replies through the REST API. It runs on any machine with outbound HTTPS to the Zulip server. A laptop is fine. 

Features are classes in `winston/features/`. A feature reacts to messages, runs on a daily schedule, or both. To add one, write the class and register it in `winston/features/__init__.py`.

## arXiv cards

When someone posts an arXiv link in `#papers`, Winston replies in the same topic with the title, the arXiv id with category and date, the authors, and the abstract in a spoiler block. Each paper is answered once per topic. `@Winston arxiv <id or link>` asks for a card anywhere.

## Daily arXiv digest

Every weekday morning Winston reads the new astro-ph listing, keeps the papers with an author from `authors.txt`, and posts one message in `#papers`. Nothing is posted on days without a hit.

`authors.txt` lists one name per line, surname first: `Nättilä, Joonas`, `Nättilä, J.`, or `Nättilä`. A bare surname matches any first name. Winston re-reads the file on every run, so editing it needs no restart. `@Winston digest` runs the digest at any time.

# Setup

## Zulip

An organization administrator creates the bot: Personal settings → Bots → Add a new bot, type **Generic bot**, name *Winston*. Download its `zuliprc` file and treat it as a password. Subscribe Winston to `#papers`.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest

./setup.sh # automated install script that copies winston.toml and authors.txt to ~/.config/winston
mv ~/Downloads/zuliprc ~/.config/winston/zuliprc && chmod 600 ~/.config/winston/zuliprc
```

Edit `~/.config/winston/winston.toml` (channels, time zone, digest time) and `authors.txt`. Then:

```sh
.venv/bin/winston check 2406.01234        # print a paper card, no Zulip needed
.venv/bin/winston run-feature digest      # post today's digest once
.venv/bin/winston run                     # run the bot in the foreground
```

## Run in the background

On macOS, `deploy/com.winston.bot.plist` is a launchd agent that starts Winston at login and restarts it if it exits. Edit the absolute paths, then:

```sh
mkdir -p ~/Library/Logs/winston
cp deploy/com.winston.bot.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.winston.bot.plist
tail -f ~/Library/Logs/winston/winston.log
```

On a Linux host, `deploy/winston.service` is the equivalent systemd unit, and `deploy/Dockerfile` builds a container; both expect the config directory at `/etc/winston`.

`winston run-feature <name>` runs one scheduled feature and exits, so an external cron can trigger scheduled posts when no machine of ours is awake.
