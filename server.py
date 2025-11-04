import asyncio, csv, os, base64
from datetime import datetime
from struct import unpack_from
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, DatagramFrameReceived, HandshakeCompleted, ConnectionTerminated
from aioquic.quic.logger import QuicFileLogger

STREAM_CSV = "reliable_stream.csv"
DGRAM_CSV  = "unreliable_dgram.csv"

def _stamp(): return datetime.now().isoformat(timespec="milliseconds")
def _peer(proto): 
    info = proto._transport.get_extra_info("peername")
    return str(info) if info else "peer=?"
def _ensure_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp","peer","channel","seqno","length","payload_b64","preview_utf8"])
def _append(path, row):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
def _b64(b: bytes) -> str: return base64.b64encode(b).decode("ascii")
def _preview(b: bytes, n=64) -> str: return b.decode("utf-8", "replace")[:n]

class DualChannelProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            ch = "DGRAM-OK" if self._quic.datagram_supported else "DGRAM-NOT-SUPPORTED"
            _append(DGRAM_CSV, [_stamp(), _peer(self), ch, "", "", "", ""])
            return

        # Reliable: QUIC streams
        if isinstance(event, StreamDataReceived):
            data = event.data
            if len(data) < 5:
                _append(STREAM_CSV, [_stamp(), _peer(self), "stream", "", len(data), _b64(data), _preview(data)])
                return
            flag = data[0]          # expect 1
            seqno = unpack_from(">I", data, 1)[0]
            payload = data[5:]
            _append(
                STREAM_CSV,
                [_stamp(), _peer(self),
                 "stream" if flag == 1 else "stream(flag!=1)",
                 seqno, len(payload), _b64(payload), _preview(payload)]
            )
            if flag == 1:
                self._quic.send_stream_data(event.stream_id, data, end_stream=False)
            else:
                self._quic.send_stream_data(event.stream_id, b"\x01NOTE: use DATAGRAM for unreliable.\n", end_stream=False)

        # Unreliable: QUIC DATAGRAMs
        elif isinstance(event, DatagramFrameReceived):
            data = event.data
            if len(data) < 5:
                _append(DGRAM_CSV, [_stamp(), _peer(self), "dgram", "", max(0, len(data)-1), _b64(data[1:]), _preview(data[1:])])
                return
            flag = data[0]          # expect 0
            seqno = unpack_from(">I", data, 1)[0]
            payload = data[5:]
            _append(
                DGRAM_CSV,
                [_stamp(), _peer(self),
                 "dgram" if flag == 0 else "dgram(flag!=0)",
                 seqno, len(payload), _b64(payload), _preview(payload)]
            )
            if flag == 0 and self._quic.datagram_supported:
                self._quic.send_datagram_frame(data)

        elif isinstance(event, ConnectionTerminated):
            _append(STREAM_CSV, [_stamp(), _peer(self), "closed", "", "", "", ""])
            _append(DGRAM_CSV,  [_stamp(), _peer(self), "closed", "", "", "", ""])

async def main():
    _ensure_csv(STREAM_CSV); _ensure_csv(DGRAM_CSV)
    os.makedirs("qlogs", exist_ok=True)
    cfg = QuicConfiguration(is_client=False, alpn_protocols=["custom-quic"], quic_logger=QuicFileLogger("qlogs"))
    cfg.max_datagram_frame_size = 65536
    cfg.load_cert_chain("cert.pem", "key.pem")  # real deployment

    await serve(host="0.0.0.0", port=8001, configuration=cfg, create_protocol=DualChannelProtocol)
    await asyncio.Future()

if __name__ == "__main__":
    print("Starting QUIC server on 0.0.0.0:8001")
    asyncio.run(main())
