#!/bin/bash
# copied from https://github.com/mininet/mininet/pull/968

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

sudo mn -c --switch lxbr,stp=1

"$@"
EXITCODE=$?

service openvswitch-switch stop
echo "*** Exiting Container..."

exit $EXITCODE
