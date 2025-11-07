import asyncio
import gamenet
from gamenet import GameNetProtocol

certs = ("cert.pem", "key.pem")

async def new_client_connected(conn):
    print("New client connected.")

    async def conn_closed():
        print("Client disconnected.")

    async def process_data(channel, data, seq, timestamp):
        if channel is GameNetProtocol.RELIABLE:
            # reliable data
            print(f"Received: [{seq}, {timestamp}, reliable]: {data.decode()}")
        else:
            # unreliable data
            print(f"Received: [{seq}, {timestamp}, unreliable]: {data.decode()}")

    conn.on_data(process_data)
    conn.on_close(conn_closed)

async def main():
    server = gamenet.Server(certs, new_client_connected)
    await server.listen(8001)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
