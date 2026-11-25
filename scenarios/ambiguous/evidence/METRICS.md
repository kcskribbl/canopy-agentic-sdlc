# Metrics: ambiguous

```json
{
  "released_at_least_once": true,
  "attempts": {
    "created": 1,
    "tool_requested": 10,
    "passed": 9,
    "clarification_requested": 1,
    "invalidated": 2,
    "revise": 2,
    "approval_requested": 5,
    "approved": 5,
    "failed": 1,
    "safe_stop": 1,
    "repair_authorized": 1,
    "released": 1
  },
  "stage_success_rates": {
    "requirements": 1.0,
    "design": 0.5,
    "implementation": 1.0,
    "qa": 1.0,
    "security": 1.0,
    "documentation": 1.0,
    "readiness": 1.0
  },
  "stage_latency_seconds": {
    "requirements": {
      "total": 0.0,
      "mean": 0.0,
      "attempts": 3
    },
    "design": {
      "total": 0.17099999999999999,
      "mean": 0.08549999999999999,
      "attempts": 2
    },
    "implementation": {
      "total": 0.0,
      "mean": 0.0,
      "attempts": 1
    },
    "qa": {
      "total": 35.172,
      "mean": 35.172,
      "attempts": 1
    },
    "security": {
      "total": 17.156,
      "mean": 17.156,
      "attempts": 1
    },
    "documentation": {
      "total": 0.0,
      "mean": 0.0,
      "attempts": 1
    },
    "readiness": {
      "total": 0.0,
      "mean": 0.0,
      "attempts": 1
    }
  },
  "elapsed_seconds": 39.787786,
  "retries": 1,
  "rollbacks": 0,
  "replans": 2,
  "human_interventions": 7,
  "mttr_seconds": 1.449845,
  "recovery_durations_seconds": [
    1.449845
  ],
  "unrecovered_gates": []
}
```
