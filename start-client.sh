#!/bin/sh
set -eu

NAME=${1:-"Player"}
BROADCAST_IP=${2:-255.255.255.255}

exec python3 src/client.py --name "$NAME" --broadcast "$BROADCAST_IP"
