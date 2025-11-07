import asyncio
from common import random_pokemon_payload
import gamenet

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

async def main():
    client = gamenet.Client(certs, connected)
    await client.connect('127.0.0.1', 8001)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
