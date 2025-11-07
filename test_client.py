import asyncio
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
            await conn.send(b'world!', GameNetProtocol.UNRELIABLE)
            await asyncio.sleep(1)
            alternate = False
        else:
            print("Sending hello reliable...")
            await conn.send(b'Hello ', GameNetProtocol.RELIABLE)
            await asyncio.sleep(1)
            alternate = True

async def main():
    client = gamenet.Client(certs, connected)
    await client.connect('127.0.0.1', 8001)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
