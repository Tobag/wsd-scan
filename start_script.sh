#!/bin/bash

echo "Hint: you can also start wsd-scan directly with:"
echo "  docker run -p 6666:6666 wsd-scan wsd-scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110"
echo ""
echo "What is the address of your printer [http://192.168.0.149:8018/wsd]"
read address

if [[ -z "$address" ]]; then
  address="http://192.168.0.149:8018/wsd"
fi

echo "What is your ip address [192.168.0.110]"
read self

if [[ -z "$self" ]]; then
  self="192.168.0.110"
fi

echo "Scanner: $address"
echo "Self: $self"
echo ""
echo "Starting wsd-scan"

wsd-scan start -t "$address" -s "$self"
