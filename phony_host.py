#!/usr/bin/env python3
import socket
import argparse

UDP_IP = "0.0.0.0"
UDP_PORT = 987


def reply_always(host_type):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    text = """HTTP/1.1 200 OK\r
host-id:0123456789AB\r
host-type:{}\r
host-name:My{}\r
host-request-port:{}\r
device-discovery-protocol-version:00020020\r
system-version:07020001\r
running-app-name:Youtube\r
running-app-titleid:CUSA01116\r
\r
"""
    while True:
        data, addr = sock.recvfrom(1024)
        print(
            "received message from %s[%d]: %s" % (addr[0], addr[1], data.decode("utf8"))
        )

        response = text.format(host_type, host_type, addr[1])
        print(response)
        sock.sendto(response.encode("utf8"), addr)


def ask_response(ask_ip):
    text = "SRCH * HTTP/1.1\r\n\r\n"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
    sock.sendto(bytes(text, "utf-8"), (ask_ip, UDP_PORT))
    print("send to {}: {}".format((ask_ip, UDP_PORT), text))
    data, addr = sock.recvfrom(1024)
    print("received message from %s[%d]: %s" % (addr[0], addr[1], data.decode("utf8")))


def main():
    parser = argparse.ArgumentParser(
        description="Fake Console - A fake UDP console responder for testing."
    )
    parser.add_argument(
        "--host-type",
        default="SteamDeck",
        choices=[
            "PS4",
            "PS5",
            "Windows",
            "SteamDeck",
            "Xbox X",
            "Xbox S",
            "Switch",
            "Switch 2",
        ],
    )
    parser.add_argument("--ask-ip", default=None)
    args = parser.parse_args()
    if args.ask_ip is not None:
        ask_response(args.ask_ip)
    reply_always(args.host_type)


if __name__ == "__main__":
    main()
