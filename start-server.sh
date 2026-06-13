#!/bin/sh
set -eu

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 WS_PORT CONTROL_PORT [LAN_IP] [BROADCAST_IP] [IDENTITY_FILE]"
    exit 1
fi

WS_PORT=$1
CONTROL_PORT=$2
LAN_IP=${3:-}
BROADCAST_IP=${4:-255.255.255.255}
IDENTITY_FILE=${5:-".server_uuid_${CONTROL_PORT}"}

HOST_ARGUMENT=""
if [ -n "$LAN_IP" ]; then
    HOST_ARGUMENT="--host $LAN_IP"
fi

exec python3 src/server.py \
    --identity-file "$IDENTITY_FILE" \
    --ws-port "$WS_PORT" \
    --control-port "$CONTROL_PORT" \
    --broadcast "$BROADCAST_IP" \
    $HOST_ARGUMENT
