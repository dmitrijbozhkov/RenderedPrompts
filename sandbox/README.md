# Agent Sandbox on Kubernetes

This repository is a small example of using the Kubernetes SIGs
[Agent Sandbox](https://agent-sandbox.sigs.k8s.io/) extensions and Python SDK.
It assumes the Agent Sandbox controller and extension CRDs are already
installed.

## Layout

```text
agent-sandbox-config/  SandboxTemplate, warm pool, and shared PVC
client/                Python SDK example
```

The warm pool keeps three Python runtime sandboxes ready. All of them mount the
same `ReadWriteMany` claim at `/shared`.

## Prerequisites

- A current Agent Sandbox installation with the extension CRDs.
- A default `StorageClass` that can provision `ReadWriteMany` volumes. Set
  `storageClassName` in `agent-sandbox-config/shared-pvc.yaml` if needed.
- A container image for the client code when running the example in-cluster.
- Python 3.10 or newer.

## Deploy

```bash
kubectl apply -k agent-sandbox-config
kubectl -n agent-sandbox-demo get sandboxwarmpools,sandboxes,pods,pvc
```

Wait until the warm pool reports three ready instances and the PVC is `Bound`.

## Run the client in-cluster

Package `client/main.py` and `client/requirements.txt` in your application
image, then run that image in a Deployment or Job using the included
ServiceAccount:

```yaml
spec:
  template:
    spec:
      serviceAccountName: sandbox-client
      containers:
        - name: client
          image: your-client-image
```

The program uses the async SDK to check out two warm sandboxes concurrently. It
runs inline Python through shell commands, writes a JSON document to `/shared`
from the first sandbox, and reads it from the second. Claims are terminated in
`finally` blocks.

`SandboxInClusterConnectionConfig` makes the pod authenticate with its mounted
ServiceAccount token and connect directly to the sandbox runtime through cluster
DNS. The client container must install `client/requirements.txt` and run
`python client/main.py`.

This mode needs neither an external Gateway nor a Router.

Pass different Python source with:

```bash
python client/main.py --code 'import platform; print(platform.platform())'
```

Use `--keep` while debugging to retain claims. Delete retained claims manually:

```bash
kubectl -n agent-sandbox-demo delete sandboxclaims --all
```

## How this can grow

- Build and pin a project-owned runtime image instead of using the staging
  `latest-main` image. Add the OS packages, Python dependencies, non-root user,
  and the Agent Sandbox runtime server to that image.
- Add overlays such as `overlays/dev` and `overlays/prod` for pool size,
  resource limits, storage classes, runtime classes, and image digests.
- Add a client Deployment or Job and build its container image; use Gateway
  mode for external production callers.
- Add NetworkPolicies, admission policies, quotas, monitoring, autoscaling, and
  PodDisruptionBudgets. Use gVisor or Kata Containers when executing untrusted
  code.
- Allocate one volume per sandbox with `volumeClaimTemplates` when shared state
  is not intentional.

## Gotchas

- A shared claim requires a storage backend that truly supports
  `ReadWriteMany` (for example NFS, CephFS, or a suitable cloud file service).
  Many default block-disk storage classes only support `ReadWriteOnce`.
- `/shared` is deliberately not an isolation boundary. Concurrent sandboxes can
  overwrite files, observe each other's data, and contend on locks. Use
  per-claim directories plus file locking, or prefer per-sandbox PVCs.
- A plain `ubuntu` or `python` image is not sufficient for the SDK: it must run
  the Agent Sandbox runtime HTTP API. The example uses the upstream Python
  runtime image and exposes port 8888.
- Warm-pool capacity is spare capacity. Checked-out sandboxes cause the
  controller to create replacements, so budget for both active claims and warm
  replicas.
- The SDK, CRDs, and runtime image must be version-compatible. Pin all three in
  real deployments and review migration notes before upgrades.
- Treat generated shell text as hostile. This example quotes inline Python with
  `shlex.quote`; avoid concatenating untrusted values into shell commands.
- Terminate claims on every error path and add lifecycle TTLs for crash cleanup.
  Retained claims and PVCs can otherwise accumulate cost and data.
