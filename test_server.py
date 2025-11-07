import asyncio
import gamenet
import random
from gamenet import GameNetProtocol

certs = ("cert.pem", "key.pem")

async def new_client_connected(conn):
    print("New client connected.")
    counter = 8

    async def conn_closed():
        print("Client disconnected.")

    async def process_data(channel, data, seq, timestamp):
        nonlocal counter
        if channel is GameNetProtocol.RELIABLE:
            # reliable data
            print(f"Received: [{seq}, {timestamp}, reliable]: {data.decode()}")
            await conn.send(b"ACK:" + data, GameNetProtocol.RELIABLE)      # echo
        else:
            # unreliable data
            # Simulate packet loss
            if random.random() < 0.3:        # drop ~30%
                conn.skip_unreliable()
            else:   
                print(f"Received: [{seq}, {timestamp}, unreliable]: {data.decode()}")
                await conn.send(b"ACK:" + data, GameNetProtocol.UNRELIABLE)    # echo

        counter -= 1
        if counter == 0:
            await conn.close()

    conn.on_data(process_data)
    conn.on_close(conn_closed)

async def main():
    server = gamenet.Server(certs, new_client_connected)
    print("Starting server on port 8001...")
    await server.listen(8001)
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
