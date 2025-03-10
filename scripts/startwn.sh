# Join the cluster
bash /kind/restoreconfigs.sh
#cat /kind/kubeadm.conf
#ls -la /etc/kubernetes
kubeadm join --config=/kind/kubeadm.conf --skip-phases=preflight --v=6
# Load custom images
bash /archives/loadimages.sh