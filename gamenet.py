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
from aioquic.quic.logger import QuicLogger

class GameNetProtocol(Enum):
    """
    GameNetProtocol - Flags to be used when sending/receiving data
    """
    RELIABLE = 0
    UNRELIABLE = 1


class GameNetMetricsWrapper:
    """
    GameNetMetricsWrapper - actual class that keeps tracks of packets and data
    """
    def __init__(self, original_trace):
        self._trace = original_trace
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_lost = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.start_time = time.time()

    def log_event(self, *, category: str, event: str, data: dict):
        self._trace.log_event(category=category, event=event, data=data)

        # track metrics in real-time
        if event == "packet_sent":
            self.packets_sent += 1
            header = data.get("raw", {})
            if "length" in header:
                self.bytes_sent += header["length"]

        elif event == "packet_received":
            self.packets_received += 1
            header = data.get("raw", {})
            if "length" in header:
                self.bytes_received += header["length"]

        elif event == "packet_lost":
            self.packets_lost += 1

    def get_metrics(self):
        elapsed = time.time() - self.start_time
        metrics = {
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_lost': self.packets_lost,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'elapsed_seconds': elapsed
        }

        if elapsed > 0:
            metrics['tx_mbps'] = (self.bytes_sent * 8) / (elapsed * 1_000_000)
            metrics['rx_mbps'] = (self.bytes_received * 8) / (elapsed * 1_000_000)

        if self.packets_sent > 0:
            metrics['loss_rate'] = self.packets_lost / self.packets_sent

        return metrics

    # Delegate all other methods to the original trace
    def __getattr__(self, name):
        return getattr(self._trace, name)


class GameNetMetricsLogger(QuicLogger):
    """
    GameNetMetricsLogger - wrapper class around QuicLogger to log information about the connection.

    Used for collecting metrics and info about the channel.
    """
    def __init__(self):
        super().__init__()
        self.metrics_wrapper = None

    def start_trace(self, is_client: bool, odcid: bytes):
        original_trace = super().start_trace(is_client=is_client, odcid=odcid)

        # wrap created trace with custom metrics tracker
        self.metrics_wrapper = GameNetMetricsWrapper(original_trace)
        self._traces.remove(original_trace)
        self._traces.append(self.metrics_wrapper)

        return self.metrics_wrapper

    def get_metrics(self):
        if self.metrics_wrapper:
            return self.metrics_wrapper.get_metrics()
        return {}


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
            await self.gamenet.close()
        else:
            self._conn.close()
            self._conn.transmit()

    def stats(self):
        stats = self._conn._quic._loss
        metrics = self.gamenet._logger.get_metrics()
        return {
            'rtt_latest': stats._rtt_latest,
            'rtt_avg': stats._rtt_smoothed,
            'rtt_min': stats._rtt_min,
            'packets_sent': metrics['packets_sent'],
            'packets_received': metrics['packets_received'],
            'packets_lost': metrics['packets_lost'],
            'bytes_sent': metrics['bytes_sent'],
            'bytes_received': metrics['bytes_received'],
            'elapsed_time': metrics['elapsed_seconds'],
            'loss_rate': metrics['loss_rate'],
            'tx_mbps': metrics['tx_mbps'],
            'rx_mbps': metrics['rx_mbps']
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
        self._logger = GameNetMetricsLogger()

        self._config = QuicConfiguration(
            is_client = self._is_client,
            alpn_protocols = [GameNet.ALPN],
            max_datagram_frame_size = self.datagram_frame_size,
            quic_logger = self._logger
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

    async def listen(self, port = None, host = '0.0.0.0'):
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

    async def close(self):
        if self._is_client and self._context is not None:
            await self._context.__aexit__(None, None, None)  # <-- pass 3 args
            self._context = None
            
            self._instance = None


def Server(certs, on_connect):
    return GameNet(is_client = False, cert_file = certs[0], key_file = certs[1], on_connect = on_connect)

def Client(certs, on_connect):
    return GameNet(is_client = True, cert_file = certs[0], key_file = certs[1], on_connect = on_connect, verify_cert = False)
