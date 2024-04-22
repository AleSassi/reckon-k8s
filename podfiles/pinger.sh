#!/bin/bash

_term() {
    echo "Killing ping manually to terminate"
    kill -9 "$child" 2>/dev/null
}

trap _term SIGTERM

EGG=$(echo $POD_IP | cut -f1  -d'/' | tr -d '.')
ping -s 120 -p "$EGG" 10.0.0.1 &

child=$!
wait "$child"