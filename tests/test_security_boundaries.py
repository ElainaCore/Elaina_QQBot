import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.foundation.archives import safe_extract_tar, safe_extractall


class ArchiveSecurityTests(unittest.TestCase):
    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('../outside.txt', 'blocked')
            with zipfile.ZipFile(archive_path) as archive, self.assertRaises(ValueError):
                safe_extractall(archive, str(Path(temp) / 'dest'))

    def test_tar_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / 'bad.tar'
            member = tarfile.TarInfo('../outside.txt')
            member.size = 7
            with tarfile.open(archive_path, 'w') as archive:
                archive.addfile(member, io.BytesIO(b'blocked'))
            with tarfile.open(archive_path) as archive, self.assertRaises(ValueError):
                safe_extract_tar(archive, str(Path(temp) / 'dest'))

    def test_tar_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / 'link.tar'
            member = tarfile.TarInfo('link')
            member.type = tarfile.SYMTYPE
            member.linkname = '../../outside'
            with tarfile.open(archive_path, 'w') as archive:
                archive.addfile(member)
            with tarfile.open(archive_path) as archive, self.assertRaises(ValueError):
                safe_extract_tar(archive, str(Path(temp) / 'dest'))


if __name__ == '__main__':
    unittest.main()
