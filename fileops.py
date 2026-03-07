import os
import shutil
from config import FILE_ROOT


def _safe_path(path: str) -> str:
    """Resolve path and ensure it stays within FILE_ROOT."""
    if not path:
        return FILE_ROOT
    # Handle relative paths as relative to FILE_ROOT
    if not os.path.isabs(path):
        full = os.path.join(FILE_ROOT, path)
    else:
        full = path
    full = os.path.realpath(full)
    if not full.startswith(os.path.realpath(FILE_ROOT)):
        raise PermissionError(f"Access denied: path outside {FILE_ROOT}")
    return full


def list_dir(path: str = "") -> str:
    target = _safe_path(path)
    if not os.path.isdir(target):
        return f"Not a directory: {path}"
    entries = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        if os.path.isdir(full):
            entries.append(f"[DIR]  {name}/")
        else:
            size = os.path.getsize(full)
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size // 1024}KB"
            else:
                size_str = f"{size // (1024 * 1024)}MB"
            entries.append(f"[FILE] {name} ({size_str})")
    return "\n".join(entries) if entries else "(empty directory)"


def read_file(path: str, max_chars: int = 3000) -> str:
    target = _safe_path(path)
    if not os.path.isfile(target):
        return f"File not found: {path}"
    with open(target, "r", errors="replace") as f:
        content = f.read(max_chars)
    if len(content) == max_chars:
        content += "\n... (truncated)"
    return content


def write_file(path: str, content: str) -> str:
    target = _safe_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        f.write(content)
    return f"Written: {path}"


def move_file(src: str, dst: str) -> str:
    src_path = _safe_path(src)
    dst_path = _safe_path(dst)
    if not os.path.exists(src_path):
        return f"Not found: {src}"
    # If dst is a directory, move into it
    if os.path.isdir(dst_path):
        dst_path = os.path.join(dst_path, os.path.basename(src_path))
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.move(src_path, dst_path)
    return f"Moved: {src} -> {dst}"


def make_dir(path: str) -> str:
    target = _safe_path(path)
    os.makedirs(target, exist_ok=True)
    return f"Created directory: {path}"
