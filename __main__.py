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
    
    # We inject the specific Volume ID for the /dev/disk/by-id path
    return template.replace("{{ volume_id }}", str(vol_id)) \
                   .replace("{{ email }}", "msmetko@msmetko.xyz") \
                   .replace("{{ ca_server }}", LetsEncryptEnv.STAGING.value)

cloud_init_data = volume.id.apply(create_cloud_init)

ssh_key = hcloud.SshKey("ARIES", public_key=os.environ.get("ARIES_PUB"))

# 3. Define server
test_server = hcloud.Server(
    "test-server",
    location="fsn1",
    public_nets=[hcloud.ServerPublicNetArgs(ipv4_enabled=True, ipv6_enabled=False)],
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

# Graceful shutdown command
shutdown_k3s = command.remote.Command(
    "shutdown-k3s",
    connection=connection,
    delete="systemctl stop k3s",
    opts=pulumi.ResourceOptions(depends_on=[test_server, volume_attachment]),
)

pulumi.export("ip", test_server.ipv4_address)
