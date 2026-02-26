import requests
import hashlib
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

class DownloadError(Exception):
    pass

class HashMismatchError(DownloadError):
    pass

def download_file(
    url: str,
    dest: Path,
    expected_hash: Optional[str] = None,
    hash_algo: str = 'sha1',
    progress_callback: Optional[Callable[[int, int], None]] = None,
    chunk_size: int = 8192,
    timeout: float = 30.0,
    max_retries: int = 3,
    resume: bool = True,
) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            mode = 'wb'
            resume_pos = 0
            if resume and dest.exists() and attempt == 0:
                try:
                    head_resp = requests.head(url, timeout=timeout)
                    head_resp.raise_for_status()
                    remote_size = int(head_resp.headers.get('content-length', 0))
                    local_size = dest.stat().st_size
                    if local_size < remote_size:
                        mode = 'ab'
                        resume_pos = local_size
                except Exception:
                    pass

            headers = {'Range': f'bytes={resume_pos}-'} if resume_pos > 0 else {}
            response = requests.get(url, stream=True, timeout=timeout, headers=headers)
            response.raise_for_status()

            if resume_pos > 0 and response.status_code == 200:
                resume_pos = 0
                mode = 'wb'

            total_size = int(response.headers.get('content-length', 0)) + resume_pos
            downloaded = resume_pos

            with open(dest, mode) as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            progress_callback(downloaded, total_size)

            if expected_hash:
                file_hash = hashlib.new(hash_algo)
                with open(dest, 'rb') as f:
                    for chunk in iter(lambda: f.read(chunk_size), b''):
                        file_hash.update(chunk)
                if file_hash.hexdigest() != expected_hash:
                    dest.unlink()
                    raise HashMismatchError(f"Hash mismatch for {url}")

            return True

        except (requests.RequestException, OSError, ValueError) as e:
            logger.warning(f"Download attempt {attempt+1} failed for {url}: {e}")
            if dest.exists():
                dest.unlink()
            if attempt == max_retries - 1:
                raise DownloadError(f"Failed to download {url} after {max_retries} attempts")
        # HashMismatchError не ловится, уходит выше
    return False
