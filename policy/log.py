"""Policy decision logging to JSONL."""
import json
from pathlib import Path
from policy.models import PolicyDecisionRecord


class PolicyDecisionLog:
    """Append-only JSONL logger for policy decisions."""
    
    @staticmethod
    def append(record: PolicyDecisionRecord, path: str) -> None:
        """Append a policy decision record to JSONL file atomically.
        
        Args:
            record: PolicyDecisionRecord to log
            path: Absolute path to JSONL file
        """
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        line = json.dumps(record.to_dict()) + "\n"
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
