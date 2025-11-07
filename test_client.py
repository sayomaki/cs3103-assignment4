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

async def connected(conn, *, channel: GameNetProtocol, packet_count: int, interval: float):
    alternate = False
    run = True
    print("Connected to server.")

    async def conn_closed():
        nonlocal run
        print("Connection closed.")
        run = False

    conn.on_close(conn_closed)

    while run:
        print(conn.stats())
        if alternate:
            print("Sending world unreliable...")
            await conn.send(random_pokemon_payload(GameNetProtocol.UNRELIABLE.value),GameNetProtocol.UNRELIABLE)
            await asyncio.sleep(1)
            alternate = False
        else:
            print("Sending hello reliable...")
            await conn.send(random_pokemon_payload(GameNetProtocol.RELIABLE.value),GameNetProtocol.RELIABLE)
            await asyncio.sleep(1)
            alternate = not alternate

async def main():
    parser = argparse.ArgumentParser(description="GameNet QUIC test client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--cert", default="cert.pem")
    parser.add_argument("--key", default="key.pem")
    parser.add_argument("--channel-id", type=parse_channel_id, default="reliable",
                        help="0|reliable or 1|unreliable")
    parser.add_argument("--packet-count", type=int, default=10,
                        help="number of packets to send")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between packets")
    args = parser.parse_args()

    certs = (args.cert, args.key)

    # pass args into the connected callback via closure
    async def on_connected(conn):
        await connected(conn, channel=args.channel_id,
                        packet_count=args.packet_count,
                        interval=args.interval)
    
    client = gamenet.Client(certs, on_connected)
    await client.connect(args.host, args.port)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
