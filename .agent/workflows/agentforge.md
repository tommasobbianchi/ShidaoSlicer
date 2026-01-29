---
description: AgentForge Delegation Paradigm - Use these tools by default
---

# AgentForge Tools - ORCA_BELT

## Philosophy

**Delegate execution, focus on strategy.** Use these tools for:

- Builds, tests, and long-running tasks
- Notifications and status updates
- Repetitive workflows

## Available Tools

### 1. Async Build (`./async_build.sh`)

// turbo-all

```bash
# Start async build (systemd-run, background)
./async_build.sh build -s

# Check status
./async_build.sh status

# View live logs
./async_build.sh logs

# Stop build
./async_build.sh stop
```

### 2. Delegation Script (`scripts/delegate_agentforge.py`)

```bash
# Delegate build
python3 scripts/delegate_agentforge.py build

# Delegate tests
python3 scripts/delegate_agentforge.py test

# Delegate custom task (from spec file)
python3 scripts/delegate_agentforge.py path/to/task_spec.md
```

### 3. Telegram Notifications (`./telegram_notify.sh`)

```bash
./telegram_notify.sh start "PROJECT" "job_id"
./telegram_notify.sh finish "PROJECT" "success|failure" "log_path" "exit_code"
```

### 4. Belt Printer Testing

```bash
# Run unit tests
./scripts/run_unit_tests.sh

# Test belt print
./scripts/test_belt_print.sh

# Certification
./scripts/certify_belt_printer.sh
```

## Decision Matrix

| Task              | Tool                          | Rationale                    |
| ----------------- | ----------------------------- | ---------------------------- |
| Build project     | `async_build.sh build`        | Background, resource-limited |
| Check build       | `async_build.sh status`       | JSON state file              |
| Run tests         | `delegate_agentforge.py test` | Parallel, monitored          |
| Send notification | `telegram_notify.sh`          | User alerting                |
| CLI slicing test  | Manual (quick)                | Direct feedback needed       |

## Workflow Rules

1. **Always check** for async_build state before starting new builds
2. **Prefer delegation** for tasks > 2 minutes
3. **Use notifications** for completed long tasks
4. **Focus on** planning, decision-making, code review
