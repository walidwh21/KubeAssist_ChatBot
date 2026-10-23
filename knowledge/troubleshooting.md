# Troubleshooting pods

CrashLoopBackOff: the container starts and exits repeatedly. Read the previous container's output with
`kubectl logs <pod> --previous`, then check `kubectl describe pod <pod>` for the exit code and events.

ImagePullBackOff or ErrImagePull: the image name or tag is wrong, or the registry needs credentials. Verify the
image in `kubectl describe pod <pod>` and confirm the imagePullSecret exists.

Pending: the scheduler cannot place the pod. Events usually say why — insufficient CPU or memory, an unbound
PersistentVolumeClaim, or node taints without matching tolerations.

OOMKilled: the container exceeded its memory limit. Raise the limit or fix the leak; confirm with
`kubectl describe pod <pod>` (Last State: Terminated, Reason: OOMKilled).

# Quick health checks

`kubectl get nodes` shows node readiness. `kubectl top pods` shows CPU and memory when metrics-server is installed.
`kubectl get events -A --sort-by=.metadata.creationTimestamp` lists what happened most recently.
