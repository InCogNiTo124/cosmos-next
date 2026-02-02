# Project Context: cosmos-next

This document serves as a "state of the world" summary for the `cosmos-next` project, intended to help developers (and AI assistants) quickly understand the current infrastructure, configuration, and recent changes.

**Last Updated:** 2026-02-02

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
    *   **Mount Point:** `/data` (mounted via `runcmd` with robust wait loop).
    *   **Storage Class:** `local-path` (default) but critical applications use **Static PVs** bound to `/data/...` hostPaths.
*   **Networking:**
    *   **Ingress Controller:** Traefik (bundled with K3s, custom configured via `HelmChartConfig`).
    *   **TLS/ACME:** Let's Encrypt **Staging** (via Traefik `letsencrypt` resolver).
    *   **Cert Storage:** `/data/traefik/acme.json` (Managed via Static PV `traefik-acme-pv` + PVC).
    *   **Redirect:** Global HTTP -> HTTPS enforcement enabled.

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
    *   `argocd-ingress.yaml`: Exposes ArgoCD UI (`argo.altair.space`).
    *   `kepler-orbit.yaml`, `brachi.yaml`, `personal-blog.yaml`: Application manifests.
    *   `monitoring-storage.yaml`: Defines Static PVs for Prometheus/Alertmanager/Grafana persistence.

## 5. Recent Changes (Feb 2, 2026)
1.  **Traefik Persistence Solved:** Implemented a robust **Static PV/PVC** strategy for Traefik's ACME storage, pointing to `/data/traefik`. This resolved permissions issues and ensured certificates survive nuclear rebuilds.
2.  **Global HTTPS Redirect:** Enabled `web` -> `websecure` redirection using the new Traefik v3 syntax (`ports.web.redirections.entryPoint`).
3.  **Application Migration:** Migrated `kepler-orbit`, `brachi`, and `personal-blog` from Flux to ArgoCD.
4.  **Ingress Fixes:** Removed conflicting `cert-manager` annotations and explicit `tls` blocks from Ingress resources to let Traefik's native ACME resolver handle certificates correctly.
5.  **Verified Persistence:** Confirmed via "Nuclear Rebuild" that certificates are reused and monitoring data is preserved.

## 6. Next Steps / TODOs
*   [ ] **Switch to Production LE**: Change `LetsEncryptEnv.STAGING` to `LetsEncryptEnv.PRODUCTION` in `__main__.py`.
*   [ ] **CI/CD Pipeline**: Implement GitHub Actions to run `pulumi up` automatically.

