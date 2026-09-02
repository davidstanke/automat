# Agent Runtime Deployment Rules

When deploying an agent to **Agent Runtime** using `agents-cli`, the following rules and standards MUST be strictly followed:

## 1. Agent Identity Requirement
- **ALWAYS** pass the `--agent-identity` flag whenever deploying an agent to Agent Runtime.
- Agent Identity ensures secure runtime credentials, identity propagation, and governance integration (such as Agent Gateway).

```bash
# Standard deployment command
agents-cli deploy --agent-identity
```

## 2. Non-Interactive Executions
- In automated or non-interactive environments where the project is resolved automatically, include `--no-confirm-project` to prevent interactive prompt blocking:

```bash
agents-cli deploy --agent-identity --no-confirm-project
```
