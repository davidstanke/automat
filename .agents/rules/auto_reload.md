# Auto-Reload Rule for Agents in /agents

When starting an agent locally, always run from the repository root with auto-reloading enabled so file changes take effect immediately. Trigger reloading on the entire `agents` directory because the agents are interdependent.

Example:

```bash
uvx watchfiles "uv --directory agents/<agent_name> run main.py" agents
```

**Example:**
```bash
uvx watchfiles "uv --directory agents/sched_agent run main.py" agents
```