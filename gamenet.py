import ssl
import struct
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

class GameNetQUICClient:
    """
    flag=1 -> reliable (QUIC stream)
    flag=0 -> unreliable (QUIC DATAGRAM)
    """
    def __init__(self, alpn="custom-quic", verify=False):
        self.alpn = alpn
        self.verify = verify
        self._ctx = None          # connect() context manager
        self.conn = None          # QuicConnectionProtocol
        self.stream_id = None     # reliable stream id

    async def connect(self, target: str):
        host, port = target.split(":")
        cfg = QuicConfiguration(is_client=True, alpn_protocols=[self.alpn])
        if not self.verify:
            cfg.verify_mode = ssl.CERT_NONE

        # connect() returns an async context manager
        self._ctx = connect(host, int(port), configuration=cfg)
        self.conn = await self._ctx.__aenter__()

        # pre-create one bidirectional stream for reliable sends
        self.stream_id = self.conn._quic.get_next_available_stream_id(is_unidirectional=False)
        self.conn._quic.send_stream_data(self.stream_id, b"", end_stream=False)
        await self.conn.wait_connected()

    async def close(self):
        if self._ctx is not None:
            await self._ctx.__aexit__(None, None, None)
            self._ctx = None
            self.conn = None

    async def send_packet(self, flag: int, payload: bytes):
        if flag == 1:
            # frame: [flag][seq:4B][payload]
            seq = getattr(self, "_seq_rel", 0)
            self._seq_rel = (seq + 1) & 0xFFFFFFFF
            framed = bytes([1]) + struct.pack(">I", seq) + payload

            # use a FRESH bidirectional stream each time to avoid FIN issues
            stream_id = self.conn._quic.get_next_available_stream_id(is_unidirectional=False)
            self.conn._quic.send_stream_data(stream_id, framed, end_stream=False)
        else:
            seq = getattr(self, "_seq_unr", 0)
            self._seq_unr = (seq + 1) & 0xFFFFFFFF
            framed = bytes([0]) + struct.pack(">I", seq) + payload
            self.conn._quic.send_datagram_frame(framed)

        self.conn.transmit()
