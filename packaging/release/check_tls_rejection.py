"""임시 자체서명 HTTPS를 원격 미디어 도구가 거부하는지 검사한다."""
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
import ssl
import subprocess
import sys
import threading
from urllib.request import urlopen


def certificate(folder, dependencies):
    # 검사 전용 의존성이다. 앱의 site-packages·OS 신뢰 저장소는 변경하지 않는다.
    previous = list(sys.path)
    sys.path.insert(0, str(dependencies))
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([
                    x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(key, hashes.SHA256()))
        cert_path, key_path = folder/'temporary-cert.pem', folder/'temporary-key.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return cert_path, key_path
    finally:
        sys.path[:] = previous


def check(ffmpeg, folder, fixture_dir, dependencies):
    cert_path, key_path = certificate(folder, dependencies)
    requests = []

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(fixture_dir)))
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'https://localhost:{server.server_port}'
    try:
        # 테스트 서버가 정상임을 이 Python 연결에서만 명시적으로 신뢰하여 확인한다.
        trusted_test_context = ssl.create_default_context(cafile=str(cert_path))
        with urlopen(base+'/https-media.mp4', context=trusted_test_context, timeout=10) as response:
            if response.read() != (fixture_dir/'https-media.mp4').read_bytes():
                raise ValueError('임시 HTTPS 검사 서버 응답이 다릅니다')
        requests.clear()
        master = folder/'untrusted-playlist.m3u8'
        master.write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\n'+base+'/https-media.m3u8\n', encoding='utf-8')
        segment = folder/'untrusted-segment.m3u8'
        segment.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:4.0,\n'+base+'/https-segment.ts\n#EXT-X-ENDLIST\n', encoding='utf-8')
        encrypted = folder/'untrusted-key.m3u8'
        encrypted.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:5\n'
            '#EXT-X-KEY:METHOD=AES-128,URI="'+base+'/key.bin",IV=0x00000000000000000000000000000000\n'
            '#EXTINF:4.0,\n'+(fixture_dir/'https-segment.ts').resolve().as_uri()+'\n#EXT-X-ENDLIST\n', encoding='utf-8')
        results = {}
        for kind, source in [('direct_https', base+'/https-media.mp4'),
                             ('hls_playlist', str(master)), ('hls_segment', str(segment)),
                             ('hls_key', str(encrypted))]:
            # -tls_verify를 생략하여 빌드의 안전 기본값 및 하위 연결을 직접 검증한다.
            completed = subprocess.run([str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error',
                '-protocol_whitelist', 'file,https,tls,tcp,crypto', '-rw_timeout', '3000000',
                '-i', source, '-t', '0.1', '-f', 'null', '-'], capture_output=True, timeout=30)
            log = completed.stderr.decode('utf-8', errors='replace').lower()
            recognized = any(word in log for word in ('certificate', 'security context failed', 'tls/ssl session'))
            if not completed.returncode or not recognized or requests:
                raise ValueError(f'신뢰하지 않는 인증서 거부 검사 실패 ({kind}): '+log[-1600:])
            results[kind] = True
        return results
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
