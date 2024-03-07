SHELL := /bin/bash

.PHONY: build
build: pinger

.PHONY: pinger
pinger:
	docker build -f Dockerfile.pinger -t pinger:v1 .
	docker save -o ./archives/pinger.tar pinger:v1