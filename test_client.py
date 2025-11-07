import asyncio
import gamenet
import argparse

from common import random_pokemon_payload
from gamenet import GameNetProtocol

certs = ("cert.pem", "key.pem")

def parse_channel_id(x: str) -> GameNetProtocol:
    x = str(x).strip().lower()
    if x in {"0", "r", "rel", "reliable"}:
        return GameNetProtocol.RELIABLE
    if x in {"1", "u", "unrel", "unreliable"}:
        return GameNetProtocol.UNRELIABLE
    raise argparse.ArgumentTypeError("channel-id must be: 0|reliable or 1|unreliable")

async def connected(conn, channel_id: int, packet_count: int, interval: float):
    run = True
    print("Connected to server.")

    async def conn_closed():
        nonlocal run
        print("Connection closed.")
        run = False

    conn.on_close(conn_closed)

    for i in range(packet_count):
        if not i % 5: #show stats every 5 packets
            print(conn.stats())

        if channel_id == 0:
            await conn.send(random_pokemon_payload(GameNetProtocol.RELIABLE.value),GameNetProtocol.RELIABLE)
            await asyncio.sleep(interval)
        else:
            await conn.send(random_pokemon_payload(GameNetProtocol.UNRELIABLE.value),GameNetProtocol.UNRELIABLE)
            await asyncio.sleep(interval)

async def main():
    parser = argparse.ArgumentParser(description="GameNet QUIC test client")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--port", type=int, default=8001, help="Server port")
    parser.add_argument("--cert", default="cert.pem", help="Certificate file")
    parser.add_argument("--key", default="key.pem", help="Private key file")
    parser.add_argument("--channel-id", type=int, choices=[0, 1], default=0, help="0 = reliable (stream), 1 = unreliable (datagram)")
    parser.add_argument("--packet-count", type=int, default=10, help="Number of packets to send")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between packets")
    args = parser.parse_args()

    certs = (args.cert, args.key)

    async def on_connected(conn):
        await connected(conn, args.channel_id, args.packet_count, args.interval)

    client = gamenet.Client(certs, on_connected)
    await client.connect(args.host, args.port)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
