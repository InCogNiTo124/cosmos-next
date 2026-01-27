# Cosmos Next

This project provisions a single-node K3s cluster on Hetzner Cloud using Pulumi with Python.

## Infrastructure

- **Server:** Ubuntu 24.04 (Type: cx33, Location: fsn1)
- **Storage:** 50GB Volume (ext4, automounted)
- **Kubernetes:** K3s installed via cloud-init
- **Utilities:** `k9s` installed via cloud-init

## Prerequisites

Ensure the following environment variables are set:

- `HCLOUD_TOKEN`: Your Hetzner Cloud API token.
- `ARIES_PUB`: The public SSH key content for the server.
- `ARIES`: The private SSH key content (used by Pulumi to establish connections for remote commands).

## Usage

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Deploy:**
   ```bash
   pulumi up
   ```

3. **Access:**
   SSH into the server using your `ARIES` key.
   ```bash
   ssh -i <path-to-private-key> root@<server-ip>
   ```
   *Note: `KUBECONFIG` is set globally in `/etc/environment`, so `kubectl` and `k9s` work out of the box.*

## Features

- **Graceful Shutdown:** Includes logic to drain and stop K3s before server deletion.
- **Volume Persistence:** The 50GB data volume persists across server replacements (instance swaps).
