#!/bin/bash

files=("admin.conf" "pki/ca.crt" "pki/ca.key" "pki/front-proxy-ca.crt" "pki/front-proxy-ca.key" "pki/sa.pub" "pki/sa.key" "pki/etcd/ca.crt" "pki/etcd/ca.key")

for file in /kind/nodedata/*
do
    #echo "${file}"
    mv "${file}" "/etc/kubernetes/"
done