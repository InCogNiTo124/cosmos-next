"""A Python Pulumi program"""

import os
import pulumi_hcloud as hcloud
import pulumi_command as command
import pulumi
import pathlib
from enum import Enum

class LetsEncryptEnv(Enum):
    STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
    PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"

# 1. Create Volume (Independent)
# We disable automount here/in attachment because we handle it via cloud-init 'mounts'
volume = hcloud.Volume(
    "data-volume",
    size=50,
    format="ext4",
    location="fsn1",
)

# 2. Template Cloud Init
def create_cloud_init(vol_id):
    with pathlib.Path("cloud-init.yaml").open() as file:
        template = file.read()
    
    # Read all ArgoCD application manifests
    apps_content = ""
    argocd_dir = pathlib.Path("cosmos/argocd")
    if argocd_dir.exists():
        for app_file in argocd_dir.glob("*.yaml"):
            with app_file.open() as f:
                apps_content += f"\n---\n# Source: {app_file.name}\n"
                apps_content += f.read()

    # Indent the content to match YAML structure (6 spaces)
    indented_apps = "\n".join([f"      {line}" if line.strip() else line for line in apps_content.splitlines()])

    # We inject the specific Volume ID for the /dev/disk/by-id path
    return template.replace("{{ volume_id }}", str(vol_id)) \
                   .replace("{{ email }}", "msmetko@msmetko.xyz") \
                   .replace("{{ ca_server }}", LetsEncryptEnv.STAGING.value) \
                   .replace("{{ argocd_apps }}", indented_apps)

cloud_init_data = volume.id.apply(create_cloud_init)

ssh_key = hcloud.SshKey("ARIES", public_key=os.environ.get("ARIES_PUB"))

# Create Static IP
static_ip = hcloud.PrimaryIp(
    "static-ip",
    location="fsn1",
    type="ipv4",
    assignee_type="server",
    auto_delete=False,
)

# 3. Define server
test_server = hcloud.Server(
    "test-server",
    location="fsn1",
    public_nets=[hcloud.ServerPublicNetArgs(
        ipv4_enabled=True,
        ipv4=static_ip.id,
        ipv6_enabled=False
    )],
    ssh_keys=[ssh_key.id],
    server_type="cx33",
    image="ubuntu-24.04",
    user_data=cloud_init_data,
    opts=pulumi.ResourceOptions(delete_before_replace=True),
)

# 4. Attach Volume
# automount=False because we used 'mounts' in cloud-init
volume_attachment = hcloud.VolumeAttachment(
    "data-volume-attachment",
    server_id=test_server.id,
    volume_id=volume.id,
    automount=False,
)

connection = command.remote.ConnectionArgs(
    host=test_server.ipv4_address, user="root", private_key=os.environ.get("ARIES")
)

# Lifecycle Management:
# Dependencies force Creation Order: Attachment -> Unmount Resource -> Shutdown Resource
# Destruction Order (Reverse): Shutdown Resource -> Unmount Resource -> Attachment

# 1. Unmount Volume (Ensures data consistency before detach)
unmount_volume = command.remote.Command(
    "unmount-volume",
    connection=connection,
    create="ls -d /data", # Verify mount exists on create
    delete="umount /data",
    opts=pulumi.ResourceOptions(depends_on=[volume_attachment]),
)

# 2. Graceful shutdown of services
shutdown_k3s = command.remote.Command(
    "shutdown-k3s",
    connection=connection,
    delete="systemctl stop k3s",
    opts=pulumi.ResourceOptions(depends_on=[unmount_volume]),
)

pulumi.export("ip", test_server.ipv4_address)
