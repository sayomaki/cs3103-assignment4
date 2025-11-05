import ssl
import struct
import time
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

# ch(1), seq(2), ts_ms(4)
HDR_FMT = ">BHI"  

class GameNetQUICClient:
    """
    ch=1 (reliable) -> QUIC stream
    ch=0 (unreliable) -> QUIC DATAGRAM (fallback to stream if not negotiated)
    """
    def __init__(self, alpn="custom-quic", verify=False):
        self.alpn = alpn
        self.verify = verify
        self._ctx = None          # connect() context manager
        self.conn = None          # QuicConnectionProtocol
        self.rel_seq = 0
        self.unr_seq = 0
        self.rel_stream = None            # long-lived reliable stream
        self.unr_fallback_stream = None   # long-lived fallback stream

    async def connect(self, target: str):
        host, port = target.split(":")
        cfg = QuicConfiguration(is_client=True, alpn_protocols=[self.alpn], max_datagram_frame_size=65535)
        
        if not self.verify:
            cfg.verify_mode = ssl.CERT_NONE

        # connect() returns an async context manager
        self._ctx = connect(host, int(port), configuration=cfg)
        self.conn = await self._ctx.__aenter__()
        await self.conn.wait_connected()
        
        # Print to confirm negotiation
        tp = getattr(self.conn._quic, "_peer_transport_parameters", None)
        print("Peer max_dgram:", getattr(tp, "max_datagram_frame_size", 0))
        print("Local max_dgram:", getattr(self.conn._quic, "_local_max_datagram_frame_size", 0))

        # pre-create one bidirectional stream for reliable sends
        self.rel_stream = self.conn._quic.get_next_available_stream_id(is_unidirectional=False)
        self.conn._quic.send_stream_data(self.rel_stream, b"", end_stream=False)

        self.unr_fallback_stream = self.conn._quic.get_next_available_stream_id(is_unidirectional=False)
        self.conn._quic.send_stream_data(self.unr_fallback_stream, b"", end_stream=False)

    async def close(self):
        if self._ctx is not None:
            await self._ctx.__aexit__(None, None, None)
            self._ctx = None
            self.conn = None
            
    def _peer_supports_datagram(self) -> bool:
        tp = getattr(self.conn._quic, "_peer_transport_parameters", None)
        return bool(getattr(tp, "max_datagram_frame_size", 0))

    async def send_packet(self, flag: int, payload: bytes):
        now_ms = int(time.time() * 1000) & 0xFFFFFFFF
        if flag == 1:
            # reliable ch1
            self.rel_seq = (self.rel_seq + 1) & 0xFFFF
            header = struct.pack(HDR_FMT, 1, self.rel_seq, now_ms)
            self.conn._quic.send_stream_data(self.rel_stream, header + payload, end_stream=False)
        else:
            # unreliable ch0
            self.unr_seq = (self.unr_seq + 1) & 0xFFFF
            header = struct.pack(HDR_FMT, 0, self.unr_seq, now_ms)
            framed = header + payload
            if self._peer_supports_datagram():
                self.conn._quic.send_datagram_frame(framed)
            else:
                self.conn._quic.send_stream_data(self.unr_fallback_stream, framed, end_stream=False)

        self.conn.transmit()
