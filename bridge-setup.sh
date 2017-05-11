#/!/bin/sh
ifconfig $1 up

## 添加网桥接口 br0
brctl addbr br0

## 将 eth0 加入网桥
brctl addif br0 enp2s0

## 将 tap0 加入网桥
brctl addif br0 $1

## 启动网桥
ifconfig br0 up
