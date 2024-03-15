#!/bin/bash

files=("admin.conf" "pki/ca.crt" "pki/ca.key" "pki/front-proxy-ca.crt" "pki/front-proxy-ca.key" "pki/sa.pub" "pki/sa.key" "pki/etcd/ca.crt" "pki/etcd/ca.key")

for dir in /kind/nodedata/*
do
    dir=${dir%*/}
    rm -rf "${dir}/*"
    mkdir "${dir}/pki"
    mkdir "${dir}/pki/etcd"
    for file in "${files[@]}"
    do
        echo "${file}"
        cp "/etc/kubernetes/${file}" "${dir}/${file}"
    done
done

cp "/etc/kubernetes/admin.conf" "/kind/shared_files/config"