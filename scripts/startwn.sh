# Join the cluster
kubeadm join --config=/kind/kubeadm.conf --skip-phases=preflight --v=6
# Load custom images
bash /archives/loadimages.sh