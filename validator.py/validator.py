import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    pass

class FileValidator:
    """
    Валидатор файлов на основе эталонного JSON-снимка.
    
    :param snapshot_file: путь к файлу снимка (.json)
    :param root_dir: корневая директория для проверки
    :param ignore_patterns: список подстрок/шаблонов для игнорирования путей (упрощённо)
    """
    
    def __init__(self, snapshot_file: Path, root_dir: Path, ignore_patterns: Optional[List[str]] = None):
        
        self.snapshot_file = snapshot_file
        self.root_dir = root_dir.resolve()
        self.ignore_patterns = ignore_patterns or []
        self.snapshot: Optional[Dict] = None
    
    # ------------------------------------------------------------------
    # Загрузка/сохранение снимка
    # ------------------------------------------------------------------
    
    def load_snapshot(self) -> Dict:
        """Загружает эталонный снимок из JSON."""
        if not self.snapshot_file.exists():
            raise ValidationError(f"Snapshot file not found: {self.snapshot_file}")
        with open(self.snapshot_file, 'r', encoding='utf-8') as f:
            self.snapshot = json.load(f)
        if 'files' not in self.snapshot: # pyright: ignore[reportOperatorIssue]
            raise ValidationError("Invalid snapshot format: missing 'files'")
        return self.snapshot # pyright: ignore[reportReturnType]
    
    def generate_snapshot(self, description: str = ""):
        """
        Сканирует root_dir и создаёт снимок: для каждого файла вычисляет SHA1-хеш.
        Сохраняет результат в snapshot_file.
        """
        
        files = {}
        
        for file_path in self.root_dir.rglob('*'):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            if self._is_ignored(rel_path):
                continue
            files[rel_path] = self._calculate_hash(file_path)
        
        snapshot = {
            "version": "1.0",
            "description": description,
            "files": files
        }
        
        with open(self.snapshot_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(snapshot, indent=2, ensure_ascii=False))
        self.snapshot = snapshot
        return snapshot
    
    # ------------------------------------------------------------------
    # Проверка
    # ------------------------------------------------------------------
    
    def validate(self) -> Dict[str, List[str]]:
        """
        Сравнивает текущее состояние с эталоном.
        Возвращает словарь с ключами:
            'missing'  : файлы, которые должны быть, но отсутствуют
            'extra'    : файлы, которые есть, но не должны (лишние)
            'modified' : файлы, чей хеш изменился
        """
        
        if not self.snapshot:
            self.load_snapshot()
        
        expected_files = set(self.snapshot['files'].keys()) # pyright: ignore[reportOptionalSubscript]
        current_files = set()
        current_hashes = {}
        
        # Сканируем текущую директорию
        for file_path in self.root_dir.rglob('*'):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            if self._is_ignored(rel_path):
                continue
            current_files.add(rel_path)
            # Для потенциально измененных файлов вычислим хеш
            if rel_path in expected_files:
                current_hashes[rel_path] = self._calculate_hash(file_path)
        
        missing = expected_files - current_files
        extra = current_files - expected_files
        
        modified = []
        for f in expected_files & current_files:
            expected_hash = self.snapshot['files'][f] # pyright: ignore[reportOptionalSubscript]
            # Если ожидаемый хеш = None, значит изменение допускается
            if expected_hash is None:
                continue
            current_hash = current_hashes.get(f)
            if current_hash is None:
                # Файл есть, но хеш не вычислен
                current_hash = self._calculate_hash(self.root_dir / f)
            if current_hash != expected_hash:
                modified.append(f)
        
        return {
            'missing': sorted(missing),
            'extra': sorted(extra),
            'modified': sorted(modified)
        }
    
    def quick_check(self) -> bool:
        """
        Быстрая проверка: только наличие лишних файлов.
        Возвращает True, если нет лишних файлов (или все лишние в игноре).
        """
        
        if not self.snapshot:
            self.load_snapshot()
        expected_files = set(self.snapshot['files'].keys()) # pyright: ignore[reportOptionalSubscript]
        for file_path in self.root_dir.rglob('*'):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            if self._is_ignored(rel_path):
                continue
            if rel_path not in expected_files:
                return False
        
        return True
    
    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    
    def _calculate_hash(self, file_path: Path, algorithm: str = 'sha1') -> str:
        """Вычисляет хеш файла."""
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    
    def _is_ignored(self, rel_path: str) -> bool:
        """
        Проверяет, нужно ли игнорировать файл.
        Упрощенная реализация: если любая из подстрок ignore_patterns содержится в пути.
        Можно заменить на fnmatch для полноценных шаблонов.
        """
        for pattern in self.ignore_patterns:
            if pattern in rel_path:
                return True
        return False
