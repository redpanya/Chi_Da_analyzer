import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
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
        with patch.object(legal, "urlopen", return_value=io.BytesIO(b"wrong")):
            with self.assertRaisesRegex(ValueError, "체크섬"):
                legal.fetch_sources(self.root)
        self.assertFalse((cache / "source.tar.gz").exists())
        self.assertFalse((cache / "source.tar.gz.part").exists())

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
