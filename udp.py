import socket


def send_udp(msg, server_address):
    msg_bytes = msg.encode('utf-8')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(msg_bytes, server_address)

    finally:
        sock.close()
