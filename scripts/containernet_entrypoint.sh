#!/bin/bash
# copied from https://github.com/containernet/containernet and https://github.com/mininet/mininet/pull/968

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

# check if docker socket is mounted
if [ ! -S /var/run/docker.sock ]; then
    echo 'Error: the Docker socket file "/var/run/docker.sock" was not found. It should be mounted as a volume.'
    exit 1
fi

sudo mn -c --switch lxbr,stp=1

echo "Welcome to Containernet running within a Docker container ..."

"$@"
EXITCODE=$?

service openvswitch-switch stop
echo "*** Exiting Container..."

exit $EXITCODE
