#!/bin/sh
set -eu

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 SERVER_ID WS_PORT CONTROL_PORT [LAN_IP] [BROADCAST_IP]"
    exit 1
fi

SERVER_ID=$1
WS_PORT=$2
CONTROL_PORT=$3
LAN_IP=${4:-}
BROADCAST_IP=${5:-255.255.255.255}

HOST_ARGUMENT=""
if [ -n "$LAN_IP" ]; then
    HOST_ARGUMENT="--host $LAN_IP"
fi

exec python3 src/server.py \
    --id "$SERVER_ID" \
    --ws-port "$WS_PORT" \
    --control-port "$CONTROL_PORT" \
    --broadcast "$BROADCAST_IP" \
    $HOST_ARGUMENT
