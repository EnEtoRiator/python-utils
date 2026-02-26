import zipfile
import tarfile
import subprocess
from pathlib import Path
from typing import Optional, Callable, Union
import logging
import shutil

logger = logging.getLogger(__name__)

class ExtractionError(Exception):
    pass

def extract_archive(
    archive_path: Path,
    extract_to: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    use_7z_if_available: bool = False,
    seven_zip_path: Optional[Path] = None
) -> None:
    """
        Распаковывает архив в указанную папку.
        
        Поддерживает .zip .tar .tar.gz .tgz .tar.bz2
        
        Если use_7z_if_available=True и 7z найден, может распаковывать .7z, .rar и др.
    """
    
    extract_to.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    name = archive_path.name
    
    # ZIP
    if suffix == '.zip':
        _extract_zip(archive_path, extract_to, progress_callback)
    # TAR and compressed TAR
    elif suffix in ('.tar', '.gz', '.bz2', '.xz') or name.endswith('.tgz') or name.endswith('.tbz2'):
        _extract_tar(archive_path, extract_to, progress_callback)
    else:
        raise ExtractionError(f'Unsupported archive format: {suffix}. Try enabling 7z support.')

def _extract_zip(
    zip_path: Path,
    extract_to: Path,
    progress_callback: Optional[Callable[[int, int], None]]
) -> None:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            members = zf.infolist()
            total = len(members)
            for i, member in enumerate(members, 1):
                zf.extract(member, extract_to)
                if progress_callback:
                    progress_callback(i, total)
    except zipfile.BadZipFile as e:
        raise ExtractionError(f'Invalid ZIP file: {e}')

def _extract_tar(
    tar_path: Path,
    extract_to: Path,
    progress_callback: Optional[Callable[[int, int], None]]
) -> None:
    try:
        with tarfile.open(tar_path, 'r:*') as tf:
            members = tf.getmembers()
            total = len(members)
            for i, member in enumerate(members, 1):
                tf.extract(member, extract_to)
                if progress_callback:
                    progress_callback(i, total)
    except tarfile.TarError as e:
        raise ExtractionError(f'Invalid TAR file: {e}')

def _extract_with_7z(
    archive_path: Path,
    extract_to: Path,
    seven_zip_path: Optional[Path],
    progress_callback: Optional[Callable[[int, int], None]]
) -> None:
    if seven_zip_path is None:
        seven_zip_path = shutil.which('7z') or shutil.which('7za') # pyright: ignore[reportAssignmentType]
    if seven_zip_path is None:
        raise ExtractionError("7-Zip not found. Please install 7-Zip or place it in the launcher folder.")
    
    cmd = [
        str(seven_zip_path), 'x',
        str(archive_path),
        f'-o{extract_to}',
        '-y'
    ]
    logger.info(f'Running 7z: {' '.join(cmd)}')
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.debug(f'7z output: {result.stdout}')
        if progress_callback:
            progress_callback(1, 1)
    except subprocess.CalledProcessError as e:
        raise ExtractionError(f'7-Zip failed: {e.stderr}')
