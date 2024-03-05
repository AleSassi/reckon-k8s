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
    config_dict: dict = {
        "control_plane": {},
        "workers": []
    }

    def __init__(self, number_nodes, number_clients, link_latency=None, link_loss=None, link_jitter=None):
        self.number_nodes = number_nodes
        self.number_clients = number_clients

        # Since we have a star topology we use link_latency = link_latency / 2
        self.per_link_latency = (
                None if not link_latency else f"{link_latency / 2}ms"
        )

        
        self.per_link_jitter = (
                None if not link_jitter else f"{math.sqrt(((link_jitter * link_latency) ** 2) / 2)}ms"
        ) if (link_jitter is not None and link_jitter > 0) else None

        # since we have 2 links, when we want the abstraction of one direct link
        # we use link_loss = 1 - sqrt(1 - L)
        self.per_link_loss = (
            None if not link_loss else (1 - math.sqrt(1 - link_loss / 100)) * 100
        )
        if self.per_link_loss == 0:
            self.per_link_loss = None

        self.switch_num = 0
        self.host_num = 0
        self.cp_num = 0
        self.worker_num = 0
        self.client_num = 0

    def add_switch(self):
        name = "s%s" % str(self.switch_num + 1)
        self.switch_num += 1
        return self.net.addSwitch(name)

    def add_control_plane(self):
        assert(self.cp_num == 0)
        name = "cp"
        ip_addr = f"10.0.0.{self.cp_num + 1}"
        self.cp_num += 1
        self.host_num += 1
        # Create the shared Docker volume
        docker.from_env().volumes.create("kubefiles_cp")
        self.config_dict["control-plane"] = {
            "name": name,
            "ip_addr": ip_addr,
            "endpoint": f"{ip_addr}:6443",
            "volume": "kubefiles_cp"
        }
    
    def add_worker_node(self):
        assert(self.cp_num > 0)
        name = f"wn{'' if self.worker_num == 0 else (self.worker_num + 1)}"
        self.worker_num += 1
        self.host_num += 1
        # Create the shared Docker volume
        docker.from_env().volumes.create(f"kubefiles_wn{self.worker_num}")
        self.config_dict["workers"].append({
            "name": name,
            "ip_addr": f"10.0.0.{255 - self.worker_num}",
            "volume": f"kubefiles_wn{self.worker_num}"
        })

    def add_client(self) -> Host:
        name = "mc%s" % str(self.client_num + 1)
        self.client_num += 1
        return self.net.addHost(name)

    def setup(self):
        self.net = t.KuberNet(controller=Controller, link=TCLink)
        self.net.addController("c0")
        sw = self.add_switch()

        hosts = []

        # Build the Kubernetes config
        self.add_control_plane()
        if self.number_nodes > 1:
            for _ in range(self.number_nodes - 1):
                self.add_worker_node()

        # Preconfigure all nodes
        for i in range(self.number_nodes):
            # Generate the kubeadm config file for the node
            is_control = i == 0
            worker_idx = i - 1
            node_info = self.config_dict["control-plane"] if is_control else self.config_dict["workers"][worker_idx]
            
            # Determine the shared folder for the node
            docker_vols = ["/lib/modules:/lib/modules:ro",
                           "/var",
                           f"kubefiles_{'cp' if is_control else 'wn'+str(worker_idx + 1)}:/etc/kubernetes:rw"]
            if is_control:
                workers: list[dict] = self.config_dict["workers"]
                i = 1
                for worker in workers:
                    docker_vols.append(f"{worker['volume']}:/kind/nodedata/wn{i}")
                    i += 1

            # Create the Node container
            kubenode = self.net.addDocker(node_info['name'],
                                            ip=node_info['ip_addr'],
                                            dimage=f"AleSassi/reckon-k8s-{'control' if is_control else 'worker'}",
                                            dcmd="/usr/local/bin/entrypoint /sbin/init && /bin/bash",
                                            volumes=docker_vols)
            hosts.append(kubenode)


        #hosts = [self.add_host() for _ in range(self.number_nodes)]
        #clients = [self.add_client() for _ in range(self.number_clients)]
        clients = []

        for host in hosts + clients:
            self.net.addLink(host, sw, delay=self.per_link_latency, loss=self.per_link_loss, jitter=self.per_link_jitter)

        self.net.start()
        
        # Now that interfaces are up, we can start our Kubernetes cluster
        for i in range(self.number_nodes):
            # Generate the kubeadm config file for the node
            is_control = i == 0
            kubenode = hosts[i]
            worker_idx = i - 1
            node_info = self.config_dict["control-plane"] if is_control else self.config_dict["workers"][worker_idx]
            config_str = ""
            with open("/root/files/conf/clusterconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["controlPlaneEndpoint"] = self.config_dict['control-plane']['endpoint']
                conf_template["controllerManager"]["extraArgs"]["enable-hostpath-provisioner"] = "true"
                config_str += yaml.dump(conf_template, default_style='"')
                config_str += "---\n"
            with open("/root/files/conf/initconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["localAPIEndpoint"]["advertiseAddress"] = node_info["ip_addr"]
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = node_info["ip_addr"]
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += node_info["name"]
                config_str += yaml.dump(conf_template)
                config_str += "---\n"
            with open("/root/files/conf/joinconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["discovery"]["bootstrapToken"]["apiServerEndpoint"] = self.config_dict['control-plane']['endpoint']
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = node_info["ip_addr"]
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += node_info["name"]
                if is_control:
                    conf_template["controlPlane"] = {
                        "localAPIEndpoint": {
                            "advertiseAddress": self.config_dict["control-plane"]["ip_addr"],
                            "bindPort": 6443
                        }
                    }
                config_str += yaml.dump(conf_template)
                config_str += "---\n"
            with open("/root/files/conf/kubeletconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                config_str += yaml.dump(conf_template)
                config_str += "---\n"
            with open("/root/files/conf/kubeproxyconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                config_str += yaml.dump(conf_template)
            
            kubenode.cmd(f"echo '{config_str}' > /kind/kubeadm.conf")

            # Perform node-specific things and start the cluster
            if is_control:
                # Clear up the /etc/kubernetes directory
                kubenode.cmd("rm -rf /etc/kubernetes/*", privileged=True)
                # Start the control plane
                kubenode.cmd("kubeadm init --skip-phases=preflight --config=/kind/kubeadm.conf --skip-token-print --v=6", privileged=True, verbose=True)
                # Update the Kubectl config path
                kubenode.cmd("export KUBECONFIG=/etc/kubernetes/admin.conf", verbose=True)
                # Install CNI
                with open("/root/files/conf/cni.template", "r") as cni_conf_template:
                    cni_template_gen = yaml.safe_load_all(cni_conf_template)
                    cni_template = list(cni_template_gen)
                    cni_template[3]["spec"]["template"]["spec"]["containers"][0]["env"].append({
                        "name": "CONTROL_PLANE_ENDPOINT",
                        "value": self.config_dict['control-plane']['endpoint']
                    })
                    # Remove a trailing None
                    cni_template.pop()
                    cni_template_str: str = yaml.safe_dump_all(cni_template)
                    print(cni_template_str)
                    print(cni_template)
                    kubenode.cmd(f"echo '{cni_template_str}' > /kind/manifests/patched-cni.conf")
                    kubenode.cmd("kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/patched-cni.conf", privileged=True, verbose=True)
                # Install storage class
                kubenode.cmd("kubectl create --kubeconfig=/etc/kubernetes/admin.conf -f /kind/manifests/default-storage.yaml", privileged=True, verbose=True)
            else:
                # Join all worker nodes!
                kubenode.cmd("kubeadm join --config=/kind/kubeadm.conf --skip-phases=preflight --v=6", privileged=True, verbose=True)

        return (self.net, hosts, clients)
