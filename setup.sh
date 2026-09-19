#!/usr/bin/env bash
# Copy Winston's example config files to ~/.config/winston. Existing files are left untouched.
# The bot credentials (zuliprc) are not handled here: download them from Zulip and put them
# at ~/.config/winston/zuliprc yourself.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${XDG_CONFIG_HOME:-$HOME/.config}/winston"
mkdir -p "$target"

install_example() {   # install_example <example file> <destination name>
    if [ -e "$target/$2" ]; then
        echo "kept     $target/$2 (already exists)"
    else
        cp "$here/$1" "$target/$2"
        echo "created  $target/$2"
    fi
}

install_example winston.toml.example winston.toml
install_example authors.txt.example authors.txt

echo
if [ -e "$target/zuliprc" ]; then
    chmod 600 "$target/zuliprc"
    echo "found    $target/zuliprc"
else
    echo "missing  $target/zuliprc  <- download it from Zulip (Personal settings > Bots) and put it there"
fi
echo
echo "Next: edit $target/authors.txt, then run  $here/.venv/bin/winston run-feature digest"
