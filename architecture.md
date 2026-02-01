# Architecture & Design Decisions

## SSL/TLS & Persistence Strategy

### Context
This infrastructure uses a **Single-Node** architecture on Hetzner Cloud.
- **Compute:** Ephemeral. The server instance can be replaced (swapped) at any time. This wipes the OS disk.
- **Storage:** Persistent. A 50GB Volume is attached to the instance and survives replacements.
- **Networking:** Static. A Primary IP is assigned to ensure the address survives server replacements.
- **Kubernetes:** K3s (lightweight Kubernetes).
- **GitOps:** ArgoCD manages all application workloads.

### Storage Architecture: The "One Disk" Strategy
Instead of creating many small cloud volumes, we attach one large 50GB volume to the node.

1.  **Mounting:** We disable Hetzner's "automount" and use `cloud-init`'s standard `mounts:` directive to mount the volume directly to `/data`.
2.  **Kubernetes Storage (PVCs):**
    - We utilize the K3s bundled `local-path-provisioner`.
    - We configure this provisioner to store data in `/data/k3s-storage` instead of the ephemeral OS disk.

#### Decision: Default Persistence
We explicitly reconfigured the **default** `local-path` storage class to use the persistent volume (`/data`).
- **Reasoning:** In this single-node setup, accidental data loss is a higher risk than storage clutter. Ephemeral needs use `emptyDir`.

### SSL/TLS Strategy (Traefik Native)
To prevent Let's Encrypt rate limits during instance swaps:
1.  **Configuration:** Traefik is configured via `HelmChartConfig` to use a HostPath mount.
2.  **Mount Path:** The host volume `/data` is mounted to `/mnt/data` inside the Traefik container (avoiding collisions with chart defaults).
3.  **Persistence:** ACME certificates are stored at `/mnt/data/traefik/acme.json`.

## Lifecycle & Data Consistency

### Graceful Shutdown Sequence
To prevent data corruption on the persistent volume, we enforce a strict teardown order using Pulumi dependencies and remote commands:
1.  **Stop K3s:** `systemctl stop k3s` (stops all writes).
2.  **Unmount Volume:** `umount /data` (ensures filesystem consistency).
3.  **Detach Volume:** API call to detach the volume.
4.  **Delete Server:** API call to destroy the VM.

## GitOps & Bootstrapping

### The "App of Apps" Bootstrap
The cluster follows a recursive GitOps pattern (App of Apps) for zero-touch recovery:
1.  **ArgoCD Installation:** Installed via K3s Helm Controller.
2.  **Root Application:** A single "Root" `Application` manifest is inlined into `cloud-init`. This manifest points to the `cosmos/argocd/apps` directory in Git.
3.  **Authentication:** A GitHub PAT (Personal Access Token) is injected via `cloud-init` as a Kubernetes Secret. This allows ArgoCD to authenticate with the repository for both reading and writing (Image Updater).
4.  **Self-Assembly:** As soon as ArgoCD is healthy, it applies the Root App, which then discovers and deploys all other applications defined in the repository.

### Handling CRD Race Conditions (The "Chicken and Egg" Problem)
A known limitation of the GitOps bootstrap process is the **CRD Race Condition**:
- **Scenario:** The `root-app` attempts to deploy the `kube-prometheus-stack` (which installs the `ServiceMonitor` CRD) AND a custom `ServiceMonitor` resource (e.g., for Traefik) in the same sync operation.
- **Problem:** ArgoCD performs a dry-run validation on all resources before applying. Since the `ServiceMonitor` CRD does not exist yet (the stack hasn't installed it), the validation fails for the custom resource, aborting the entire sync.
- **Solution:** We explicitly configure the `root-app` with the sync option `SkipDryRunOnMissingResource=true`.
    - **Mechanism:** ArgoCD skips the dry-run validation for resources whose CRDs are missing.
    - **Outcome:** The sync proceeds, `kube-prometheus-stack` installs the CRDs, and the custom `ServiceMonitor` resource is applied successfully (either in the same pass or on the immediate next retry/self-heal cycle).
    - **Expectation:** It is **expected** for the first sync attempt to show a transient error or warning regarding the missing CRD, which resolves itself automatically as the stack installs.

### Image Lifecycle (ArgoCD Image Updater)
To achieve fully automated deployments, we utilize **ArgoCD Image Updater**:
- **Monitoring:** It polls GHCR for new tags matching a specific strategy (e.g., `numeric` for Unix timestamps).
- **Automation:** When a newer image is detected, it automatically updates the Kubernetes manifest.
- **Write-back:** It commits the new image tag directly back to the Git repository, ensuring the source of truth is always up to date.

## Monitoring Architecture

### The "Port 9100" Conflict (Traefik vs. Node Exporter)
A specific conflict exists in the K3s ecosystem when enabling metrics:
1.  **Node Exporter:** Runs as a DaemonSet with `hostNetwork: true`. It binds to **port 9100** on the host to export hardware metrics.
2.  **Traefik:** Runs as a Service with type `LoadBalancer` (via Klipper ServiceLB). If configured with default metrics settings, it *also* attempts to listen on **port 9100** on the host interface.
3.  **Conflict:** Since two processes cannot bind to the same host port, Node Exporter fails to schedule (Pending state) if Traefik starts first.

**Resolution:**
We explicitly configure Traefik to expose metrics on **port 9101** (both in the container arguments and the Service definition).
- **Container:** `--entryPoints.metrics.address=:9101/tcp`
- **Service:** `port: 9101` mapping to `targetPort: metrics`

**Security:**
Both ports 9100 (Node Exporter) and 9101 (Traefik Metrics) are blocked from the public internet via the Hetzner Cloud Firewall, ensuring metrics are only accessible internally by the Prometheus scraper.

## Design Decisions

### Why not Cert-Manager?
Traefik's file-based approach coupled with our persistent volume is simpler and more robust for this specific single-node architecture. It avoids the need for complex etcd/sqlite database backup/restore logic to preserve certificates.

### Why GitHub PAT over SSH?
Using a GitHub PAT for repository authentication is simpler to manage in both local and CI environments. It provides a unified credential for both GitOps (ArgoCD) and Image Lifecycle management (Image Updater write-back) without the overhead of SSH key management.

## Future Optimizations (Ideas)

1.  **ArgoCD UI Exposure (Completed):**
    - Expose the ArgoCD dashboard via Ingress with automatic HTTP-to-HTTPS redirection.

2.  **Pre-baked Image (Packer):**
    - **Concept:** Pre-install K3s, Helm, and ArgoCD binaries/images into a custom Hetzner snapshot.
    - **Benefit:** Drastically reduces bootstrap time (no downloads/installs on boot). Server comes up "ready".

3.  **K3s Airgap / Pre-loading:**
    - **Concept:** Host K3s binaries and airgap image archives on the persistent volume or upload them via Pulumi during provisioning.
    - **Benefit:** Removes dependency on external internet speed/availability for the K3s installation phase.

3.  **Parallel Image Pulling:**
    - **Concept:** Configure `cloud-init` to pre-pull large docker images (like ArgoCD core components) in the background while K3s installs.
    - **Benefit:** Reduces the "ContainerCreating" wait time after K3s starts.

4.  **Resource Scaling:**
    - **Concept:** Temporarily provision a larger instance type for the initial bootstrap/sync, then resize down (requires stopping) or just use a larger baseline instance.
    - **Benefit:** Faster CPU processing for startup tasks (ArgoCD controller startup, initial reconciliations).