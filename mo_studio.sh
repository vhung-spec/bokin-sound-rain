#!/bin/sh
# Chạy để mở Rain Mixer Studio
cd "$(dirname "$0")" || exit 1
exec python3 rainmix.py studio "$@"
