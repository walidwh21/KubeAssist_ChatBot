# Example runbook: releasing to a pre-production environment

Replace this file with your own team procedures; the assistant retrieves from everything in this folder.

1. Confirm the release candidate image tag has passed CI.
2. Update the image with `kubectl set image deployment/<name> <container>=<image>:<tag> -n <namespace>`.
3. Watch the rollout: `kubectl rollout status deployment/<name> -n <namespace>`.
4. If health checks fail, roll back: `kubectl rollout undo deployment/<name> -n <namespace>`.
