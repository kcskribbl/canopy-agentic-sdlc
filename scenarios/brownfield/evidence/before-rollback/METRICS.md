# Metrics: brownfield

```json
{
  "released_at_least_once": true,
  "attempts": {
    "created": 1,
    "tool_requested": 7,
    "passed": 7,
    "approval_requested": 4,
    "approved": 4,
    "released": 1
  },
  "stage_success_rates": {
    "requirements": 1.0,
    "design": 1.0,
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
      "attempts": 1
    },
    "design": {
      "total": 0.062,
      "mean": 0.062,
      "attempts": 1
    },
    "implementation": {
      "total": 0.0,
      "mean": 0.0,
      "attempts": 1
    },
    "qa": {
      "total": 40.343,
      "mean": 40.343,
      "attempts": 1
    },
    "security": {
      "total": 18.265,
      "mean": 18.265,
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
  "elapsed_seconds": 42.569836,
  "retries": 0,
  "rollbacks": 0,
  "replans": 0,
  "human_interventions": 4,
  "mttr_seconds": null,
  "recovery_durations_seconds": [],
  "unrecovered_gates": []
}
```
