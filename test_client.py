import asyncio
import gamenet
import argparse

from common import random_pokemon_payload
from gamenet import GameNetProtocol

certs = ("cert.pem", "key.pem")

async def connected(conn):
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

import asyncio
import gamenet
import argparse

from gamenet import GameNetProtocol

certs = ("cert.pem", "key.pem")

async def connected(conn):
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
            await conn.send(b'world!', GameNetProtocol.UNRELIABLE)
            await asyncio.sleep(1)
            alternate = False
        else:
            print("Sending hello reliable...")
            await conn.send(b'Hello ', GameNetProtocol.RELIABLE)
            await asyncio.sleep(1)
            alternate = True

async def main():
    parser = argparse.ArgumentParser(description="GameNet QUIC test client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--cert", default="cert.pem")
    parser.add_argument("--key", default="key.pem")
    args = parser.parse_args()

    certs = (args.cert, args.key)
    client = gamenet.Client(certs, connected)
    await client.connect(args.host, args.port)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
