# Architecture & Design Decisions

## SSL/TLS & Persistence Strategy

### Context
This infrastructure uses a **Single-Node** architecture on Hetzner Cloud.
- **Compute:** Ephemeral. The server instance can be replaced (swapped) at any time to upgrade the OS or change specifications. This wipes the OS disk.
- **Storage:** Persistent. A 50GB Volume is attached to the instance and survives replacements.
- **Kubernetes:** K3s (lightweight Kubernetes).

### Storage Architecture: The "One Disk" Strategy
Instead of creating many small cloud volumes (which costs more and hits limits), we attach one large 50GB volume to the node.

1.  **Mounting:** We disable Hetzner's "automount" and use `cloud-init`'s standard `mounts:` directive to mount the volume directly to `/data`.
2.  **Kubernetes Storage (PVCs):**
    - We utilize the K3s bundled `local-path-provisioner`.
    - We configure this provisioner to store data in `/data/k3s-storage` instead of the ephemeral OS disk.
    - **Result:** Applications (Prometheus, Grafana, etc.) request standard PVCs. Under the hood, they get persistent directories on the 50GB volume.

#### Decision: Default Persistence
We explicitly reconfigured the **default** `local-path` storage class to use the persistent volume (`/data`).
- **Alternative Considered:** Creating a separate `persistent` storage class and leaving `default` as ephemeral (OS disk).
- **Reasoning:** In this single-node setup, accidental data loss (forgetting to set `storageClassName: persistent`) is a higher risk than storage clutter.
- **Ephemeral Needs:** Workloads that truly need ephemeral storage (caches, temp files) should use standard Kubernetes `emptyDir` volumes, which naturally map to the OS disk and are cleaned up automatically.

### SSL/TLS Strategy (Traefik Native)
To prevent Let's Encrypt rate limits during instance swaps:
1.  **Configuration:** Traefik (bundled with K3s) is configured to use a specific HostPath: `/data/traefik/acme.json`.
2.  **Workflow:**
    - Traefik stores certificates on the persistent volume.
    - On instance swap, the new Traefik instance picks up the existing certificates without contacting Let's Encrypt.

## Design Decisions

### Why not Cert-Manager?
Cert-Manager stores secrets in the K3s database (etcd/sqlite). Since our single-node DB is on the ephemeral OS disk, we would lose the certs on every swap unless we implemented complex DB backup/restore logic. Traefik's file-based approach coupled with our persistent volume is simpler and more robust for this specific single-node architecture.
