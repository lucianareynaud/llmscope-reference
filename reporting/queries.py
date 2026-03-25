"""DuckDB-backed operational queries for canonical questions."""
import duckdb
from pathlib import Path


def cost_by_tenant_and_feature(telemetry_path: str) -> list[dict]:
    """Total and average cost per tenant_id and use_case (feature).
    
    Answers: Which tenant or feature burns the most margin per request?
    
    Args:
        telemetry_path: Path to telemetry JSONL file
        
    Returns:
        List of dicts with tenant_id, feature_id, total_cost_usd, avg_cost_usd, request_count
    """
    if not Path(telemetry_path).exists() or Path(telemetry_path).stat().st_size == 0:
        return []
    
    try:
        conn = duckdb.connect(":memory:")
        query = f"""
            SELECT 
                tenant_id,
                use_case as feature_id,
                SUM(estimated_cost_usd) as total_cost_usd,
                AVG(estimated_cost_usd) as avg_cost_usd,
                COUNT(*) as request_count
            FROM read_json_auto('{telemetry_path}')
            WHERE tenant_id IS NOT NULL
            GROUP BY tenant_id, use_case
            ORDER BY total_cost_usd DESC
        """
        result = conn.execute(query).fetchall()
        conn.close()
        
        return [
            {
                "tenant_id": str(row[0]),
                "feature_id": str(row[1]) if row[1] is not None else None,
                "total_cost_usd": float(row[2]),
                "avg_cost_usd": float(row[3]),
                "request_count": int(row[4])
            }
            for row in result
        ]
    except Exception:
        return []


def experiment_cost_vs_outcome(telemetry_path: str) -> list[dict]:
    """Per experiment_id: average tokens, average cost, finish_reason=stop rate.
    
    Answers: Which experiment increased cost without improving outcome?
    
    Args:
        telemetry_path: Path to telemetry JSONL file
        
    Returns:
        List of dicts with experiment_id, avg_tokens_in, avg_tokens_out, avg_cost_usd, 
        success_rate, request_count
    """
    if not Path(telemetry_path).exists() or Path(telemetry_path).stat().st_size == 0:
        return []
    
    try:
        conn = duckdb.connect(":memory:")
        query = f"""
            SELECT 
                experiment_id,
                AVG(tokens_in) as avg_tokens_in,
                AVG(tokens_out) as avg_tokens_out,
                AVG(estimated_cost_usd) as avg_cost_usd,
                AVG(CASE WHEN finish_reason = 'stop' THEN 1.0 ELSE 0.0 END) as success_rate,
                COUNT(*) as request_count
            FROM read_json_auto('{telemetry_path}')
            WHERE experiment_id IS NOT NULL
            GROUP BY experiment_id
            ORDER BY avg_cost_usd DESC
        """
        result = conn.execute(query).fetchall()
        conn.close()
        
        return [
            {
                "experiment_id": str(row[0]),
                "avg_tokens_in": float(row[1]),
                "avg_tokens_out": float(row[2]),
                "avg_cost_usd": float(row[3]),
                "success_rate": float(row[4]),
                "request_count": int(row[5])
            }
            for row in result
        ]
    except Exception:
        return []


def budget_pressure_by_namespace(decisions_path: str) -> list[dict]:
    """Per budget_namespace: count of allow/downgrade/deny.
    
    Answers: Which namespace triggers downgrade or deny?
    
    Args:
        decisions_path: Path to policy decisions JSONL file
        
    Returns:
        List of dicts with budget_namespace, allow_count, downgrade_count, deny_count, total_count
    """
    if not Path(decisions_path).exists() or Path(decisions_path).stat().st_size == 0:
        return []
    
    try:
        conn = duckdb.connect(":memory:")
        query = f"""
            SELECT 
                budget_namespace,
                SUM(CASE WHEN decision = 'allow' THEN 1 ELSE 0 END) as allow_count,
                SUM(CASE WHEN decision = 'downgrade' THEN 1 ELSE 0 END) as downgrade_count,
                SUM(CASE WHEN decision = 'deny' THEN 1 ELSE 0 END) as deny_count,
                COUNT(*) as total_count
            FROM read_json_auto('{decisions_path}')
            WHERE budget_namespace IS NOT NULL
            GROUP BY budget_namespace
            ORDER BY (downgrade_count + deny_count) DESC
        """
        result = conn.execute(query).fetchall()
        conn.close()
        
        return [
            {
                "budget_namespace": str(row[0]),
                "allow_count": int(row[1]),
                "downgrade_count": int(row[2]),
                "deny_count": int(row[3]),
                "total_count": int(row[4])
            }
            for row in result
        ]
    except Exception:
        return []


def fallback_latency_masking(telemetry_path: str) -> list[dict]:
    """p95 latency per route and is_fallback.
    
    Answers: Which fallbacks are masking latency?
    
    Args:
        telemetry_path: Path to telemetry JSONL file
        
    Returns:
        List of dicts with route_name, is_fallback, p95_latency_ms, avg_latency_ms, request_count
    """
    if not Path(telemetry_path).exists() or Path(telemetry_path).stat().st_size == 0:
        return []
    
    try:
        conn = duckdb.connect(":memory:")
        query = f"""
            SELECT 
                route_name,
                is_fallback,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency_ms,
                AVG(latency_ms) as avg_latency_ms,
                COUNT(*) as request_count
            FROM read_json_auto('{telemetry_path}')
            WHERE route_name IS NOT NULL AND latency_ms IS NOT NULL
            GROUP BY route_name, is_fallback
            ORDER BY p95_latency_ms DESC
        """
        result = conn.execute(query).fetchall()
        conn.close()
        
        return [
            {
                "route_name": str(row[0]),
                "is_fallback": bool(row[1]) if row[1] is not None else False,
                "p95_latency_ms": float(row[2]),
                "avg_latency_ms": float(row[3]),
                "request_count": int(row[4])
            }
            for row in result
        ]
    except Exception:
        return []


def unsafe_routes(telemetry_path: str, cost_threshold_usd: float = 0.05) -> list[dict]:
    """Routes where average cost per request exceeds threshold.
    
    Answers: Which routes are no longer economically safe?
    
    Args:
        telemetry_path: Path to telemetry JSONL file
        cost_threshold_usd: Cost threshold in USD (default 0.05)
        
    Returns:
        List of dicts with route_name, avg_cost_usd, max_cost_usd, request_count
    """
    if not Path(telemetry_path).exists() or Path(telemetry_path).stat().st_size == 0:
        return []
    
    try:
        conn = duckdb.connect(":memory:")
        query = f"""
            SELECT 
                route_name,
                AVG(estimated_cost_usd) as avg_cost_usd,
                MAX(estimated_cost_usd) as max_cost_usd,
                COUNT(*) as request_count
            FROM read_json_auto('{telemetry_path}')
            WHERE route_name IS NOT NULL AND estimated_cost_usd IS NOT NULL
            GROUP BY route_name
            HAVING AVG(estimated_cost_usd) > {cost_threshold_usd}
            ORDER BY avg_cost_usd DESC
        """
        result = conn.execute(query).fetchall()
        conn.close()
        
        return [
            {
                "route_name": str(row[0]),
                "avg_cost_usd": float(row[1]),
                "max_cost_usd": float(row[2]),
                "request_count": int(row[3])
            }
            for row in result
        ]
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python -m reporting.queries <query_name> [--telemetry path] [--decisions path] [--threshold value]")
        print("\nAvailable queries:")
        print("  cost_by_tenant_and_feature")
        print("  experiment_cost_vs_outcome")
        print("  budget_pressure_by_namespace")
        print("  fallback_latency_masking")
        print("  unsafe_routes")
        sys.exit(1)
    
    query_name = sys.argv[1]
    
    # Parse arguments
    telemetry_path = "artifacts/logs/telemetry.jsonl"
    decisions_path = "artifacts/logs/policy_decisions.jsonl"
    threshold = 0.05
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--telemetry" and i + 1 < len(sys.argv):
            telemetry_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--decisions" and i + 1 < len(sys.argv):
            decisions_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--threshold" and i + 1 < len(sys.argv):
            threshold = float(sys.argv[i + 1])
            i += 2
        else:
            i += 1
    
    # Execute query
    if query_name == "cost_by_tenant_and_feature":
        result = cost_by_tenant_and_feature(telemetry_path)
    elif query_name == "experiment_cost_vs_outcome":
        result = experiment_cost_vs_outcome(telemetry_path)
    elif query_name == "budget_pressure_by_namespace":
        result = budget_pressure_by_namespace(decisions_path)
    elif query_name == "fallback_latency_masking":
        result = fallback_latency_masking(telemetry_path)
    elif query_name == "unsafe_routes":
        result = unsafe_routes(telemetry_path, threshold)
    else:
        print(f"Unknown query: {query_name}")
        sys.exit(1)
    
    print(json.dumps(result, indent=2))
