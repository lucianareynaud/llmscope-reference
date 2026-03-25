"""YAML policy configuration loader."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class PolicyRule:
    """Single policy rule configuration."""

    id: str
    primitive: str
    period: str | None = None
    limit_usd: float | None = None
    action: str | None = None
    downgrade_to_tier: str | None = None
    deny_reason: str | None = None
    route_name: str | None = None
    prefer_tier: str | None = None
    feature_id: str | None = None
    baseline_window_hours: int | None = None
    threshold_multiplier: float | None = None


@dataclass
class PolicyNamespace:
    """Policy namespace configuration."""

    rules: list[PolicyRule]


@dataclass
class PolicyConfig:
    """Complete policy configuration."""

    version: str
    namespaces: dict[str, PolicyNamespace]


def load_policy(path: str) -> PolicyConfig:
    """Load and validate YAML policy configuration.

    Args:
        path: Path to YAML policy file

    Returns:
        PolicyConfig object

    Raises:
        ValueError: If YAML is invalid or file doesn't exist
    """
    policy_path = Path(path)

    if not policy_path.exists():
        raise ValueError(f"Policy file not found: {path}")

    try:
        with open(policy_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")

    if not isinstance(data, dict):
        raise ValueError("Policy file must contain a YAML object")

    if "version" not in data:
        raise ValueError("Policy file must contain 'version' field")

    if "namespaces" not in data:
        raise ValueError("Policy file must contain 'namespaces' field")

    namespaces = {}
    for ns_name, ns_data in data["namespaces"].items():
        if "rules" not in ns_data:
            raise ValueError(f"Namespace '{ns_name}' must contain 'rules' field")

        rules = []
        for rule_data in ns_data["rules"]:
            if "id" not in rule_data:
                raise ValueError(f"Rule in namespace '{ns_name}' must have 'id' field")
            if "primitive" not in rule_data:
                raise ValueError(f"Rule '{rule_data.get('id')}' must have 'primitive' field")

            rules.append(PolicyRule(
                id=rule_data["id"],
                primitive=rule_data["primitive"],
                period=rule_data.get("period"),
                limit_usd=rule_data.get("limit_usd"),
                action=rule_data.get("action"),
                downgrade_to_tier=rule_data.get("downgrade_to_tier"),
                deny_reason=rule_data.get("deny_reason"),
                route_name=rule_data.get("route_name"),
                prefer_tier=rule_data.get("prefer_tier"),
                feature_id=rule_data.get("feature_id"),
                baseline_window_hours=rule_data.get("baseline_window_hours"),
                threshold_multiplier=rule_data.get("threshold_multiplier"),
            ))

        namespaces[ns_name] = PolicyNamespace(rules=rules)

    return PolicyConfig(
        version=data["version"],
        namespaces=namespaces
    )
