from enum import Enum
import json
from reckon.topologies.simple import SimpleTopologyProvider
from reckon.topologies.wan import WanTopologyProvider
from reckon.topologies.simple_k8s import SimpleKubeTopologyProvider

import reckon.reckon_types as t


class TopologyType(Enum):
    Simple = "simple"
    Simple_K8s = "simple_k8s"
    Wan = "wan"

    def __str__(self):
        return self.value


def register_topo_args(parser):
    topo_group = parser.add_argument_group("topologies")

    topo_group.add_argument("topo_type", type=TopologyType, choices=list(TopologyType))

    topo_group.add_argument(
        "--number-nodes",
        type=int,
        default=3,
    )

    topo_group.add_argument(
        "--number-clients",
        type=int,
        default=1,
    )

    topo_group.add_argument(
        "--link-loss",
        type=float,
        default=0,
    )

    topo_group.add_argument(
        "--link-jitter",
        type=float,
        default=0,
    )

    topo_group.add_argument(
        "--net-spec",
        type=str,
        default="[]",
        help="A JSON string describing a list of network links with their custom per-link attributes"
    )


    topo_group.add_argument("--link-latency", type=float, default=20)


def get_topology_provider(args) -> t.AbstractTopologyGenerator:
    net_spec = t.NetSpec.parse_obj(json.loads(args.net_spec))
    if args.topo_type is TopologyType.Simple:
        return SimpleTopologyProvider(
            args.number_nodes,
            args.number_clients,
            args.link_latency,
            args.link_loss,
            args.link_jitter,
            net_spec,
        )
    elif args.topo_type is TopologyType.Wan:
        return WanTopologyProvider(
            args.number_nodes,
            args.link_latency,
            args.link_loss,
            args.link_jitter,
            net_spec,
        )
    elif args.topo_type is TopologyType.Simple_K8s:
        return SimpleKubeTopologyProvider(
            args.number_nodes,
            args.number_clients,
            args.link_latency,
            args.link_loss,
            args.link_jitter,
            net_spec,
        )
    else:
        raise Exception("Not supported distribution type: " + str(args.topo_type))
