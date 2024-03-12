rm -rf /etc/kubernetes/*
# Start the control plane
kubeadm init --skip-phases=preflight --config=/kind/kubeadm.conf --skip-token-print --v=6
# Update the Kubectl config path
#export KUBECONFIG=/etc/kubernetes/admin.conf
mkdir -p $HOME/.kube
cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config
# Copy the config files needed by workers to their volumes
bash /kind/copyconfigs.sh
# Install CNI
kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/patched-cni.conf
# Install storage class
kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/default-storage.yaml
# Load custom mages
bash /archives/loadimages.sh