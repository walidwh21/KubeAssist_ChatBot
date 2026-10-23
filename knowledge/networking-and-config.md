# Services

A Service gives a stable virtual IP and DNS name to a set of pods selected by labels. Types: ClusterIP (internal
only, the default), NodePort (opens a port on every node), LoadBalancer (asks the cloud provider for an external
load balancer). List them with `kubectl get svc -n <namespace>`.

# Ingress

An Ingress routes external HTTP(S) traffic to Services by host and path. It needs an ingress controller to be
installed in the cluster.

# Namespaces

Namespaces split one cluster into virtual clusters for teams or environments. Most commands accept `-n <namespace>`
or `-A` for all namespaces. Resources such as nodes and persistent volumes are cluster-wide.

# ConfigMaps and Secrets

ConfigMaps hold non-sensitive configuration; Secrets hold credentials and are only base64-encoded, not encrypted,
unless encryption at rest is enabled. Prefer mounting them as files or environment variables.
