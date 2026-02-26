import pytest
import requests_mock
import hashlib
from pathlib import Path
import tempfile
import requests
from downloader import download_file, DownloadError, HashMismatchError

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def sample_file_content():
    return b"Hello, world! This is a test file content."

@pytest.fixture
def sample_file_sha1(sample_file_content):
    return hashlib.sha1(sample_file_content).hexdigest()

def test_download_basic(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    with requests_mock.Mocker() as m:
        m.get(url, content=sample_file_content)
        result = download_file(url, dest)
        assert result is True
        assert dest.exists()
        assert dest.read_bytes() == sample_file_content

def test_download_with_hash_success(tmp_dir, sample_file_content, sample_file_sha1):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    with requests_mock.Mocker() as m:
        m.get(url, content=sample_file_content)
        result = download_file(url, dest, expected_hash=sample_file_sha1, hash_algo='sha1')
        assert result is True

def test_download_with_hash_failure(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    wrong_hash = "wronghash"
    with requests_mock.Mocker() as m:
        m.get(url, content=sample_file_content)
        with pytest.raises(HashMismatchError, match=r"Hash mismatch for .*"):
            download_file(url, dest, expected_hash=wrong_hash, hash_algo='sha1')
        assert not dest.exists()

def test_progress_callback(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    calls = []
    def progress(downloaded, total):
        calls.append((downloaded, total))
    with requests_mock.Mocker() as m:
        # Добавлен заголовок content-length
        m.get(url, content=sample_file_content, headers={'content-length': str(len(sample_file_content))})
        download_file(url, dest, progress_callback=progress)
    assert len(calls) > 0
    last_downloaded, last_total = calls[-1]
    assert last_downloaded == len(sample_file_content)
    assert last_total == len(sample_file_content)

def test_download_resume_from_partial(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    partial_content = sample_file_content[:10]
    dest.write_bytes(partial_content)
    with requests_mock.Mocker() as m:
        m.head(url, headers={'content-length': str(len(sample_file_content))})
        m.get(url, content=sample_file_content[10:], status_code=206, headers={
            'content-range': f'bytes 10-{len(sample_file_content)-1}/{len(sample_file_content)}'
        })
        download_file(url, dest, resume=True)
    assert dest.read_bytes() == sample_file_content

def test_download_resume_server_no_range(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    partial_content = sample_file_content[:10]
    dest.write_bytes(partial_content)
    with requests_mock.Mocker() as m:
        m.head(url, headers={'content-length': str(len(sample_file_content))})
        # Сервер игнорирует Range и возвращает полный файл с кодом 200
        m.get(url, content=sample_file_content, status_code=200)
        download_file(url, dest, resume=True)
    # Файл должен быть полностью перезаписан, а не дополнен
    assert dest.read_bytes() == sample_file_content

def test_download_retry_on_failure(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    with requests_mock.Mocker() as m:
        m.get(url, [
            {'status_code': 500},
            {'status_code': 500},
            {'content': sample_file_content}
        ])
        result = download_file(url, dest, max_retries=3)
        assert result is True
        assert dest.read_bytes() == sample_file_content

def test_download_max_retries_exceeded(tmp_dir):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "test.txt"
    with requests_mock.Mocker() as m:
        m.get(url, status_code=500)
        with pytest.raises(DownloadError, match=r"Failed to download .* after 3 attempts"):  # изменено
            download_file(url, dest, max_retries=3)

def test_download_http_error_404(tmp_dir):
    url = "http://example.com/missing.txt"
    dest = tmp_dir / "missing.txt"
    with requests_mock.Mocker() as m:
        m.get(url, status_code=404)
        with pytest.raises(DownloadError):
            download_file(url, dest)

def test_download_creates_directory(tmp_dir, sample_file_content):
    url = "http://example.com/test.txt"
    dest = tmp_dir / "subdir" / "nested" / "test.txt"
    with requests_mock.Mocker() as m:
        m.get(url, content=sample_file_content)
        result = download_file(url, dest)
        assert result is True
        assert dest.exists()

def test_download_with_timeout(tmp_dir):
    url = "http://example.com/slow.txt"
    dest = tmp_dir / "slow.txt"
    with requests_mock.Mocker() as m:
        m.get(url, exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(DownloadError):
            download_file(url, dest, timeout=1, max_retries=1)
