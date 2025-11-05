import asyncio, csv, os, base64
import struct
import time
from datetime import datetime
from struct import unpack_from
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, DatagramFrameReceived, HandshakeCompleted, ConnectionTerminated
from aioquic.quic.logger import QuicFileLogger

STREAM_CSV = "reliable_stream.csv"
DGRAM_CSV  = "unreliable_dgram.csv"
HDR_FMT = ">BHI"  # ch(1), seq(2), ts_ms(4)
HDR_SIZE = struct.calcsize(HDR_FMT)

def _stamp(): return datetime.now().isoformat(timespec="milliseconds")
def _peer(proto):
    info = proto._transport.get_extra_info("peername")
    return str(info) if info else "peer=?"

def _ensure_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "timestamp","peer","channel","seqno","lat_ms","jitter_ms",
                "payload_len","payload_b64","preview_utf8"
            ])

def _append(path, row):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def _b64(b: bytes) -> str: return base64.b64encode(b).decode("ascii")

def _preview(b: bytes, n=64) -> str: return b.decode("utf-8", "replace")[:n]

class _JitterRFC3550:
    def __init__(self): self.prev=None; self.j=0.0
    def update(self, send_ts_ms:int, recv_ts_ms:int)->float:
        tr = recv_ts_ms - send_ts_ms
        if self.prev is None: self.prev=tr; return 0.0
        d = abs(tr - self.prev); self.prev = tr; self.j += (d - self.j)/16.0; return self.j

class DualChannelProtocol(QuicConnectionProtocol):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        # reliable reorder buffer
        self.expected = 0
        self.buf = {}
        self.gap_started_ms = None
        self.gap_deadline_ms = 200
        # jitter estimators
        self.j_rel = _JitterRFC3550()
        self.j_unr = _JitterRFC3550()

    def _deliver_in_order(self, recv_ts_ms:int):
        # deliver all contiguous from expected
        while self.expected in self.buf:
            send_ts, payload = self.buf.pop(self.expected)
            lat = recv_ts_ms - send_ts
            jit = round(self.j_rel.update(send_ts, recv_ts_ms), 3)
            _append(STREAM_CSV, [_stamp(), _peer(self), "stream", self.expected, lat, jit,
                                 len(payload), _b64(payload), _preview(payload)])
            self.expected = (self.expected + 1) & 0xFFFF
        # if still a gap
        if self.buf and self.gap_started_ms is None:
            self.gap_started_ms = recv_ts_ms

        # if timer expired, skip one missing seq
        if self.gap_started_ms is not None and (recv_ts_ms - self.gap_started_ms) >= self.gap_deadline_ms:
            # skip missing seq to unblock delivery
            self.expected = (self.expected + 1) & 0xFFFF
            self.gap_started_ms = None

            self._deliver_in_order(recv_ts_ms)

    def quic_event_received(self, event):

        if isinstance(event, HandshakeCompleted):
            print("Client max_dgram:", getattr(self._quic, "_remote_max_datagram_frame_size", 0))
            print("Server local max_dgram:", getattr(self._quic._configuration, "max_datagram_frame_size", 0))

            max_dgram = getattr(self._quic, "_remote_max_datagram_frame_size", 0) or 0
            ch = "DGRAM-OK" if max_dgram else "DGRAM-NOT-SUPPORTED"
            _append(DGRAM_CSV, [_stamp(), _peer(self), ch, "", "", "", "", "", ""])
            return

        if isinstance(event, StreamDataReceived):
            data = event.data
            recv_ts = int(time.time()*1000)
            if len(data) < HDR_SIZE:
                _append(STREAM_CSV, [_stamp(), _peer(self), "stream(raw)", "", "", "", len(data), _b64(data), _preview(data)])
                return
            ch, seq, ts_ms = struct.unpack(HDR_FMT, data[:HDR_SIZE])
            payload = data[HDR_SIZE:]
            # only treat ch==1 as reliable stream traffic
            if ch == 1:
                self.buf[seq] = (ts_ms, payload)
                self._deliver_in_order(recv_ts)
            else:
                print(ch)
                # fallback
                lat = recv_ts - ts_ms
                jit = round(self.j_unr.update(ts_ms, recv_ts), 3)
                _append(DGRAM_CSV, [_stamp(), _peer(self), "dgram(fallback-stream)", seq, lat, jit,
                                    len(payload), _b64(payload), _preview(payload)])

        elif isinstance(event, DatagramFrameReceived):
            data = event.data
            recv_ts = int(time.time()*1000)
            if len(data) < HDR_SIZE:
                _append(DGRAM_CSV, [_stamp(), _peer(self), "dgram(raw)", "", "", "", len(data), _b64(data), _preview(data)])
                return
            ch, seq, ts_ms = struct.unpack(HDR_FMT, data[:HDR_SIZE])
            payload = data[HDR_SIZE:]
            # ch should be 0 here
            lat = recv_ts - ts_ms
            jit = round(self.j_unr.update(ts_ms, recv_ts), 3)
            _append(DGRAM_CSV, [_stamp(), _peer(self), "dgram", seq, lat, jit, len(payload), _b64(payload), _preview(payload)])

        elif isinstance(event, ConnectionTerminated):
            _append(STREAM_CSV, [_stamp(), _peer(self), "closed", "", "", "", "", ""])
            _append(DGRAM_CSV,  [_stamp(), _peer(self), "closed", "", "", "", "", ""])

async def main():
    _ensure_csv(STREAM_CSV); _ensure_csv(DGRAM_CSV)
    os.makedirs("qlogs", exist_ok=True)
    cfg = QuicConfiguration(is_client=False, alpn_protocols=["custom-quic"], max_datagram_frame_size=65535, quic_logger=QuicFileLogger("qlogs"))

    cfg.load_cert_chain("cert.pem", "key.pem")  # real deployment

    await serve(host="0.0.0.0", port=8001, configuration=cfg, create_protocol=DualChannelProtocol)
    await asyncio.Future()

if __name__ == "__main__":
    print("Starting QUIC server on 0.0.0.0:8001")
    asyncio.run(main())
