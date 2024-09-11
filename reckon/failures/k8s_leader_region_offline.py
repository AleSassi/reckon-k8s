import logging
import reckon.reckon_types as t
from typing import Union
from typing_extensions import Literal
from reckon.systems import Kubernetes

class Shared:
    def __init__(self, partitioned=[]):
        self._partitioned = partitioned

    @property
    def partitioned(self):
        return self._partitioned

    @partitioned.setter
    def partitioned(self, value):
        self._partitioned = value


class LeaderRegionOfflineFault(t.AbstractFault):
    def __init__(
        self,
        kind: Union[Literal["create"], Literal["remove"]],
        shared: Shared,
        system,
        cluster: list[t.KubeNode],
    ):
        assert(type(system) is Kubernetes)
        self._kind = kind
        self._shared = shared
        self.system = system
        self.cluster = cluster

    def initiate_partition(self):
        leader = self.system.get_leader(self.cluster)
        leader_index = [h for h in self.cluster if h.node_type is t.KubeNodeType.ControlPlane].index(leader)
        assoc_worker = [h for h in self.cluster if h.node_type is t.KubeNodeType.Worker][leader_index]
        unreachable_nodes = [h for h in self.cluster if not h == leader and not h == assoc_worker]
        for unreachable_node in unreachable_nodes:
            logging.debug("Partitioning %s from %s", leader.name, unreachable_node.name)
            self.partition(leader, unreachable_node)
            self.partition(unreachable_node, leader)
            logging.debug("Partitioning %s from %s", assoc_worker.name, unreachable_node.name)
            self.partition(assoc_worker, unreachable_node)
            self.partition(unreachable_node, assoc_worker)

    def partition(self, host, remote):
        cmd = "iptables -I OUTPUT -d {0} -j DROP".format(remote.IP())
        logging.debug("cmd on {0} = {1}".format(host.name, cmd))
        host.cmd(cmd, shell=True)
        self._shared.partitioned.append(host)

    def remove_partition(self):
        cmd = "iptables -D OUTPUT 1"
        for host in self._shared.partitioned:
            host.cmd(cmd, shell=True)
            logging.debug("cmd on {0} = {1}".format(host.name, cmd))
        self._shared.partitioned = []

    def apply_fault(self):
        if self._kind == "create":
            self.initiate_partition()
        elif self._kind == "remove":
            self.remove_partition()


class LeaderRegionOfflineFaultFailure(t.AbstractFailureGenerator):
    def get_failures(self, cluster, system, restarters, stoppers):
        shared = Shared()
        return [
                t.NullFault(),
                LeaderRegionOfflineFault("create", shared, system, cluster),
                LeaderRegionOfflineFault("remove", shared, system, cluster),
                t.NullFault(),
        ]
