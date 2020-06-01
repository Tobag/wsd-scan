#!/bin/bash

echo "Hint: you can also start wsd-scan directly with something like docker run -p 6666:6666 python /wsd-scan/wsd-scan.py start -t http://192.168.0.80:8018/wsd -s 192.168.0.157"
echo ""
echo "What is the address of your printer [http://192.168.0.80:8018/wsd]"
read address

if [[ $address -eq "" ]]; then
  address="http://192.168.0.80:8018/wsd"
fi

echo "What is your ip address [192.168.0.157]"
read self

if [[ $self -eq "" ]]; then
  self="192.168.0.157"
fi

echo "Scanner: $address"
echo "Self: $self"
echo ""
echo "Starting wsd-scan"

python /wsd-scan/wsd-scan.py start -t $address -s $self
