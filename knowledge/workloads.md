# Pods

A Pod is the smallest deployable unit in Kubernetes. It wraps one or more containers that share a network
namespace and storage volumes. Pods are ephemeral: when one dies it is replaced, not repaired, and the
replacement gets a new name and IP address.

List pods with `kubectl get pods -n <namespace>`. Inspect one with `kubectl describe pod <name> -n <namespace>`.

# Deployments

A Deployment manages stateless applications. It keeps the desired number of pod replicas running and performs
rolling updates. Scale it with `kubectl scale deployment <name> --replicas=<n>`, watch an update with
`kubectl rollout status deployment/<name>`, and roll back with `kubectl rollout undo deployment/<name>`.

# StatefulSets, DaemonSets and Jobs

A StatefulSet gives pods stable names and storage for databases and queues. A DaemonSet runs one pod per node,
typically for log shippers and monitoring agents. A Job runs a pod to completion; a CronJob runs Jobs on a schedule.
