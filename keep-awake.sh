#!/bin/sh
# Keep this Mac awake and the demo running. Close Cursor; leave this terminal.
# Closing the lid still sleeps. Plug in power. Ctrl-C stops compose and caffeinate.
set -eu
cd "$(dirname "$0")"
exec caffeinate -dims docker compose up
