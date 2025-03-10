FROM AleSassi/reckon-containernet:latest as base

WORKDIR /root

RUN apt-get update && apt-get install --no-install-recommends -yy -qq \
    build-essential \
    software-properties-common

RUN ln /usr/bin/ovs-testcontroller /usr/bin/controller

# Build dependencies
RUN apt-get update && apt-get install --no-install-recommends -yy -qq \
    autoconf \
    automake \
    libtool \
    curl \
    g++ \
    unzip \
    python-is-python3

## Add stretch backports
#RUN echo 'deb http://ftp.debian.org/debian stretch-backports main' | sudo tee /etc/apt/sources.list.d/stretch-backports.list
#RUN apt-get update && apt-get install -yy -qq \
#    openjdk-11-jdk

# Runtime dependencies
RUN python -m pip install --upgrade wheel setuptools
ADD requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt
RUN apt-get update && apt-get install --no-install-recommends -yy -qq psmisc iptables

# Test dependencies
RUN apt-get update && apt-get install --no-install-recommends -yy -qq \
    tmux \
    screen \
    strace \
    linux-tools-common \
    tcpdump \
    lsof \
    vim \
    netcat \
    locales-all \
    git

# Install Kubectl
RUN curl -LO https://dl.k8s.io/release/v1.29.2/bin/linux/arm64/kubectl
RUN install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Make directory for logs
RUN mkdir -p /results/logs
RUN mkdir -p /results/logs/kubenodes
ENV KUBECONFIG=/files/kubefiles/config

# Add built artefacts
ENV ETCD_UNSUPPORTED_ARCH=arm64
#COPY --from=etcd-image /reckon/systems/etcd reckon/systems/etcd
COPY --from=k8s-image /reckon/systems/kubernetes reckon/systems/kubernetes

# Add reckon code
ADD ./reckon ./reckon
ADD ./scripts ./scripts
ADD ./to_reproduce ./to_reproduce
ADD ./vendor ./vendor
ADD ./files ./files
ENV PYTHONPATH="/root:${PYTHONPATH}"
ENV SHELL=/bin/bash