# Join the cluster
bash /kind/restoreconfigs.sh
#cat /kind/kubeadm.conf
#ls -la /etc/kubernetes
kubeadm join --config=/kind/kubeadm.conf --skip-phases=preflight --v=6
# Copy etcd config to log
cp /kind/etcd.conf /etc/kubernetes/manifests/etcd.yaml # No need to redeploy - will be done automatically
# Load custom images
bash /archives/loadimages.sh