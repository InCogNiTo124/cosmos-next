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

### The "Zero-Touch" Recovery
The cluster is designed to be fully self-healing from a "blank slate" (Pulumi Up):
1.  **ArgoCD Installation:** Installed automatically via the K3s Helm Controller (`HelmChart` manifest).
2.  **App Injection:** Local ArgoCD `Application` manifests are read by Pulumi and injected via `cloud-init` into the K3s auto-deploy manifests directory.
3.  **Synchronization:** As soon as ArgoCD is healthy, it detects the injected application manifests and begins syncing the state from the GitHub repository.

## Design Decisions

### Why not Cert-Manager?
Traefik's file-based approach coupled with our persistent volume is simpler and more robust for this specific single-node architecture. It avoids the need for complex etcd/sqlite database backup/restore logic to preserve certificates.

### Why Public Repo?
Using a public repository simplifies the ArgoCD bootstrap process by removing the need for SSH key management or credential secrets during the initial "cloud-init" phase, while still allowing for full GitOps automation.

## Future Optimizations (Ideas)

1.  **Pre-baked Image (Packer):**
    - **Concept:** Pre-install K3s, Helm, and ArgoCD binaries/images into a custom Hetzner snapshot.
    - **Benefit:** Drastically reduces bootstrap time (no downloads/installs on boot). Server comes up "ready".

2.  **K3s Airgap / Pre-loading:**
    - **Concept:** Host K3s binaries and airgap image archives on the persistent volume or upload them via Pulumi during provisioning.
    - **Benefit:** Removes dependency on external internet speed/availability for the K3s installation phase.

3.  **Parallel Image Pulling:**
    - **Concept:** Configure `cloud-init` to pre-pull large docker images (like ArgoCD core components) in the background while K3s installs.
    - **Benefit:** Reduces the "ContainerCreating" wait time after K3s starts.

4.  **Resource Scaling:**
    - **Concept:** Temporarily provision a larger instance type for the initial bootstrap/sync, then resize down (requires stopping) or just use a larger baseline instance.
    - **Benefit:** Faster CPU processing for startup tasks (ArgoCD controller startup, initial reconciliations).