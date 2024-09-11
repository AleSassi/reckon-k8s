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
	-v ./goclient-compiled:/compiled:rw \
	-v /local/scratch/as3575/raspikube-results:/reckon/to_reproduce:rw \
	-v /local/scratch/as3575/reckon-results:/results:rw \
	-v /local/scratch/as3575/reckon-results/20240509171614:/reckon/partial:rw \
	-v /local/scratch/as3575/result_analyzer:/result_analyzer:rw \
	--log-driver none \
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
reckon: podfiles reckon-containernet k8s-image reckon-k8s-control reckon-k8s-worker reckon-k8s-balancer
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

.PHONY: reckon-k8s-balancer
reckon-k8s-balancer: 
	docker build -f Dockerfile.kubelbnode -t AleSassi/reckon-k8s-balancer:latest .

.PHONY: reckon-mininet
reckon-mininet: 
	docker build -f Dockerfile.mininet -t cjen1/reckon-mininet:latest .

.PHONY: etcd-image
etcd-image:
	docker build -f Dockerfile.etcd -t etcd-image .

.PHONY: k8s-image
k8s-image:
	docker build -f Dockerfile.kubernetes -t k8s-image .
