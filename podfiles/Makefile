SHELL := /bin/bash

.PHONY: build
build: pinger

.PHONY: pinger
pinger:
	docker build -f Dockerfile.pinger -t pinger:v1 .
	docker build -f Dockerfile_v2.pinger -t pinger:v2 .
	docker save -o ./archives/pinger.tar pinger:v1
	docker save -o ./archives/pinger_v2.tar pinger:v2