#!/bin/bash

for img in /archives/*.tar
do
    echo "Importing image file ${img}"
    ctr --namespace=k8s.io images import --all-platforms --digests --snapshotter=docker "${img}"
done