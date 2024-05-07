#!/bin/bash
# Move all cni bin and other files mapped to tmpfs
cp -r -a /opt/cni/bin/* /cni-bin/
rm -rf /containerd/*
rsync -azh --stats --exclude="io.containerd.snapshotter.v1.overlayfs" /var/lib/containerd/ /containerd/
ls -la /var/lib/containerd/
ls -la /containerd/
du -h --max-depth=0 /var/lib/containerd
du -h --max-depth=0 /containerd
#cp -r -a /var/lib/kubelet/* /kubelet/