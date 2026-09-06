# Cloud / Kubernetes Deployment — **[L4], do not build yet**

> **Status: deferred.** This is a complete design, held until a second machine actually needs the board (`docs/07-roadmap.md`). It is documented now so that L0's `Store` interface is shaped correctly on day one — not so that it gets built in week one. The KEDA/queue-depth section additionally depends on **L2**, which is itself deferred.

Same image, same tool surface, different `Store` and artifact drivers (D1). Nothing in an agent's prompt changes between local and cluster — only the MCP endpoint URL and the token.

## Topology
```
                          ┌─────────────────────────────────────────┐
   Agent pods / Jobs ────► │  bb-gateway (Deployment, 2–5 replicas)  │
   (Claude, Gemini,        │  MCP Streamable HTTP + REST mirror      │
    local models)          │  stateless · JWT verify · budget guard  │
                          └───────────┬─────────────────┬───────────┘
                                      │                 │
                        ┌─────────────▼──────┐   ┌──────▼───────────────┐
                        │ Postgres (CNPG HA) │   │ MinIO / S3           │
                        │ entries, tasks,    │   │ content-addressed    │
                        │ events, grants     │   │ artifacts sha256/... │
                        └────────────────────┘   └──────────────────────┘
                                      │
                        ┌─────────────▼──────┐
                        │ KEDA ScaledObject  │  scales worker Jobs on
                        │ blackboard_tasks   │  state="ready" depth
                        └────────────────────┘
```

## Why Postgres in-cluster and not SQLite on a PVC
SQLite over NFS/EFS/RWX has unsafe advisory locking; concurrent gateway replicas will corrupt it. Options, in order of preference:
1. **Postgres (CloudNativePG)** — multi-replica gateway, real HA, `LISTEN/NOTIFY` for `watch_events`. Default for anything multi-tenant or >5 workers.
2. **Single-replica gateway + SQLite on an RWO PVC** — valid for a small team or a per-run ephemeral board. Set `replicas: 1`, `strategy: Recreate`, and accept the restart gap. Cheapest path to "it works in the cluster today".

## Manifests (skeleton)

**Namespace + isolation (one workspace ≈ one namespace, Q15/R8)**
```yaml
apiVersion: v1
kind: Namespace
metadata: { name: bb-acme-audit, labels: { blackboard.io/workspace: acme-audit } }
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny, namespace: bb-acme-audit }
spec: { podSelector: {}, policyTypes: [Ingress, Egress] }
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: workers-to-gateway-only, namespace: bb-acme-audit }
spec:
  podSelector: { matchLabels: { app: bb-worker } }
  policyTypes: [Egress]
  egress:
    - to: [{ podSelector: { matchLabels: { app: bb-gateway } } }]
      ports: [{ port: 8787, protocol: TCP }]
    - to: [{ namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } } }]
      ports: [{ port: 53, protocol: UDP }]     # DNS
    # model-provider egress added explicitly per workload; default is deny
```

**Gateway**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: bb-gateway, namespace: bb-acme-audit }
spec:
  replicas: 2
  selector: { matchLabels: { app: bb-gateway } }
  template:
    metadata: { labels: { app: bb-gateway } }
    spec:
      serviceAccountName: bb-gateway
      automountServiceAccountToken: false
      securityContext: { runAsNonRoot: true, runAsUser: 10001, fsGroup: 10001,
                         seccompProfile: { type: RuntimeDefault } }
      containers:
        - name: bbd
          image: ghcr.io/acme/blackboard-mcp:1.0.0
          args: ["serve","--http","--bind","0.0.0.0:8787",
                 "--store","postgres","--artifacts","s3"]
          ports: [{ containerPort: 8787 }]
          env:
            - { name: BB_PG_DSN,   valueFrom: { secretKeyRef: { name: bb-pg,  key: dsn } } }
            - { name: BB_S3_BUCKET, value: bb-artifacts }
            - { name: BB_JWT_JWKS_URL, value: "http://bb-issuer.bb-acme-audit.svc/.well-known/jwks.json" }
            - { name: BB_MAX_BUDGET_TOKENS, value: "8000" }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          resources:
            requests: { cpu: 200m, memory: 256Mi }
            limits:   { cpu: "1",  memory: 1Gi }
          readinessProbe: { httpGet: { path: /healthz, port: 8787 }, periodSeconds: 5 }
          livenessProbe:  { httpGet: { path: /livez,   port: 8787 }, periodSeconds: 15 }
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: bb-gateway, namespace: bb-acme-audit }
spec: { minAvailable: 1, selector: { matchLabels: { app: bb-gateway } } }
```

**Worker autoscaling on board depth (this is the good part)**
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata: { name: bb-worker, namespace: bb-acme-audit }
spec:
  maxReplicaCount: 12
  pollingInterval: 10
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc:9090
        query: sum(blackboard_tasks{workspace="acme-audit",state="ready"})
        threshold: "1"
  jobTargetRef:
    template:
      spec:
        restartPolicy: Never
        containers:
          - name: worker
            image: ghcr.io/acme/agent-worker:1.0.0
            env:
              - { name: BB_URL,  value: "http://bb-gateway:8787/mcp" }
              - { name: BB_TOKEN, valueFrom: { secretKeyRef: { name: bb-worker-grant, key: token } } }
              - { name: BB_ROLE, value: worker }
            resources: { requests: { cpu: 250m, memory: 512Mi }, limits: { cpu: "2", memory: 2Gi } }
            securityContext: { readOnlyRootFilesystem: true, allowPrivilegeEscalation: false,
                               runAsNonRoot: true, capabilities: { drop: ["ALL"] } }
```
The queue depth *is* the autoscaling signal — no separate broker to scale on (D11). Workers are ephemeral Jobs: they claim, execute, complete, exit. A crashed pod's lease expires and the task is re-claimed by the next one. This is the cluster-scale expression of D5.

**Postgres (CloudNativePG)**
```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata: { name: bb-pg, namespace: bb-acme-audit }
spec:
  instances: 3
  storage: { size: 20Gi }
  postgresql: { parameters: { max_connections: "200", shared_buffers: "512MB" } }
  backup: { barmanObjectStore: { destinationPath: s3://bb-backups/acme-audit } }
```

## Auth in cluster (D10)
- An issuer service (or your existing OIDC IdP) mints short-lived JWTs: `{sub: agent_id, ws, topics[], caps[], exp}`.
- The gateway verifies against JWKS and enforces `topic_globs` on **every** call — no trust in the agent's prompt.
- Planner tokens: `caps=[read,write,link,claim,contest]`, `topics=["**"]`, TTL 1h.
- Worker tokens: `caps=[read,write,claim]`, `topics=["tasks/<lane>/**","domain.<x>/**"]`, TTL 15m, minted per Job.
- Rotation: tokens are short-lived by design; revocation is a `grant` row delete.

## Multi-tenancy
- **Namespace per workspace** (strong: separate NetworkPolicy, quota, RBAC) for distinct customers/engagements.
- **Row-level `workspace` scoping in one namespace** (light) for many runs by one team. Gateway enforces `workspace` from the token claim; never from a request parameter.
- ResourceQuota + LimitRange per namespace so a runaway fan-out cannot starve the cluster.

## Observability (feeds the benchmark, `docs/06-benchmarks.md`)
Prometheus metrics exported by the gateway:
Namespace `blackboard_`, matching the spelled-out tool names. Prometheus suffix conventions observed: `_total` only on counters, `_seconds` on latency histograms, `_bytes` on size gauges, and bare names on gauges.

```
# [L0] --------------------------------------------------------------------
blackboard_entries{workspace,topic,kind,status}              gauge
blackboard_workspace_bytes{workspace}                        gauge
blackboard_read_tokens_total{workspace,agent,role}           counter
blackboard_write_tokens_total{workspace,agent,role}          counter
blackboard_budget_truncations_total{workspace,tool}          counter
blackboard_request_duration_seconds{tool}                    histogram
blackboard_cas_conflicts_total{workspace}                    counter
blackboard_artifact_bytes{workspace}                         gauge

# [L2] --------------------------------------------------------------------
blackboard_tasks{workspace,topic,state}                      gauge   state=ready|leased|done|failed
blackboard_claim_latency_seconds{workspace}                  histogram
blackboard_lease_expired_total{workspace}                    counter  # coordination failures

# [L3] --------------------------------------------------------------------
blackboard_trust{workspace,kind}                             histogram
blackboard_contested_total{workspace}                        counter
blackboard_board_health{workspace}                           gauge
```

Task state is a **label**, not four metric names — one series family instead of four, and KEDA/Grafana select with `state="ready"`.
OpenTelemetry: one trace per task with `workspace/topic/task_id`; the planner's span is the parent, worker spans are children → the DAG is directly visible in Tempo/Jaeger. Grafana dashboard ships with the chart: token spend per role, parallel efficiency, trust distribution, queue depth vs worker count.

## Rollout
```
Helm: helm install bb ./charts/blackboard -n bb-acme-audit \
  --set store=postgres --set artifacts.s3.bucket=bb-artifacts --set gateway.replicas=2
```
Chart values expose exactly the knobs that differ between local and cloud: `store`, `artifacts`, `auth.mode`, `gateway.replicas`, `compaction.enabled`, `budget.maxTokens`. Everything else is identical to the laptop.

## Cost & scaling notes
- Gateway is I/O bound and cheap: 2 replicas handle hundreds of req/s; scale on CPU, not on agent count.
- The expensive resource is **model tokens**, not the cluster. Autoscale workers on queue depth, but cap `maxReplicaCount` — unbounded fan-out is an unbounded bill. Enforce a per-workspace token budget in the gateway (`BB_MAX_BUDGET_TOKENS` and a workspace-level cumulative cap that returns `429 BUDGET_EXHAUSTED`).
- Artifacts dominate storage; lifecycle-expire the S3 prefix at 30 days, keep digests forever (they are tiny).
