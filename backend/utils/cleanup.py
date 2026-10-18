import logging
import os
import re
import shutil
import time

from backend.config import settings

logger = logging.getLogger(__name__)

GENERATION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def purge_expired_generations(now=None):
    """Delete generation directories older than GENERATION_TTL_SECONDS."""

    root = settings.GENERATED_DIR
    now = time.time() if now is None else now

    try:
        entries = os.listdir(root)
    except FileNotFoundError:
        return 0

    removed = 0

    for entry in entries:

        path = os.path.join(root, entry)

        if not GENERATION_ID_PATTERN.match(entry) or not os.path.isdir(path):
            continue

        try:
            expired = now - os.path.getmtime(path) > settings.GENERATION_TTL_SECONDS
        except OSError:
            continue

        if expired:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1

    if removed:
        logger.info("Purged %d expired generation(s) from %s", removed, root)

    return removed
