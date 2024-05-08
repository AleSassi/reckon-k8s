from datetime import datetime
from enum import Enum
import subprocess
import logging
import time
import yaml

import reckon.reckon_types as t


class Go(t.AbstractClient):
    client_path = "/root/reckon/systems/kubernetes/clients/simple/client"

    def __init__(self, args):
        self.ncpr = args.new_client_per_request

    def cmd(self, ips, client_id) -> str:
        return "{client_path} --id={client_id} --ncpr={ncpr} --kubeconfig=/files/kubefiles/config".format(
            client_path=self.client_path,
            client_id=str(client_id),
            ncpr=self.ncpr,
        )


class ClientType(Enum):
    Go = "go"

    def __str__(self):
        return self.value


class Kubernetes(t.AbstractSystem):
    binary_path = ""
    additional_flags = ""

    def get_client(self, args):
        if args.client == str(ClientType.Go) or args.client is None:
            return Go(args)
        else:
            raise Exception("Not supported client type: " + str(args.client))
        
    def add_stderr_logging(self, cmd: str, tag: str, dir: str = "/results/logs"):
        time = self.creation_time
        log = dir
        return f"{cmd} 2> {log}/{time}_{tag}.err"

    def add_stdout_logging(self, cmd: str, tag: str, dir: str = "/results/logs", verbose: bool=False):
        time = self.creation_time
        log = dir
        return f"{cmd} | tee {log}/{time}_{tag}.out" if verbose else f"{cmd} > {log}/{time}_{tag}.out"

    def start_nodes(self, cluster: list[t.KubeNode]):
        restarters = {}
        stoppers = {}
        killers = {}
        
        kubecluster: list[t.KubeNode] = cluster
        # Thanks to how the cluster list is built, the first node is always either:
        # - The one and only control plane
        # - The load balancer
        k8s_api_server_endpoint = kubecluster[0].endpoint
        # Now that interfaces are up, we can start our Kubernetes cluster
        i = 0
        cluster_main_cp_boostrapped = False
        for kubenode in kubecluster:
            tag = self.get_node_tag(kubenode)

            if kubenode.node_type is t.KubeNodeType.LoadBalancer:
                # Generate the config and commands for haproxy
                config_str = ""
                with open("/root/files/conf/haproxyconf.template", "r") as conf_template_file:
                    config_str = conf_template_file.read()
                    # Append the server config for CPs
                    for node in kubecluster:
                        if node.node_type is t.KubeNodeType.ControlPlane:
                            config_str += f"  server {node.k8s_name} {node.ip_addr} check check-ssl verify none resolvers docker resolve-prefer ipv4\n"
                
                # Write the config to the container
                kubenode.cmd(f"echo '{config_str}' > /usr/local/etc/haproxy/haproxy.cfg")
                start_cmd = "kill -s HUP 1"
            else:
                # Generate the kubeadm config file for the node
                config_str = ""
                with open("/root/files/conf/kubeadmconfig.template", "r") as conf_template_file:
                    conf_template_gen = yaml.safe_load_all(conf_template_file)
                    conf_template = list(conf_template_gen)
                    conf_template[0]["controlPlaneEndpoint"] = k8s_api_server_endpoint
                    #conf_template[0]["controllerManager"]["extraArgs"]["enable-hostpath-provisioner"] = "true"
                    conf_template[1]["localAPIEndpoint"]["advertiseAddress"] = kubenode.ip_addr
                    conf_template[1]["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = kubenode.ip_addr
                    conf_template[1]["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += kubenode.k8s_name
                    conf_template[2]["discovery"]["bootstrapToken"]["apiServerEndpoint"] = k8s_api_server_endpoint
                    conf_template[2]["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = kubenode.ip_addr
                    conf_template[2]["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += kubenode.k8s_name
                    if kubenode.is_control:
                        conf_template[2]["controlPlane"] = {
                            "localAPIEndpoint": {
                                "advertiseAddress": kubenode.endpoint, # The advertise address for THIS control plane node
                                "bindPort": 6443
                            }
                        }
                    config_str: str = yaml.safe_dump_all(conf_template, default_style='"')
                
                kubenode.cmd(f"echo '{config_str}' > /kind/kubeadm.conf")
                kubenode.cmd("cat /kind/kubeadm.conf", verbose=True)
                kubenode.cmd(f"mkdir -p /results/logs/node_{i}")

                # Perform node-specific things and start the cluster
                start_cmd = ""
                if kubenode.node_type is t.KubeNodeType.ControlPlane and not cluster_main_cp_boostrapped:
                    # Prepare files for installation of CNI
                    with open("/root/files/conf/cni.template", "r") as cni_conf_template:
                        cni_template_gen = yaml.safe_load_all(cni_conf_template)
                        cni_template = list(cni_template_gen)
                        cni_template[3]["spec"]["template"]["spec"]["containers"][0]["env"].append({
                            "name": "CONTROL_PLANE_ENDPOINT",
                            "value": k8s_api_server_endpoint
                        })
                        # Remove a trailing None
                        cni_template.pop()
                        cni_template_str: str = yaml.safe_dump_all(cni_template)
                        kubenode.cmd(f"echo '{cni_template_str}' > /kind/manifests/patched-cni.conf")
                    # Start the Control Plane
                    start_cmd = "source /kind/startcp.sh"
                    cluster_main_cp_boostrapped = True
                else:
                    # Join all worker nodes/secondary CPs!
                    start_cmd = "source /kind/startwn.sh"

                start_cmd = self.add_stderr_logging(start_cmd, tag + ".log", dir=f"/results/logs/node_{i}")
                start_cmd = self.add_stdout_logging(start_cmd, tag + ".log", dir=f"/results/logs/node_{i}", verbose=True)

            logging.debug("Start cmd: " + start_cmd)
            kubenode.cmd(start_cmd, verbose=True)

            # We use the default arguemnt to capture the host variable semantically rather than lexically
            def restarter(host=kubenode, start_cmd=start_cmd, cluster=cluster):
                newHost = host.restart(cluster)
                if newHost is not None:
                    newHost.cmd(f"tcpdump -i any -w /results/logs/node_{cluster.index(newHost)}/tcpdump_restart_{datetime.now().strftime('%Y%m%d%H%M%S')}.pcap", verbose=True, detached=True)
                del host # Restarting a host creates a new one! Delete the previous one to free some memory

            stoppers[tag] = lambda host=kubenode: host.pause()
            killers[tag] = lambda host=kubenode: host.terminateAndRemove()
            restarters[tag] = lambda host=kubenode, start_cmd=start_cmd, cluster=cluster: restarter(host, start_cmd, cluster)
            i += 1

        return restarters, stoppers, killers

    def start_client(self, client, client_id, cluster) -> t.Client:
        logging.debug("starting microclient: " + str(client_id))
        tag = self.get_client_tag(client)

        cmd = self.client_class.cmd([host.IP() for host in cluster], client_id)
        cmd = self.add_stderr_logging(cmd, tag + ".log")

        logging.debug("Starting client with: " + cmd)
        sp = client.popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=True,
            bufsize=4096,
        )
        return t.Client(sp.stdin, sp.stdout, client_id)

    def parse_resp(self, resp):
        logging.debug("--------------------------------------------------")
        logging.debug(resp)
        logging.debug("--------------------------------------------------")
        endpoint_statuses = resp.split("\n")[0:-1]
        for endpoint in endpoint_statuses:
            endpoint_ip = endpoint.split(",")[0].split("://")[-1].split(":")[0]
            if endpoint.split(",")[4].strip() == "true":
                return endpoint_ip
            
    def prepare_test_start(self, cluster: t.List[t.Host]) -> t.Result | None:
        # Start tcpdump to analyze incoming K8s packets
        logging.debug("PREPARE: Preparing the cluster for the test...")
        kubecluster: list[t.KubeNode] = cluster
        submitted = float(time.time_ns()) / 1e9
        i = 0
        for c in kubecluster:
            c.cmd(f"tcpdump -i any -w /results/logs/node_{i}/tcpdump.pcap", verbose=True, detached=True)
            i += 1
        ended = float(time.time_ns()) / 1e9
        logging.debug("PREPARE: done")
        return t.Result(kind="result", t_submitted=submitted, t_result=ended, result="tcpdump started", op_kind=t.OperationKind.Other, clientid="-1", other={})

    def get_leader(self, cluster):
        return cluster[0]

    def stat(self, host: t.MininetHost) -> str:
        return ""
