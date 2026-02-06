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
    opts=pulumi.ResourceOptions(protect=True),
)


config = pulumi.Config()
ss_public_cert = config.get("sealed_secrets_public_cert")
ss_private_key = config.get_secret("sealed_secrets_private_key")


# 2. Template Cloud Init
def create_cloud_init(args):
    vol_id, ss_priv, ss_pub = args
    with pathlib.Path("cloud-init.yaml").open() as file:
        template = file.read()
    
    # We inject the specific Volume ID for the /dev/disk/by-id path
    return template.format(
        volume_id=vol_id,
        email="msmetko@msmetko.xyz",
        ca_server=LetsEncryptEnv.STAGING.value,
        gh_pat=os.environ.get("GH_PAT", ""),
        ss_private_key=ss_priv,
        ss_public_cert=ss_pub
    )


cloud_init_args = pulumi.Output.all(volume.id, ss_private_key, ss_public_cert)
cloud_init_data = cloud_init_args.apply(create_cloud_init)

ssh_key = hcloud.SshKey("ARIES", public_key=os.environ.get("ARIES_PUB"))

# Create Static IP
static_ip = hcloud.PrimaryIp(
    "static-ip",
    location="fsn1",
    type="ipv4",
    assignee_type="server",
    auto_delete=False,
)

# Create Firewall
firewall = hcloud.Firewall(
    "web-firewall",
    rules=[
        hcloud.FirewallRuleArgs(
            direction="in",
            protocol="tcp",
            port="22",
            source_ips=["0.0.0.0/0", "::/0"],
        ),
        hcloud.FirewallRuleArgs(
            direction="in",
            protocol="tcp",
            port="80",
            source_ips=["0.0.0.0/0", "::/0"],
        ),
        hcloud.FirewallRuleArgs(
            direction="in",
            protocol="tcp",
            port="443",
            source_ips=["0.0.0.0/0", "::/0"],
        ),
        hcloud.FirewallRuleArgs(
            direction="in",
            protocol="icmp",
            source_ips=["0.0.0.0/0", "::/0"],
        ),
    ],
)

# 3. Define server
test_server = hcloud.Server(
    "test-server",
    location="fsn1",
    public_nets=[
        hcloud.ServerPublicNetArgs(
            ipv4_enabled=True, ipv4=static_ip.id, ipv6_enabled=False
        )
    ],
    firewall_ids=[firewall.id],
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
    create="ls -d /data",  # Verify mount exists on create
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
