#!/usr/bin/env bash
# Simple utility to ping a URL using curl and log the response.
# Usage: ./ping_url.sh <URL> [logfile]
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <URL> [logfile]" >&2
  exit 1
fi

URL="$1"
LOGFILE="${2:-ping_url.log}"

RESPONSE=$(curl -sS "$URL")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "$TIMESTAMP $RESPONSE" >> "$LOGFILE"

echo "Response logged to $LOGFILE"