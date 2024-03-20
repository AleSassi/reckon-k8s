SHELL := /bin/bash

.PHONY: run
run: reckon
	docker run -it --rm --pid='host' --privileged -e DISPLAY \
	--tmpfs /data \
	--network host --name reckon \
	-v /var/run/docker.sock:/var/run/docker.sock \
	-v ./files/kubernetes:/etc/kubernetes \
	-v /lib/modules:/lib/modules:ro \
	-v /var \
	-v shared_files:/files/kubefiles:rw \
	-v kubenode_results:/results/logs/kubenodes:rw \
	 cjen1/reckon:latest bash

.PHONY: tester
tester: reckon
	docker run -it --privileged -e DISPLAY \
	--tmpfs /data \
	--network host --name reckon \
	 cjen1/reckon:latest bash /root/scripts/run.sh python /root/scripts/tester.py

.PHONY:podfiles
podfiles:
	make build -C podfiles

.PHONY:reckon
reckon: podfiles reckon-containernet etcd-image k8s-image reckon-k8s-control reckon-k8s-worker
	docker build -t cjen1/reckon:latest .

.PHONY: reckon-containernet
reckon-containernet: 
	docker build -f Dockerfile.containernet -t AleSassi/reckon-containernet:latest .

.PHONY: reckon-k8s-control
reckon-k8s-control: 
	docker build -f Dockerfile.kubecpnode -t AleSassi/reckon-k8s-control:latest .

.PHONY: reckon-k8s-worker
reckon-k8s-worker: 
	docker build -f Dockerfile.kubewnode -t AleSassi/reckon-k8s-worker:latest .

.PHONY: reckon-mininet
reckon-mininet: 
	docker build -f Dockerfile.mininet -t cjen1/reckon-mininet:latest .

.PHONY: etcd-image
etcd-image:
	docker build -f Dockerfile.etcd -t etcd-image .

.PHONY: k8s-image
k8s-image:
	docker build -f Dockerfile.kubernetes -t k8s-image .