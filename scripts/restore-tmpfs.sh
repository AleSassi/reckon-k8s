#!/bin/bash
# Move back all cni bin and other files mapped to tmpfs
mv /cni-bin/* /opt/cni/bin/
rsync -azh --stats /containerd/ /var/lib/containerd/
ls -la /var/lib/containerd/
ls -la /containerd/
du -h --max-depth=0 /var/lib/containerd
du -h --max-depth=0 /containerd
#mv /kubelet/* /var/lib/kubelet/
# Restore missing images
#bash /archives/loadimages.sh