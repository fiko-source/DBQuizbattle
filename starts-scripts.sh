#!/bin/bash

python src/client1.py &
sleep 1

python src/client2.py &
sleep 1

python src/client3.py &