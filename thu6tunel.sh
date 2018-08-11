#!/bin/bash

### begin user configuration
# thu6tunnel eth0 start
# thu6tunnel eth0 stop

# iface     - interface name that is to be created for the 6in4 link
iface=sit1
touch /tmp/6tunnel

if [ -z "$1" ]; then
    local_iface="eth0"
else
    local_iface="$1"
fi

# server_ipv4 - ipv4 address of the server that is providing the 6in4 tunnel
#server_ipv4=59.66.4.50
server_ipv4=166.111.21.1

# client_ipv4 - ipv4 address of the client that is receiving the 6in4 tunnel
client_ipv4=$(ip addr show dev ${local_iface}|grep -m 1 'inet\ '|awk '{print $2}'|cut -d/ -f1)
echo ${client_ipv4}

# client_ipv6 - ipv6 address of the client 6in4 tunnel endpoint
#client_ipv6=2001:da8:200:900e:0:5efe:${client_ipv4}/64
client_ipv6=2402:f000:1:1501:200:5efe:${client_ipv4}/64

# link_mtu    - set the mtu for the 6in4 link
link_mtu=1480

# tunnel_ttl  - set the ttl for the 6in4 tunnel
tunnel_ttl=64

### end user configuration

case "$2" in
  start)
    ifconfig $iface &>/dev/null
    if [ $? -eq 0 ]; then
      exit 1
    fi
 ip tunnel add $iface mode sit remote $server_ipv4 local $client_ipv4 
 ip link set $iface up
    ip addr add $client_ipv6 dev $iface
    #ip route add ::/0 via 2001:da8:200:900e::1 metric 1 dev $iface
    ip route add ::/0 via 2402:f000:1:1501::1 metric 1 dev $iface

    ;;
  stop)
    ifconfig $iface &>/dev/null
    if [ $? -ne 0 ]; then
      exit 1
    fi
    ip link set $iface down
    ip tunnel del $iface
    ;;
  *)
    $0 eth0 start
    ;;
esac
exit 0
