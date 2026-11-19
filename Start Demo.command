#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    python3 start_demo.py
else
    echo "Ask a grown-up to install Python 3 from https://www.python.org/downloads/ first."
fi
printf '\nPress Enter to close this window. '
read -r answer
