# Project Context: cosmos-next

This document serves as a "state of the world" summary for the `cosmos-next` project, intended to help developers (and AI assistants) quickly understand the current infrastructure, configuration, and recent changes.

**Last Updated:** 2026-01-31

## 1. Project Identity
*   **Name:** `cosmos-next`
*   **Repository:** `https://github.com/InCogNiTo124/cosmos-next`
*   **Infrastructure Stack:** Pulumi (Python), Hetzner Cloud (hcloud), K3s (Lightweight Kubernetes).
*   **GitOps Engine:** ArgoCD (App of Apps pattern).

## 2. Infrastructure State
*   **Server:** `test-server` (Type: `cx33`, OS: `ubuntu-24.04`)
    *   **Public IP:** `91.98.90.218` (Static Primary IP).
    *   **SSH Access:** Key `ARIES` (private key injected via env var).
*   **Persistence:**
    *   **Volume:** 50GB Block Storage (`data-volume`).
    *   **Mount Point:** `/data` (mounted via `cloud-init`, avoiding automount).
    *   **Storage Class:** `local-path` reconfigured to use `/data/k3s-storage`.
*   **Networking:**
    *   **Ingress Controller:** Traefik (bundled with K3s).
    *   **TLS/ACME:** Let's Encrypt **Staging** (via Traefik `myresolver`).
    *   **Cert Storage:** `/data/acme.json` (hostPath mount with `600` permissions via initContainer).

## 3. GitOps Configuration
*   **Pattern:** **App of Apps**.
*   **Bootstrap:**
    *   `cloud-init.yaml` installs K3s + ArgoCD (Helm).
    *   It injects the **Root Application** manifest (`argocd-apps.yaml`) pointing to `cosmos/argocd/apps/` in Git.
    *   It injects the **Repository Secret** (`cosmos-next-repo`) using the `GH_PAT` environment variable.
*   **Image Lifecycle (ArgoCD Image Updater):**
    *   **Strategy:** `numeric` (using Unix timestamp tags).
    *   **Registry:** GHCR (`ghcr.io`).
    *   **Write-back:** Commits new image tags back to the Git repository.
    *   **Polling Interval:** 1 minute (`--interval=1m`).
*   **ArgoCD Sync Interval:** 60 seconds (via `timeout.reconciliation`).

## 4. Key File Locations
*   `__main__.py`: Pulumi infrastructure definition. Handles `cloud-init` templating (via `.format()`) and resource lifecycle.
*   `cloud-init.yaml`: The "Source of Truth" for node configuration. Contains K3s install script, Traefik config, and inlined ArgoCD manifests.
*   `cosmos/argocd/apps/`: The GitOps source directory.
    *   `argocd-image-updater.yaml`: Deploys the image updater.
    *   `argocd-ingress.yaml`: Exposes ArgoCD UI (`argo.altair.space`) with HTTP->HTTPS redirect.
    *   `personal-website-prod.yaml`: Production application manifest.
    *   `root.yaml`: (Legacy/Reference) The root application definition (now inlined in cloud-init).

## 5. Recent Changes (Feb 1, 2026)
1.  **Monitoring stack finalized**: Deployed Grafana, Prometheus, and Traefik metrics on port 9101.
2.  **K9s Config**: Added minimal configuration to show all namespaces by default.
3.  **Critical Bug Found**: Discovered that `/data` volume was NOT mounting via cloud-init `mounts` (failing silently). All data was being written to the ephemeral root disk.

## 6. Next Steps / TODOs
*   [ ] **Fix Persistence**: Move mounting logic to `runcmd` with a retry/wait loop to ensure the block device is ready before K3s starts.
*   [ ] **Switch to Production LE**: Change `LetsEncryptEnv.STAGING` to `LetsEncryptEnv.PRODUCTION` in `__main__.py`.
*   [ ] **CI/CD Pipeline**: Implement GitHub Actions to run `pulumi up`.

