import os
import sys
import shutil
import subprocess
import logging
from config import MEDIA_DIRS, MEDIA_THRESHOLD

# Resolve yt-dlp path relative to the running Python's venv
_YTDLP = os.path.join(os.path.dirname(sys.executable), "yt-dlp")

logger = logging.getLogger(__name__)


def get_disk_usage(path: str) -> dict | None:
    """Get disk usage for the mount point of path."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": usage.used / usage.total,
        }
    except Exception:
        return None


def _format_size(bytes_val: int) -> str:
    if bytes_val < 1024 ** 2:
        return f"{bytes_val / 1024:.1f}KB"
    if bytes_val < 1024 ** 3:
        return f"{bytes_val / (1024 ** 2):.1f}MB"
    return f"{bytes_val / (1024 ** 3):.1f}GB"


def find_active_dir() -> str | None:
    """Find first mounted and writable media directory."""
    for d in MEDIA_DIRS:
        if os.path.ismount(d) or os.path.isdir(d):
            if os.access(d, os.W_OK):
                return d
    return None


def cleanup_old_files(target_dir: str) -> list[str]:
    """Delete oldest files until usage <= MEDIA_THRESHOLD. Returns deleted filenames.
    Only deletes files INSIDE target_dir. If target_dir shares the system disk
    (not a separate mount), only media files in target_dir are counted/deleted."""
    # Safety: only measure usage of files inside target_dir, not whole disk,
    # when target_dir is NOT a separate mount point
    is_separate_mount = os.path.ismount(target_dir)

    if is_separate_mount:
        usage = get_disk_usage(target_dir)
        if not usage or usage["percent"] <= MEDIA_THRESHOLD:
            return []
    else:
        # For local dirs on system disk: limit by directory size, not disk usage
        # Don't auto-delete from system disk — just stop downloading
        logger.info(f"Skipping cleanup: {target_dir} is on system disk")
        return []

    # Only target video/audio files for deletion
    MEDIA_EXTENSIONS = {
        ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v",
        ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma",
    }

    all_files = []
    for root, dirs, files in os.walk(target_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in MEDIA_EXTENSIONS:
                continue
            fpath = os.path.join(root, f)
            try:
                all_files.append((fpath, os.path.getmtime(fpath), os.path.getsize(fpath)))
            except OSError:
                continue

    all_files.sort(key=lambda x: x[1])  # oldest first

    deleted = []
    for fpath, mtime, size in all_files:
        usage = get_disk_usage(target_dir)
        if not usage or usage["percent"] <= MEDIA_THRESHOLD:
            break
        try:
            os.remove(fpath)
            deleted.append(os.path.basename(fpath))
            logger.info(f"Cleaned up: {fpath} ({_format_size(size)})")
        except OSError as e:
            logger.warning(f"Failed to delete {fpath}: {e}")

    # Remove empty directories
    for root, dirs, files in os.walk(target_dir, topdown=False):
        for d in dirs:
            dpath = os.path.join(root, d)
            try:
                if not os.listdir(dpath):
                    os.rmdir(dpath)
            except OSError:
                pass

    return deleted


def download_youtube(url: str) -> dict:
    """Download YouTube video to active media directory. Returns result info."""
    target_dir = find_active_dir()
    if not target_dir:
        return {"ok": False, "error": "No writable media directory found. Check USB mounts."}

    # Check space and cleanup if needed
    is_separate_mount = os.path.ismount(target_dir)
    usage = get_disk_usage(target_dir)

    if usage and usage["percent"] > MEDIA_THRESHOLD:
        if is_separate_mount:
            # External USB: auto-cleanup old files
            deleted = cleanup_old_files(target_dir)
            if deleted:
                logger.info(f"Cleaned {len(deleted)} files before download")
        else:
            # System disk: try to find an external USB instead
            found_external = False
            for d in MEDIA_DIRS:
                if d != target_dir and os.path.ismount(d) and os.access(d, os.W_OK):
                    target_dir = d
                    found_external = True
                    break
            if not found_external:
                return {
                    "ok": False,
                    "error": f"System disk is {usage['percent'] * 100:.0f}% full. "
                    "Connect an external USB to continue downloading. "
                    "Auto-cleanup is disabled on system disk for safety.",
                }

    # Check free space
    usage = get_disk_usage(target_dir)
    if usage and usage["free"] < 100 * 1024 * 1024:  # less than 100MB free
        for d in MEDIA_DIRS:
            if d != target_dir and (os.path.ismount(d) or os.path.isdir(d)):
                if os.access(d, os.W_OK):
                    target_dir = d
                    break
        else:
            return {"ok": False, "error": "All media directories are full."}

    # Validate URL — only allow YouTube and Instagram domains
    import re
    url = url.strip()
    ALLOWED_DOMAINS = r'^https?://(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com|instagram\.com|instagr\.am)/'
    if not re.match(ALLOWED_DOMAINS, url):
        return {"ok": False, "error": "Only YouTube and Instagram URLs are allowed."}

    # Download with yt-dlp (list args, no shell=True — safe from injection)
    output_template = os.path.join(target_dir, "%(title)s.%(ext)s")
    cmd = [
        _YTDLP,
        "--no-playlist",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--print", "after_move:filepath",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
        )
        if result.returncode != 0:
            error = result.stderr.strip().split("\n")[-1] if result.stderr else "Unknown error"
            return {"ok": False, "error": error}

        filepath = result.stdout.strip().split("\n")[-1]
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

        usage = get_disk_usage(target_dir)
        return {
            "ok": True,
            "filename": filename,
            "filesize": _format_size(filesize),
            "path": filepath,
            "disk_usage": f"{usage['percent'] * 100:.0f}%" if usage else "unknown",
            "disk_free": _format_size(usage['free']) if usage else "unknown",
            "directory": target_dir,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Download timed out (10 min limit)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_storage_status() -> str:
    """Get status of all media directories."""
    lines = []
    for d in MEDIA_DIRS:
        if not (os.path.ismount(d) or os.path.isdir(d)):
            lines.append(f"- {d}: NOT MOUNTED")
            continue
        usage = get_disk_usage(d)
        if not usage:
            lines.append(f"- {d}: ERROR")
            continue
        file_count = sum(len(files) for _, _, files in os.walk(d))
        lines.append(
            f"- {d}: {usage['percent'] * 100:.0f}% used "
            f"({_format_size(usage['used'])}/{_format_size(usage['total'])}) "
            f"| {_format_size(usage['free'])} free | {file_count} files"
        )
    return "\n".join(lines) if lines else "No media directories configured."


def list_media_files(limit: int = 20) -> str:
    """List recent media files across all directories."""
    all_files = []
    for d in MEDIA_DIRS:
        if not (os.path.ismount(d) or os.path.isdir(d)):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    all_files.append((fpath, os.path.getmtime(fpath), os.path.getsize(fpath)))
                except OSError:
                    continue

    all_files.sort(key=lambda x: x[1], reverse=True)  # newest first

    if not all_files:
        return "No media files."

    lines = []
    for fpath, mtime, size in all_files[:limit]:
        from datetime import datetime
        date = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
        lines.append(f"- {os.path.basename(fpath)} ({_format_size(size)}) [{date}]")

    return "\n".join(lines)
