import os
import socket
from pathlib import Path



def get_free_port(preferred: int | None = None) -> int:
    if preferred is not None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', preferred)) != 0:
                return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def write_lock(port: int, lock_path: Path) -> None:
    Path(lock_path).write_text(f'{os.getpid()}\n{port}', encoding='utf-8')


def read_lock(lock_path: Path) -> int | None:
    lock_path = Path(lock_path)
    if not lock_path.exists():
        return None
    parts = lock_path.read_text(encoding='utf-8').strip().split('\n')
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def read_pid(lock_path: Path) -> int | None:
    lock_path = Path(lock_path)
    if not lock_path.exists():
        return None
    parts = lock_path.read_text(encoding='utf-8').strip().split('\n')
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return None


def release_lock(lock_path: Path) -> None:
    Path(lock_path).unlink(missing_ok=True)
