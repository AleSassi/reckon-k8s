from mininet.net import Containernet
from mininet.node import Controller, Host
from mininet.log import setLogLevel
from mininet.link import TCLink
import yaml
import docker

import reckon.reckon_types as t

import math

setLogLevel("info")


class SimpleKubeTopologyProvider(t.AbstractTopologyGenerator):
    def __init__(self, number_nodes, number_clients, link_latency=None, link_loss=None, link_jitter=None, link_specs: t.NetSpec | None = None):
        # Since we have a star topology we use link_latency = link_latency / 2
        per_link_latency = (
                None if not link_latency else link_latency / 2
        )
        
        per_link_jitter = (
                None if not link_jitter else math.sqrt(((link_jitter * link_latency) ** 2) / 2)
        ) if (link_jitter is not None and link_jitter > 0) else None

        # since we have 2 links, when we want the abstraction of one direct link
        # we use link_loss = 1 - sqrt(1 - L)
        per_link_loss = (
            None if not link_loss else (1 - math.sqrt(1 - link_loss / 100)) * 100
        )
        if per_link_loss == 0:
            per_link_loss = None
        super().__init__(number_nodes, number_clients, per_link_latency, per_link_loss, per_link_jitter, link_specs)

    def add_switch(self):
        name = "s%s" % str(self.switch_num + 1)
        self.switch_num += 1
        return self.net.addSwitch(name)

    def add_client(self) -> Host:
        name = "mc%s" % str(self.client_num + 1)
        self.client_num += 1
        return self.net.addHost(name)

    def setup(self):
        self.net = t.KuberNet(controller=Controller, link=TCLink)
        self.net.addController("c0")
        sw = self.add_switch()

        # Create the cluster and start containers
        hosts = self.net.createCluster(workers=self.number_nodes - 1)
        clients = [self.add_client() for _ in range(self.number_clients)]

        # Set up connections between nodes (with custom parameters, different for each node)
        # cp = hosts[0]
        # wn = hosts[1]
        # wn2 = hosts[2]
        # self.net.addLink(cp, sw, delay="10ms")
        # self.net.addLink(wn, sw, delay="20ms")
        # self.net.addLink(wn2, sw, delay="30ms", loss=0)
        # self.net.addLink(clients[0], sw)
        for host in hosts + clients:
            spec = self.get_link_spec(host, sw)
            self.net.addLink(host, sw, delay=None if spec.latency_ms is None else f"{spec.latency_ms}ms", loss=spec.loss_perc, jitter=None if spec.jitter_ms is None else f"{spec.jitter_ms}ms")

        self.net.start()

        return (self.net, hosts, clients)
