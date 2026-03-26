"""Policy decision logging to JSONL."""
import fcntl
import json
from pathlib import Path

from policy.models import PolicyDecisionRecord


class PolicyDecisionLog:
    """Append-only JSONL logger for policy decisions."""

    @staticmethod
    def append(record: PolicyDecisionRecord, path: str) -> None:
        """Append a policy decision record to JSONL file atomically.

        Uses POSIX advisory file locking (fcntl.LOCK_EX) to prevent concurrent
        writes from producing interleaved or partial JSON lines. The lock is
        released automatically when the file handle closes.

        This is advisory locking — it does not prevent access from processes
        that do not also use fcntl (e.g., log readers).

        Args:
            record: PolicyDecisionRecord to log
            path: Absolute path to JSONL file
        """
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(record.to_dict()) + "\n"

        with open(log_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
