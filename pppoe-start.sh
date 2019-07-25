#!/bin/sh 
#安装pppd，rp-pppoe
#pppoe-setup
#pppoe-start
#pppoe-stop
sudo pppoe-start
sudo route add default dev ppp0 
