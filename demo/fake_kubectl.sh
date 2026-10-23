#!/usr/bin/env bash
# A stand-in for kubectl that prints canned output, so the UI can be tried without a cluster.
# Usage: KUBEASSIST_KUBECTL_BIN=$PWD/demo/fake_kubectl.sh KUBEASSIST_KUBECONFIG=$PWD/demo/kubeconfig.yaml python run.py
args=("$@")
# Drop "--context <name>" which the app always injects.
filtered=()
skip=0
for a in "${args[@]}"; do
  if [[ $skip -eq 1 ]]; then skip=0; continue; fi
  if [[ "$a" == "--context" ]]; then skip=1; continue; fi
  filtered+=("$a")
done
verb="${filtered[0]}"; res="${filtered[1]}"
case "$verb $res" in
  "get pods"*|"get po"*)
    cat <<'OUT'
NAME                       READY   STATUS             RESTARTS      AGE
api-6c5d9f7b8-kx2vp        1/1     Running            0             3d4h
api-6c5d9f7b8-q9tlm        1/1     Running            0             3d4h
web-7d9f6b5c44-8fzrn       1/1     Running            1 (2d ago)    5d
worker-5b7c8d9f66-2hn7d    0/1     CrashLoopBackOff   14 (3m ago)   52m
OUT
    ;;
  "get deployments"*|"get deploy"*)
    cat <<'OUT'
NAME     READY   UP-TO-DATE   AVAILABLE   AGE
api      2/2     2            2           12d
web      1/1     1            1           12d
worker   0/1     1            0           52m
OUT
    ;;
  "get namespaces"*|"get ns"*)
    cat <<'OUT'
NAME              STATUS   AGE
default           Active   41d
kube-system       Active   41d
monitoring        Active   30d
shop              Active   12d
OUT
    ;;
  "get nodes"*)
    cat <<'OUT'
NAME       STATUS   ROLES           AGE   VERSION
node-a1    Ready    control-plane   41d   v1.31.2
node-b1    Ready    <none>          41d   v1.31.2
node-b2    Ready    <none>          41d   v1.31.2
OUT
    ;;
  "get services"*|"get svc"*)
    cat <<'OUT'
NAME   TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
api    ClusterIP   10.96.14.201    <none>        8080/TCP   12d
web    NodePort    10.96.88.17     <none>        80:31080/TCP   12d
OUT
    ;;
  "logs "*)
    cat <<OUT
2026-10-23T09:14:02Z INFO  starting ${filtered[1]}
2026-10-23T09:14:03Z INFO  listening on :8080
2026-10-23T09:14:41Z WARN  upstream latency 480ms
OUT
    ;;
  "describe "*)
    cat <<OUT
Name:         ${filtered[2]}
Namespace:    shop
Status:       Running
Containers:
  app:
    Image:          registry.example.com/shop/${filtered[2]}:1.8.2
    Restart Count:  0
Events:           <none>
OUT
    ;;
  "delete "*)   echo "${filtered[1]} \"${filtered[2]}\" deleted" ;;
  "scale "*)    echo "${filtered[1]}.apps/${filtered[2]} scaled" ;;
  "create "*)   echo "${filtered[1]}/${filtered[2]} created" ;;
  "rollout "*)  echo "${filtered[2]}.apps/${filtered[3]} restarted" ;;
  *) echo "error: demo kubectl does not know '${filtered[*]}'" >&2; exit 1 ;;
esac
