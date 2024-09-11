from mininet.net import Containernet
from mininet.node import Controller, Host, OVSSwitch
from mininet.log import setLogLevel
from mininet.link import TCLink
import yaml
import docker

import reckon.reckon_types as t

import math

setLogLevel("info")


class RegionHAKubeTopologyProvider(t.AbstractTopologyGenerator):
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
        return self.net.addSwitch(name, cls=OVSSwitch, failMode='standalone', stp=True)

    def add_client(self) -> Host:
        name = "mc%s" % str(self.client_num + 1)
        self.client_num += 1
        return self.net.addHost(name)

    def setup(self):
        assert(self.number_nodes > 3)
        self.net = t.KuberNet(controller=Controller, link=TCLink)
        self.net.addController("c0")
        sw = self.add_switch()
        regional_sws: list[t.MininetHost] = []

        num_regions = 3
        num_controllers = 3
        for _ in range(num_regions):
            regional_switch = self.add_switch()
            spec = self.get_link_spec(regional_switch, sw)
            self.net.delLinkBetween(regional_switch, sw, allLinks=True) # Ensure no links between the two nodes exist
            self.net.addLink(regional_switch, sw, delay=None if spec.latency_ms is None else f"{spec.latency_ms}ms", loss=spec.loss_perc, jitter=None if spec.jitter_ms is None else f"{spec.jitter_ms}ms")
            regional_sws.append(regional_switch)
        spec = self.get_link_spec(regional_sws[1], regional_sws[2])
        self.net.delLinkBetween(regional_sws[1], regional_sws[2], allLinks=True) # Ensure no links between the two nodes exist
        self.net.addLink(regional_sws[1], regional_sws[2], delay=None if spec.latency_ms is None else f"{spec.latency_ms}ms", loss=spec.loss_perc, jitter=None if spec.jitter_ms is None else f"{spec.jitter_ms}ms")
        
        # Create the cluster and start containers
        print("Creating hosts")
        hosts = self.net.createCluster(workers=self.number_nodes - num_controllers, control=num_controllers)
        clients = [self.add_client() for _ in range(self.number_clients)]

        # Set up connections between nodes (with custom parameters, different for each node)
        # cp = hosts[0]
        # wn = hosts[1]
        # wn2 = hosts[2]
        # self.net.addLink(cp, sw, delay="10ms")
        # self.net.addLink(wn, sw, delay="20ms")
        # self.net.addLink(wn2, sw, delay="30ms", loss=0)
        # self.net.addLink(clients[0], sw)
        
        # Assume that each "region" equally splits the number of nodes in a round-robin fashion (with the LB always in region 0)
        region_idx = 0
        for host in hosts:
            regional_switch = regional_sws[region_idx]
            spec = self.get_link_spec(host, regional_switch)
            self.net.delLinkBetween(host, regional_switch, allLinks=True) # Ensure no links between the two nodes exist
            self.net.addLink(host, regional_switch, delay=None if spec.latency_ms is None else f"{spec.latency_ms}ms", loss=spec.loss_perc, jitter=None if spec.jitter_ms is None else f"{spec.jitter_ms}ms")
            if host.node_type is not t.KubeNodeType.LoadBalancer:
                region_idx = (region_idx + 1) % num_regions
        
        # Clients are connected directly to one area (the first one)
        for host in clients:
            spec = self.get_link_spec(host, regional_sws[0])
            self.net.delLinkBetween(host, regional_sws[0], allLinks=True) # Ensure no links between the two nodes exist
            self.net.addLink(host, regional_sws[0], delay=None if spec.latency_ms is None else f"{spec.latency_ms}ms", loss=spec.loss_perc, jitter=None if spec.jitter_ms is None else f"{spec.jitter_ms}ms")
        
        self.net.start()

        return (self.net, hosts, clients)
