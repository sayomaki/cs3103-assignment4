"""
CS3103 - GameNetAPI based on QUIC

@authors Reanee Chua, Ng Hong Ray, Ryan Warwick Han, Zhang Yao

This library provides both a reliable & unreliable communication link between clients & server, built 
on top of QUIC with a lightweight protocol.
"""

import ssl
import struct
import time

from enum import Enum
from functools import partial
from aioquic.asyncio import serve, connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, DatagramFrameReceived, HandshakeCompleted, ConnectionTerminated

class GameNetProtocol(Enum):
    """
    GameNetProtocol - Flags to be used when sending/receiving data
    """
    RELIABLE = 0
    UNRELIABLE = 1


class GameNetConnection:
    """
    GameNetConnection - Represents a connection between a client & server
    """
    def __init__(self, gamenet, connection):
        self.gamenet = gamenet
        self._conn = connection

        # callback handlers
        self._on_data_received = None
        self._on_close = None

    def on_data(self, handler):
        self._on_data_received = handler

    def on_close(self, handler):
        self._on_close = handler

    async def send(self, data, flags):
        timestamp = struct.pack('<I', int(time.time())) # timestamp in secs

        if flags is GameNetProtocol.RELIABLE:
            seq = struct.pack('<H', self._conn.seq_reliable)
            self._conn.seq_reliable += 1

            header = b'\0' + seq + timestamp + b'\0'
            self._conn._quic.send_stream_data(self._conn.reliable_stream_id, header + data)
            self._conn.transmit() # no buffering, send immediately
        elif flags is GameNetProtocol.UNRELIABLE:
            seq = struct.pack('<H', self._conn.seq_unreliable)
            self._conn.seq_unreliable += 1

            header = b'\1' + seq + timestamp + b'\0'
            self._conn._quic.send_datagram_frame(header + data)
            self._conn.transmit() # no buffering, send immediately

    async def close(self):
        if self.gamenet._is_client:
            self.gamenet.close()
        else:
            self._conn.close()
            self._conn.transmit()

    def stats(self):
        stats = self._conn._quic._loss
        return {
            'rtt_latest': stats._rtt_latest,
            'rtt_avg': stats._rtt_smoothed,
            'rtt_min': stats._rtt_min
        }


class GameNetServerProtocol(QuicConnectionProtocol):
    """
    GameNetServerProtocol - Handles gamenet protocol packets on both client & server side

    Protocol header specification (8 Bytes): 
    0                                                                          8
    |---------|---------|---------|--------|--------|--------|--------|--------|
    | chn(1B) | sequence no. (2B) |           timestamp (4B)          | unused |
    |---------|---------|---------|--------|--------|--------|--------|--------|
    """
    def __init__(self, *args, gamenet, **kwargs): 
        # client - connected to server, server - new connection from client
        super().__init__(*args, **kwargs)
        self.gamenet = gamenet
        self.connection = GameNetConnection(gamenet, self)

        # sequence numbers
        self.seq_reliable = 0
        self.seq_unreliable = 0

        self.reliable_stream_id = self._quic.get_next_available_stream_id(is_unidirectional = False)

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            # connection established for reliable
            self._call_handler_async(self.gamenet._on_connect, self.connection)
        elif isinstance(event, StreamDataReceived): 
            # received in-order reliable packet
            self._handle_reliable_data(event.data)
        elif isinstance(event, DatagramFrameReceived):
            # received unreliable packet
            self._handle_unreliable_data(event.data)
        elif isinstance(event, ConnectionTerminated):
            # client/server closed connection
            self._handle_conn_closed()

    def process_header(self, header):
        channel, seq, timestamp = struct.unpack('<BHI', header[:7])
        return channel, seq, timestamp

    def _handle_reliable_data(self, data):
        channel, seq, timestamp = self.process_header(data[:8])
        data = data[8:]

        if self.connection._on_data_received is None:
            # user did not provider handler, ignore packet
            return
        
        self._call_handler_async(
            self.connection._on_data_received, 
            GameNetProtocol.RELIABLE, 
            data, 
            timestamp, 
            seq
        )

    def _handle_unreliable_data(self, data):
        channel, seq, timestamp = self.process_header(data[:8])
        data = data[8:]

        if self.connection._on_data_received is None:
            # user did not provider handler, ignore packet
            return
        
        self._call_handler_async(
            self.connection._on_data_received, 
            GameNetProtocol.UNRELIABLE, 
            data, 
            timestamp, 
            seq
        )    

    def _handle_conn_closed(self):
        if self.connection._on_close is None:
            # user did not provider handler, ignore
            return
        
        self._call_handler_async(self.connection._on_close)

    def _call_handler_async(self, handler, *args):
        loop = self._loop
        loop.create_task(handler(*args))


class GameNet:
    # shared GameNet structure for server/client
    ALPN = "gamenet"
    datagram_frame_size = 1200 # less than typical UDP MTU, but large enough

    def __init__(self, *, is_client, cert_file, key_file, verify_cert = True, on_connect):
        self._is_client = is_client
        self._config = QuicConfiguration(
            is_client = self._is_client, 
            alpn_protocols = [GameNet.ALPN], 
            max_datagram_frame_size = self.datagram_frame_size
        )

        self._config.load_cert_chain(cert_file, key_file)

        if not verify_cert:
            self._config.verify_mode = ssl.CERT_NONE

        self._on_connect = on_connect # register connect callback handler

        self._ready = 0 # used to check if listen/connect already called TODO

        self._context = None
        self._instance = None

    def is_client(self):
        return self._is_client

    async def listen(self, port = None, host = '127.0.0.1'):
        if self._is_client:
            raise Exception('Cannot listen in client mode!')

        if port is None:
            raise Exception('No port provided to listen!')
        
        self._instance = await serve(
            host = host, 
            port = port, 
            configuration = self._config, 
            create_protocol = partial(GameNetServerProtocol, gamenet = self)
        )

    async def connect(self, host, port):
        if not self._is_client:
            raise Exception('Cannot connect in server mode!')
        
        if not host:
            raise Exception('Invalid host to connect to!')

        if port is None:
            raise Exception('No port to connect to!')

        self._context = connect(
            host, port, 
            configuration = self._config, 
            create_protocol = partial(GameNetServerProtocol, gamenet = self)
        )
        self._instance = await self._context.__aenter__()

    async def close():
        if self._is_client:
            await self._context.__aexit__()
            self._context = None
            self._instance = None
            

def Server(certs, on_connect):
    return GameNet(is_client = False, cert_file = certs[0], key_file = certs[1], on_connect = on_connect)

def Client(certs, on_connect):
    return GameNet(is_client = True, cert_file = certs[0], key_file = certs[1], on_connect = on_connect, verify_cert = False)
