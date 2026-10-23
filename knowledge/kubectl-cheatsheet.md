# kubectl cheat sheet

Request: show me the pods
Command: kubectl get pods

Request: list pods in the shop namespace
Command: kubectl get pods -n shop

Request: list every pod in the cluster
Command: kubectl get pods -A

Request: describe the deployment api
Command: kubectl describe deployment api

Request: show logs for pod web-7d9f in namespace shop
Command: kubectl logs web-7d9f -n shop

Request: scale the deployment api to 3 replicas
Command: kubectl scale deployment api --replicas=3

Request: restart a deployment
Command: kubectl rollout restart deployment api

Request: check rollout progress
Command: kubectl rollout status deployment/api

Request: list namespaces
Command: kubectl get namespaces

Request: create a namespace called staging
Command: kubectl create namespace staging

Request: delete a pod
Command: kubectl delete pod web-7d9f -n shop

Request: see cluster nodes and their versions
Command: kubectl get nodes -o wide

Request: recent events, newest last
Command: kubectl get events --sort-by=.metadata.creationTimestamp
