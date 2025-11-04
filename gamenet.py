import ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

class GameNetQUICClient:
    """Routes by flag:
       flag=1 -> RELIABLE (predefined bidirectional QUIC stream)
       flag=0 -> UNRELIABLE (QUIC DATAGRAM)
    """
    def __init__(self, alpn="hq-29", verify=False):
        self.alpn = alpn
        self.verify = verify
        self.conn_ctx = None
        self.stream_id = None

    async def connect(self, target:str):
        host, port = target.split(":")
        cfg = QuicConfiguration(is_client=True, alpn_protocols=[self.alpn])
        if not self.verify:
            cfg.verify_mode = ssl.CERT_NONE
        self.conn_ctx = await connect(host, int(port), configuration=cfg)
        # Predefine reliable stream
        self.stream_id = self.conn_ctx._quic.get_next_available_stream_id(is_unidirectional=False)
        self.conn_ctx._quic.send_stream_data(self.stream_id, b"", end_stream=False)
        await self.conn_ctx.wait_connected()

    async def close(self):
        if self.conn_ctx:
            await self.conn_ctx.close()

    async def send_packet(self, flag:int, payload:bytes):
        if flag == 1:
            self.conn_ctx._quic.send_stream_data(self.stream_id, payload + b"\n", end_stream=False)
        else:
            self.conn_ctx._quic.send_datagram_frame(payload)
        self.conn_ctx.transmit()
