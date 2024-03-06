#!/bin/bash

rm -rf /etc/kubernetes/*
# Start the control plane
kubeadm init --skip-phases=preflight --config=/kind/kubeadm.conf --skip-token-print --v=6
# Update the Kubectl config path
export KUBECONFIG=/etc/kubernetes/admin.conf
# Install CNI
kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/patched-cni.conf
# Install storage class
kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/default-storage.yaml