import hashlib
import io
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging/release"))
import legal


class LegalPackagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        names = (
            "onnxruntime/LICENSE", "onnxruntime/ThirdPartyNotices.txt",
            "models/CC-BY-4.0.txt", "models/Apache-2.0.txt",
            "fluidaudio/ThirdPartyLicenses/fastcluster-LICENSE.md",
            "fluidaudio/ThirdPartyLicenses/vbx-LICENSE.md",
        )
        rows = []
        for name in names:
            file = self.root / "licenses" / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(name)
            rows.append({"file": name, "sha256": legal.digest(file)})
        (self.root / "licenses/manifest.json").write_text(json.dumps({"files": rows}))
        for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/third-party-source-guide.md"):
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("시험용 이용 조건")
        (self.root / "packaging/release").mkdir(parents=True)

    def test_embedded_notice_names_are_collected(self):
        for name in ("ThirdPartyNotices.txt", "fastcluster-LICENSE.md", "COPYING", "Copyright.txt"):
            self.assertTrue(legal.is_notice(name), name)
        self.assertFalse(legal.is_notice("model.bin"))

    def test_missing_or_modified_notice_stops_packaging(self):
        folder = Path(self.temp.name) / "package"
        legal.copy_static(folder, self.root)
        legal.check_folder(folder, self.root)
        notice = folder / "licenses/onnxruntime/LICENSE"
        notice.write_text("변조")
        with self.assertRaisesRegex(ValueError, "고지"):
            legal.check_folder(folder, self.root)
        notice.unlink()
        with self.assertRaisesRegex(ValueError, "고지"):
            legal.check_folder(folder, self.root)

    def test_paths_cannot_escape_source_cache(self):
        for name in ("../secret", "/tmp/secret", "folder\\secret", "C:/secret",
                     "C:secret", "//server/share/secret", "file:stream"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                legal.checked_path(self.root, name)

    def test_bad_source_download_is_not_published(self):
        sha = hashlib.sha256(b"expected").hexdigest()
        manifest = self.root / "packaging/release/legal_sources.json"
        manifest.write_text(json.dumps({"sources": [
            {"file": "source.tar.gz", "url": "https://example.invalid/source", "sha256": sha}
        ]}))
        cache = self.root / "build/legal-sources"
        with patch.object(legal, "urlopen", return_value=io.BytesIO(b"wrong")) as fetch:
            with self.assertRaisesRegex(ValueError, "체크섬"):
                legal.fetch_sources(self.root)
        fetch.assert_called_once()
        self.assertFalse((cache / "source.tar.gz").exists())
        self.assertFalse((cache / "source.tar.gz.part").exists())

    def test_network_failure_restarts_partial_source_and_verifies_checksum(self):
        manifest = self.root / "packaging/release/legal_sources.json"
        manifest.write_text(json.dumps({"sources": [
            {"file": "source.tar.gz", "url": "https://example.invalid/source",
             "sha256": hashlib.sha256(b"complete").hexdigest()}
        ]}))
        class Interrupted(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise ConnectionResetError("연결 중단")
                return super().read(size)
        attempts = [URLError(ssl.SSLEOFError("연결 종료")),
                    Interrupted(b"partial"), io.BytesIO(b"complete")]
        with patch.object(legal, "urlopen", side_effect=attempts) as fetch, \
                patch.object(legal.time, "sleep") as sleep:
            legal.fetch_sources(self.root)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
        file = self.root / "build/legal-sources/source.tar.gz"
        self.assertEqual(file.read_bytes(), b"complete")
        self.assertFalse(file.with_name(file.name + ".part").exists())
        self.assertNotIn("context", fetch.call_args.kwargs)

    def test_download_retries_only_temporary_failures(self):
        part = self.root / "download.part"
        errors = [
            (HTTPError("https://example.invalid", 503, "일시 오류", {}, None), 3),
            (URLError(TimeoutError("시간 초과")), 3),
            (HTTPError("https://example.invalid", 404, "없음", {}, None), 1),
            (ssl.SSLCertVerificationError("인증서 오류"), 1),
            (URLError(ssl.SSLCertVerificationError("인증서 오류")), 1),
            (PermissionError("읽기 전용 폴더"), 1),
        ]
        for error, expected in errors:
            with self.subTest(error=repr(error)):
                part.write_bytes(b"previous partial")
                with patch.object(legal, "urlopen", side_effect=error) as fetch, \
                        patch.object(legal.time, "sleep") as sleep, \
                        self.assertRaises(type(error)):
                    legal.download("https://example.invalid", part)
                self.assertEqual(fetch.call_count, expected)
                self.assertEqual(sleep.call_count, expected - 1)
                self.assertFalse(part.exists())

    def test_python_notice_uses_retry_and_preserves_existing_on_invalid_response(self):
        folder = self.root / "package"
        data = b"PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n"
        attempts = [HTTPError("https://example.invalid", 429, "잠시 대기", {}, None),
                    io.BytesIO(data)]
        with patch.object(legal, "distributions", return_value=[]), \
                patch.object(legal, "urlopen", side_effect=attempts) as fetch, \
                patch.object(legal.time, "sleep"):
            legal.collect(folder, root=self.root)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual((folder / "python-runtime/LICENSE").read_bytes(), data)
        with patch.object(legal, "distributions", return_value=[]), \
                patch.object(legal, "urlopen", return_value=io.BytesIO(b"wrong")) as fetch, \
                self.assertRaisesRegex(ValueError, "런타임 고지"):
            legal.collect(folder, root=self.root)
        fetch.assert_called_once()
        self.assertEqual((folder / "python-runtime/LICENSE").read_bytes(), data)
        self.assertFalse((folder / "python-runtime/LICENSE.part").exists())

    def test_valid_cache_is_reused_and_corruption_is_rejected(self):
        cache = self.root / "build/legal-sources"
        cache.mkdir(parents=True)
        source = cache / "source.tar.gz"
        source.write_bytes(b"source")
        (self.root / "packaging/release/legal_sources.json").write_text(json.dumps({
            "sources": [{"file": source.name, "url": "https://example.invalid/source",
                         "sha256": legal.digest(source)}]
        }))
        with patch.object(legal, "urlopen", side_effect=AssertionError("다시 받으면 안 됨")):
            legal.fetch_sources(self.root)
            source.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "체크섬"):
                legal.fetch_sources(self.root)

    def test_source_archives_are_deterministic(self):
        source = self.root / "LICENSE"
        a, b = Path(self.temp.name) / "a.zip", Path(self.temp.name) / "b.zip"
        legal.zip_files(a, [(source, "LICENSE")], compression=zipfile.ZIP_STORED)
        class WindowsZipInfo(zipfile.ZipInfo):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.create_system = 0
        with patch.object(legal.zipfile, "ZipInfo", WindowsZipInfo):
            legal.zip_files(b, [(source, "LICENSE")], compression=zipfile.ZIP_STORED)
        self.assertEqual(legal.digest(a), legal.digest(b))
        with zipfile.ZipFile(a) as archive:
            self.assertEqual(archive.read("LICENSE"), source.read_bytes())
            self.assertEqual(archive.getinfo("LICENSE").create_system, 3)
            self.assertEqual(archive.getinfo("LICENSE").compress_type, zipfile.ZIP_STORED)


if __name__ == "__main__":
    unittest.main()
