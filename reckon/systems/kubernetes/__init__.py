from enum import Enum
import subprocess
import logging
import yaml

import reckon.reckon_types as t


class Go(t.AbstractClient):
    client_path = "reckon/systems/etcd/clients/go/client"

    def __init__(self, args):
        self.ncpr = args.new_client_per_request

    def cmd(self, ips, client_id) -> str:
        return "{client_path} --targets={ips} --id={client_id} --ncpr={ncpr}".format(
            client_path=self.client_path,
            ips=",".join(f"http://{ip}:2379" for ip in ips),
            client_id=str(client_id),
            ncpr=self.ncpr,
        )


class GoTracer(Go):
    client_path = "reckon/systems/etcd/clients/go-tracer/client"


class ClientType(Enum):
    Go = "go"
    GoTracer = "go-tracer"

    def __str__(self):
        return self.value


class Kubernetes(t.AbstractSystem):
    binary_path = ""
    additional_flags = ""

    def get_client(self, args):
        if args.client == str(ClientType.Go) or args.client is None:
            return Go(args)
        elif args.client == str(ClientType.GoTracer):
            return GoTracer(args)
        else:
            raise Exception("Not supported client type: " + str(args.client))

    def start_nodes(self, cluster):
        restarters = {}
        stoppers = {}
        killers = {}

        kubecluster: list[t.KubeNode] = cluster
        control_plane = kubecluster[0]
        # Now that interfaces are up, we can start our Kubernetes cluster
        for kubenode in kubecluster:
            tag = self.get_node_tag(kubenode)

            # Generate the kubeadm config file for the node
            config_str = ""
            with open("/root/files/conf/clusterconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["controlPlaneEndpoint"] = control_plane.endpoint
                conf_template["controllerManager"]["extraArgs"]["enable-hostpath-provisioner"] = "true"
                config_str += yaml.dump(conf_template, default_style='"')
                config_str += "---\n"
            with open("/root/files/conf/initconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["localAPIEndpoint"]["advertiseAddress"] = kubenode.ip_addr
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = kubenode.ip_addr
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += kubenode.k8s_name
                config_str += yaml.dump(conf_template)
                config_str += "---\n"
            with open("/root/files/conf/joinconfig.template", "r") as conf_template_file:
                conf_template = yaml.safe_load(conf_template_file)
                conf_template["discovery"]["bootstrapToken"]["apiServerEndpoint"] = control_plane.endpoint
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["node-ip"] = kubenode.ip_addr
                conf_template["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] += kubenode.k8s_name
                if kubenode.is_control:
                    conf_template["controlPlane"] = {
                        "localAPIEndpoint": {
                            "advertiseAddress": control_plane.ip_addr,
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
            start_cmd = ""
            if kubenode.is_control:
                # Prepare files for installation of CNI
                with open("/root/files/conf/cni.template", "r") as cni_conf_template:
                    cni_template_gen = yaml.safe_load_all(cni_conf_template)
                    cni_template = list(cni_template_gen)
                    cni_template[3]["spec"]["template"]["spec"]["containers"][0]["env"].append({
                        "name": "CONTROL_PLANE_ENDPOINT",
                        "value": control_plane.endpoint
                    })
                    # Remove a trailing None
                    cni_template.pop()
                    cni_template_str: str = yaml.safe_dump_all(cni_template)
                    kubenode.cmd(f"echo '{cni_template_str}' > /kind/manifests/patched-cni.conf")
                # Start the Control Plane
                start_cmd = "source /kind/startcp.sh"
            else:
                # Join all worker nodes!
                start_cmd = "kubeadm join --config=/kind/kubeadm.conf --skip-phases=preflight --v=6"
            start_cmd = self.add_stderr_logging(start_cmd, tag + ".log")
            start_cmd = self.add_stdout_logging(start_cmd, tag + ".log", verbose=True)

            logging.debug("Start cmd: " + start_cmd)
            kubenode.cmd(start_cmd, verbose=True)

            # We use the default arguemnt to capture the host variable semantically rather than lexically
            stoppers[tag] = lambda host=kubenode: host.pause()
            killers[tag] = lambda host=kubenode: host.terminate()
            restarters[tag] = lambda host=kubenode, start_cmd=start_cmd: host.restart()

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

    def get_leader(self, cluster):
        ips = [host.IP() for host in cluster]
        return cluster[0]

    def stat(self, host: t.MininetHost) -> str:
        return ""
