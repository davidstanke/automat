# Auto-Reload Rule for Agents in /agents

When starting an agent locally, always run from the repository root with auto-reloading enabled so file changes take effect immediately. Trigger reloading on the entire `agents` directory because the agents are interdependent.

## Starting Agents with Auto-Reload

```bash
uvx watchfiles "uv --directory agents/<agent_name> run main.py" agents
```

**Examples:**
```bash
uvx watchfiles "uv --directory agents/sched_agent run main.py" agents
uvx watchfiles "uv --directory agents/strat_agent run main.py" agents
uvx watchfiles "uv --directory agents/luncher_agent run main.py" agents
```

## Port Cleanup & Lifecycle Management

When clearing or resetting local agent ports (8080–8083), use repeated `-i` flags with `lsof` to avoid syntax errors:

```bash
PIDS=$(lsof -t -i :8080 -i :8081 -i :8082 -i :8083 2>/dev/null); [ -n "$PIDS" ] && kill -9 $PIDS
```

## Health & Endpoint Verification

Always quote URLs containing query parameters when making verification requests in zsh:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8080/dev-ui/?app=app"
```

## Default Model Configuration

- The standard default Gemini model across the workspace is `gemini-3.7-flash`.