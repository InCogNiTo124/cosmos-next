"""A Python Pulumi program"""

import os
import pulumi_hcloud as hcloud
import pulumi_command as command
import pulumi
import pathlib

with pathlib.Path("cloud-init.yaml").open() as file:
    CLOUD_INIT = file.read()

ssh_key = hcloud.SshKey("ARIES", public_key=os.environ.get("ARIES_PUB"))

## Define server
test_server = hcloud.Server(
    "test-server",
    location="fsn1",
    public_nets=[hcloud.ServerPublicNetArgs(ipv4_enabled=True, ipv6_enabled=False)],
    ssh_keys=[ssh_key.id],
    server_type="cx33",
    image="ubuntu-24.04",
    user_data=CLOUD_INIT,
    opts=pulumi.ResourceOptions(delete_before_replace=True),
)

volume = hcloud.Volume(
    "data-volume",
    size=50,
    server_id=test_server.id,
    automount=True,
    format="ext4",
)

connection = command.remote.ConnectionArgs(
    host=test_server.ipv4_address, user="root", private_key=os.environ.get("ARIES")
)

# Graceful shutdown command
shutdown_k3s = command.remote.Command(
    "shutdown-k3s",
    connection=connection,
    delete="systemctl stop k3s",
    opts=pulumi.ResourceOptions(depends_on=[test_server]),
)
