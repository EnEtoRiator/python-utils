import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import logging

from .downloader import download_file, DownloadError
from .extractor import extract_archive
# from .extractor import extract_archive

logger = logging.getLogger(__name__)

class InstallationError(Exception):
    pass

class BaseInstaller:
    """Базовый класс для установки компонента"""
    
    def __init__(self, name: str, version: str, install_dir: Path, temp_dir: Path):
        self.name = name
        self.version = version
        self.install_dir = install_dir
        self.temp_dir = temp_dir
        self.downloaded_file: Optional[Path] = None
    
    def download(self, url: str, expected_hash: Optional[str] = None, progress_callback: Optional[Callable] = None) -> Path:
        """Скачивает файл установщик во временную папку"""
        dest = self.temp_dir / f'{self.name}-{self.version}-installer' / Path(url).name
        try:
            download_file(url, dest, expected_hash=expected_hash, progress_callback=progress_callback)
        except DownloadError as e:
            raise InstallationError(f"Failed to download {self.name}: {e}")
        self.downloaded_file = dest
        return dest
    
    def install(self, progress_callback: Optional[Callable] = None) -> None:
        """Запускает процесс установки. Должен быть переопределен"""
        raise NotImplementedError
    
    def clean(self) -> None:
        """Удаляет временные файлы"""
        if self.downloaded_file and self.downloaded_file.exists():
            self.downloaded_file.unlink()

class ExecutableInstaller(BaseInstaller):
    """Установщик для .exe/.msi файлов с тихими параметрами"""
    
    def __init__(self, name: str, version: str, install_dir: Path, temp_dir: Path,
                 executable_args: Optional[list] = None, 
                 silent_switches: Optional[list] = None):
        super().__init__(name, version, install_dir, temp_dir)
        self.executable_args = executable_args or []
        self.silent_switches = silent_switches or ['/S', '/quiet']
    
    def install(self, progress_callback: Optional[Callable] = None) -> None:
        if not self.downloaded_file:
            raise InstallationError("No installer downloaded")

        cmd = [str(self.downloaded_file)] + self.silent_switches + self.executable_args
        
        logger.info(f"Running installer: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"installer output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            raise InstallationError(f"Installer failed with code: {e.returncode}: {e.stderr}")

class JarInstaller(BaseInstaller):
    """Установщик для .jar файлов (Fabric, Forge, OptiFine)."""
    
    def __init__(self, name: str, version: str, install_dir: Path, temp_dir: Path,
                 java_path: Path, jar_args: Optional[list] = None):
        super().__init__(name, version, install_dir, temp_dir)
        self.java_path = java_path
        self.jar_args = jar_args or []
    
    def install(self, progress_callback: Optional[Callable] = None) -> None:
        if not self.downloaded_file:
            raise InstallationError("No installer downloaded")
        
        cmd = [str(self.java_path), '-jar', str(self.downloaded_file)] + self.jar_args
        
        logger.info(f'Running jar installer: {' '.join(cmd)}')
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"Jar installer output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            raise InstallationError(f"Jar installer failed: {e.stderr}")

class ArchiveInstaller(BaseInstaller):
    """Установщик для архивов (просто распаковать)."""
    def install(self, progress_callback: Optional[Callable] = None) -> None:
        if not self.downloaded_file:
            raise InstallationError("No archive downloaded")
        
        logger.info(f"Extracting {self.downloaded_file} to {self.install_dir}")
        try:
            extract_archive(self.downloaded_file, self.install_dir)
        except Exception as e:
            raise InstallationError(f"Extraction failed: {e}")
