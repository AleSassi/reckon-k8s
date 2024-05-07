from enum import Enum
import math
import shutil
import subprocess
import sys
from typing import Union, Tuple, List, Iterator, Any, NewType, Dict, Callable, IO
import docker.errors
import requests
from typing_extensions import Literal
import logging
from struct import pack, unpack
from abc import ABC, abstractproperty, abstractmethod
from selectors import EVENT_READ, EVENT_WRITE, BaseSelector, SelectorKey
import time
import os
import shlex
import threading
import docker
import pty
import select

from mininet.net import Mininet, Containernet
from mininet.node import Host, Docker
from mininet.link import Link
from mininet.log import info, error, warn, debug
from pydantic import BaseModel, Field
from docker.models.containers import Container

class OperationKind(str, Enum):
    Write = "write"
    Read = "read"
    Create = "create"
    Update = "update"
    Delete = "delete"
    Other = "other"

    def __str__(self):
        return self.value


class Write(BaseModel):
    kind: Literal[OperationKind.Write]
    key: str
    value: str


class Read(BaseModel):
    kind: Literal[OperationKind.Read]
    key: str

class Create(BaseModel):
    kind: Literal[OperationKind.Create]
    key: str
    value: str

class Update(BaseModel):
    kind: Literal[OperationKind.Update]
    key: str
    value: str


class Delete(BaseModel):
    kind: Literal[OperationKind.Delete]
    key: str


class Operation(BaseModel):
    payload: Union[Write, Read, Create, Update, Delete] = Field(..., discriminator="kind")
    time: float


class Preload(BaseModel):
    kind: Literal["preload"]
    prereq: bool
    operation: Operation


class Finalise(BaseModel):
    kind: Literal["finalise"]


class Ready(BaseModel):
    kind: Literal["ready"]


class Start(BaseModel):
    kind: Literal["start"]


class Result(BaseModel):
    kind: Literal["result"]
    t_submitted: float
    t_result: float
    result: str
    op_kind: OperationKind
    clientid: str
    other: dict

class Finished(BaseModel):
    kind: Literal["finished"]


class Message(BaseModel):
    __root__: Union[Preload, Finalise, Ready, Start, Result, Finished] = Field(
        ..., discriminator="kind"
    )


class Client(object):
    def __init__(self, p_in: IO[bytes], p_out: IO[bytes], id: str):
        self.stdin = p_in
        self.stdout = p_out
        self.id = id

    def _send_packet(self, payload: str):
        size = pack("<l", len(payload))  # Little endian signed long (4 bytes)
        self.stdin.write(size + bytes(payload, "ascii"))
        self.stdin.flush()

    def _recv_packet(self) -> str:
        size = self.stdout.read(4)
        if size:
            size = unpack("<l", bytearray(size))  # Little endian signed long (4 bytes)
            payload = self.stdout.read(size[0])
            return str(payload, "ascii")
        else:
            logging.error(f"Tried to recv from |{self.id}|, received nothing")
            raise EOFError

    def send(self, msg: Message):
        payload = msg.json()
        self._send_packet(payload)

    def recv(self) -> Message:
        pkt = self._recv_packet()
        return Message.parse_raw(pkt)

    def register_selector(self, s: BaseSelector, e: Any, data: Any) -> SelectorKey:
        if e == EVENT_READ:
            return s.register(self.stdout, e, data)
        if e == EVENT_WRITE:
            return s.register(self.stdin, e, data)
        raise KeyError()

    def unregister_selector(self, s: BaseSelector, e: Any) -> SelectorKey:
        if e == EVENT_READ:
            return s.unregister(self.stdout)
        if e == EVENT_WRITE:
            return s.unregister(self.stdin)
        raise KeyError()


WorkloadOperation = Tuple[Client, Operation]


class Results(BaseModel):
    __root__: List[Result]

class AbstractKeyGenerator(ABC):
    @abstractproperty
    def prerequisites(self) -> List[Write | Create]:
        return []

    @abstractproperty
    def workload(self) -> Iterator[Union[Read, Write, Create, Update, Delete]]:
        """
        Returns an iterator through the workload from time = 0

        The time for each operation strictly increases.
        """
        return iter([])


class AbstractArrivalProcess(ABC):
    @abstractproperty
    def arrival_times(self) -> Iterator[float]:
        return iter([])

class AbstractWorkload(ABC):
    @property
    def clients(self):
        return self._clients

    @clients.setter
    def clients(self, value):
        self._clients = value

    @abstractproperty
    def prerequisites(self) -> List[Operation]:
        return []

    @abstractproperty
    def workload(self) -> Iterator[WorkloadOperation]:
        """
        Returns an iterator through the workload from time = 0

        The time for each operation strictly increases.
        """
        return iter([])


# Helper constructors
def preload(prereq: bool, operation: Operation) -> Message:
    return Message(
        __root__=Preload(kind="preload", prereq=prereq, operation=operation),
    )


def finalise() -> Message:
    return Message(__root__=Finalise(kind="finalise"))


def ready() -> Message:
    return Message(__root__=Ready(kind="ready"))


def start() -> Message:
    return Message(__root__=Start(kind="start"))


def result(
    t_s: float, t_r: float, result: str, kind: OperationKind, clientid: str, other: dict
) -> Message:
    return Message(
        __root__=Result(
            kind="result",
            t_submitted=t_s,
            t_result=t_r,
            result=result,
            op_kind=kind,
            clientid=clientid,
            other=other,
        )
    )


MininetHost = NewType("MininetHost", Host)


class AbstractClient(ABC):
    @abstractmethod
    def cmd(self, ips: List[str], client_id: str) -> str:
        pass


class AbstractSystem(ABC):
    def __init__(self, args):
        ctime = time.localtime()
        creation_time = time.strftime("%H:%M:%S", ctime)

        self.system_type = args.system_type
        self.log_location = args.system_logs
        if not os.path.exists(args.system_logs):
            os.makedirs(args.system_logs)
        self.creation_time = creation_time
        self.client_class = self.get_client(args)
        self.client_type = args.client
        self.data_dir = args.data_dir
        self.failure_timeout = args.failure_timeout
        self.delay_interval = args.delay_interval

        super(AbstractSystem, self).__init__()

    def __str__(self):
        return "{0}-{1}".format(self.system_type, self.client_type)

    def get_client_tag(self, host: MininetHost):
        return "mc_" + host.name

    def get_node_tag(self, host: MininetHost):
        return "node_" + host.name

    def start_screen(self, host: MininetHost, command: str):
        FNULL = open(os.devnull, "w")
        quotedcommand = command.translate(str.maketrans({"\\": r"\\", "\"": r"\""})) # Quote all speech marks
        cmd = 'screen -dmS {tag} bash -c "{command}"'.format(
            tag=self.get_node_tag(host), command=quotedcommand
        )
        print("Starting screen on {0} with cmd: {1}".format(host.name, cmd))
        host.popen(shlex.split(cmd), stdout=FNULL, stderr=FNULL)

    def kill_screen(self, host: MininetHost):
        cmd = ("screen -X -S {0} quit").format(self.get_node_tag(host))
        logging.debug("Killing screen on host {0} with cmd {1}".format(host.name, cmd))
        host.cmd(shlex.split(cmd))

    def add_stderr_logging(self, cmd: str, tag: str):
        time = self.creation_time
        log = self.log_location
        return f"{cmd} 2> {log}/{time}_{tag}.err"

    def add_stdout_logging(self, cmd: str, tag: str, verbose: bool=False):
        time = self.creation_time
        log = self.log_location
        return f"{cmd} | tee {log}/{time}_{tag}.out" if verbose else f"{cmd} > {log}/{time}_{tag}.out"

    @abstractmethod
    def prepare_test_start(self, cluster: List[MininetHost]) -> Result | None:
        pass

    @abstractmethod
    def stat(self, host: MininetHost) -> str:
        pass

    @abstractmethod
    def get_client(self, args) -> AbstractClient:
        pass

    @abstractmethod
    def start_nodes(
        self, cluster: List[MininetHost]
    ) -> Tuple[Dict[Any, Callable[[], None]], Dict[Any, Callable[[], None]], Dict[Any, Callable[[], None]]]:
        pass

    @abstractmethod
    def start_client(
        self, client: MininetHost, client_id: str, cluster: List[MininetHost]
    ) -> Client:
        pass

    @abstractmethod
    def get_leader(self, cluster: List[MininetHost]) -> MininetHost:
        return None


class AbstractFault(ABC):
    def id(self) -> str:
        return "Generic Fault"

    @abstractmethod
    def apply_fault(self):
        pass


class NullFault(AbstractFault):
    def id(self):
        return ""

    def apply_fault(self):
        pass


class AbstractFailureGenerator(ABC):
    @abstractmethod
    def get_failures(
        self,
        cluster: List[MininetHost],
        system: AbstractSystem,
        restarters: Dict[Any, Callable[[], None]],
        stoppers: Dict[Any, Callable[[], None]],
    ) -> List[AbstractFault]:
        pass

class LinkSpec(BaseModel):
    n_from: str
    n_to: str
    latency_ms: float | None
    loss_perc: float | None
    jitter_ms: float | None

class NetSpec(BaseModel):
    __root__: List[LinkSpec]

class AbstractTopologyGenerator(ABC):
    def __init__(self, number_nodes, number_clients, link_latency=None, link_loss=None, link_jitter=None, link_specs:NetSpec|None=None):
        self.number_nodes = number_nodes
        self.number_clients = number_clients

        per_link_latency = None if not link_latency else link_latency
        per_link_jitter = link_jitter if (link_jitter is not None and link_jitter > 0) else None
        per_link_loss = None if not link_loss else (1 - math.sqrt(1 - link_loss / 100)) * 100
        if per_link_loss == 0:
            per_link_loss = None

        self.link_specs = link_specs if not None else NetSpec(__root__=[])
        self.default_spec = LinkSpec(n_from="*", n_to="*", latency_ms=per_link_latency, loss_perc=per_link_loss, jitter_ms=per_link_jitter)

        self.switch_num = 0
        self.host_num = 0
        self.client_num = 0
    
    def get_link_spec(self, n_from: str, n_to: str) -> LinkSpec:
        spec = self.default_spec
        for sp in self.link_specs.__root__:
            if (sp.n_from == n_from.name and sp.n_to == n_to.name) or (sp.n_from == n_to.name and sp.n_to == n_from.name):
                spec = sp
                print(f"Found matching spec from {sp.n_from} to {sp.n_to}")
                break
        if spec == self.default_spec:
            print(f"No matching spec from {sp.n_from} to {sp.n_to} found!")
        if spec.loss_perc == 0:
            spec.loss_perc = None
        return spec

    @abstractmethod
    def setup(self) -> Tuple[Mininet, List[MininetHost], List[MininetHost]]:
        pass


class ThreadWithResult(threading.Thread):
    def __init__(
        self, group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None
    ):
        self._result: Any = None

        def function():
            if target:
                self._result = target(*args, **kwargs)

        super().__init__(group=group, target=function, name=name, daemon=daemon)

    @property
    def result(self) -> Any:
        return self._result

class KubeNode ( Docker ):
    """
    Node that represents a docker container, but with elevated privileges.
    """

    def __init__(self, name, dimage=None, dcmd=None, build_params={},
                 **kwargs):
        """
        Creates a Docker container as Mininet host.

        Resource limitations based on CFS scheduler:
        * cpu.cfs_quota_us: the total available run-time within a period (in microseconds)
        * cpu.cfs_period_us: the length of a period (in microseconds)
        (https://www.kernel.org/doc/Documentation/scheduler/sched-bwc.txt)

        Default Docker resource limitations:
        * cpu_shares: Relative amount of max. avail CPU for container
            (not a hard limit, e.g. if only one container is busy and the rest idle)
            e.g. usage: d1=4 d2=6 <=> 40% 60% CPU
        * cpuset_cpus: Bind containers to CPU 0 = cpu_1 ... n-1 = cpu_n (string: '0,2')
        * mem_limit: Memory limit (format: <number>[<unit>], where unit = b, k, m or g)
        * memswap_limit: Total limit = memory + swap

        All resource limits can be updated at runtime! Use:
        * updateCpuLimits(...)
        * updateMemoryLimits(...)
        """
        self.dimage = dimage
        self.dnameprefix = "mn"
        self.dcmd = dcmd if dcmd is not None else "/bin/bash"
        self.dc = None  # pointer to the dict containing 'Id' and 'Warnings' keys of the container
        self.dcinfo = None
        self.did = None # Id of running container
        #  let's store our resource limits to have them available through the
        #  Mininet API later on
        defaults = { 'cpu_quota': None,
                     'cpu_period': None,
                     'cpu_shares': None,
                     'cpuset_cpus': None,
                     'mem_limit': None,
                     'memswap_limit': None,
                     'environment': {},
                     'volumes': [],  # use ["/home/user1/:/mnt/vol2:rw"]
                     'tmpfs': [], # use ["/home/vol1/:size=3G,uid=1000"]
                     'network_mode': None,
                     'publish_all_ports': True,
                     'port_bindings': {},
                     'ports': [],
                     'dns': [],
                     'ipc_mode': None,
                     'devices': [],
                     'cap_add': ['net_admin'],  # we need this to allow mininet network setup
                     'storage_opt': None,
                     'sysctls': {},
                     'shm_size': '64mb',
                     'cpus': None,
                     'device_requests': []
                     }
        defaults.update( kwargs )

        if 'net_admin' not in defaults['cap_add']:
            defaults['cap_add'] += ['net_admin']  # adding net_admin if it's cleared out to allow mininet network setup

        # keep resource in a dict for easy update during container lifetime
        self.resources = dict(
            cpu_quota=defaults['cpu_quota'],
            cpu_period=defaults['cpu_period'],
            cpu_shares=defaults['cpu_shares'],
            cpuset_cpus=defaults['cpuset_cpus'],
            mem_limit=defaults['mem_limit'],
            memswap_limit=defaults['memswap_limit']
        )
        self.shm_size = defaults['shm_size']
        self.nano_cpus = defaults['cpus'] * 1_000_000_000 if defaults['cpus'] else None
        self.device_requests = defaults['device_requests']
        self.volumes = defaults['volumes']
        self.tmpfs = defaults['tmpfs']
        self.environment = {} if defaults['environment'] is None else defaults['environment']
        # setting PS1 at "docker run" may break the python docker api (update_container hangs...)
        # self.environment.update({"PS1": chr(127)})  # CLI support
        self.network_mode = defaults['network_mode']
        self.publish_all_ports = defaults['publish_all_ports']
        self.port_bindings = defaults['port_bindings']
        self.dns = defaults['dns']
        self.ipc_mode = defaults['ipc_mode']
        self.devices = defaults['devices']
        self.cap_add = defaults['cap_add']
        self.sysctls = defaults['sysctls']
        self.storage_opt = defaults['storage_opt']

        # setup docker client
        # self.dcli = docker.APIClient(base_url='unix://var/run/docker.sock')
        self.d_client = docker.from_env(timeout=240)
        self.dcli = self.d_client.api
        self.dname = "%s.%s" % (self.dnameprefix, name)

        _id = None
        if build_params.get("path", None):
            if not build_params.get("tag", None):
                if dimage:
                    build_params["tag"] = dimage
            _id, output = self.build(**build_params)
            dimage = _id
            self.dimage = _id
            info("Docker image built: id: {},  {}. Output:\n".format(
                _id, build_params.get("tag", None)))
            info(output)

        # pull image if it does not exist
        self._check_image_exists(dimage, True, _id=None)
        # Check if a (killed) container with the same name exists. In that case, just reload the container and restart it!
        restartsContainer = False
        try:
            dc: Container = self.d_client.containers.get(self.dname)
            if dc.attrs['State']['Status'] != 'running' and kwargs.get("reloadable", False):
                self.dc = dc
                restartsContainer = True
        except docker.errors.NotFound:
            info("Container not found! Recreating...")

        # for DEBUG
        debug("Created docker container object %s\n" % name)
        debug("image: %s\n" % str(self.dimage))
        debug("dcmd: %s\n" % str(self.dcmd))
        info("%s: kwargs %s\n" % (name, str(kwargs)))

        if not restartsContainer:
            # see: https://docker-py.readthedocs.io/en/stable/api.html#docker.api.container.ContainerApiMixin.create_host_config
            # creats host config for container
            hc = self.dcli.create_host_config(
                network_mode=self.network_mode,
                privileged=True,
                binds=self.volumes,
                tmpfs=self.tmpfs,
                publish_all_ports=self.publish_all_ports,
                port_bindings=self.port_bindings,
                mem_limit=self.resources.get('mem_limit'),
                cpuset_cpus=self.resources.get('cpuset_cpus'),
                dns=self.dns,
                ipc_mode=self.ipc_mode,  # string
                devices=self.devices,  # see docker-py docu
                cap_add=self.cap_add,  # see docker-py docu
                sysctls=self.sysctls,   # see docker-py docu
                storage_opt=self.storage_opt,
                # Assuming Docker uses the cgroupfs driver, we set the parent to safely
                # access cgroups when modifying resource limits.
                cgroup_parent='/docker',
                shm_size=self.shm_size,
                nano_cpus=self.nano_cpus,
                device_requests=self.device_requests,
            )

            # create new docker container
            if kwargs.get("rm", False):
                cont_name = "%s.%s" % (self.dnameprefix, name)
                containers: list[Container] = self.d_client.containers.list(all=True)
                print(f"Checking the existence of a container named {cont_name} (found {len(containers)} containers)...")
                for container in containers:
                    if cont_name in container.name:
                        print(f"Container with ID {container.id} has the same name as the container to be started. Killing and removing...")
                        container.remove(v=True, force=True)
            
            print("Starting the container...")
            self.dc = self.dcli.create_container(
                name="%s.%s" % (self.dnameprefix, name),
                image=self.dimage,
                command=self.dcmd,
                entrypoint=list(),  # overwrite (will be executed manually at the end)
                stdin_open=True,  # keep container open
                tty=True,  # allocate pseudo tty
                environment=self.environment,
                #network_disabled=True,  # docker stats breaks if we disable the default network
                host_config=hc,
                ports=defaults['ports'],
                labels=['com.containernet'],
                volumes=[self._get_volume_mount_name(v) for v in self.volumes if self._get_volume_mount_name(v) is not None],
                hostname=name,
            )
            # start the container
            self.dcli.start(self.dc)
            debug("Docker container %s started\n" % name)
            # fetch information about new container
            self.dcinfo = self.dcli.inspect_container(self.dc)
        else:
            print("Starting the container...")
            self.dcli.start(self.dname)
            debug("Docker container %s started\n" % name)
            # fetch information about new container
            self.dcinfo = self.dcli.inspect_container(self.dname)

        self.did = self.dcinfo.get("Id")
        self.dcont: Container | None = self.d_client.containers.get(self.dname)

        # call original Node.__init__
        Host.__init__(self, name, **kwargs)

        # let's initially set our resource limits
        self.update_resources(**self.resources)

        self.master = None
        self.slave = None
        self.running = True
        self.kubenet: KuberNet = kwargs.get("net")

    def update_resources(self, **kwargs):
        """
        Update the container's resources using the docker.update function
        re-using the same parameters:
        Args:
           blkio_weight
           cpu_period, cpu_quota, cpu_shares
           cpuset_cpus
           cpuset_mems
           mem_limit
           mem_reservation
           memswap_limit
           kernel_memory
           restart_policy
        see https://docs.docker.com/engine/reference/commandline/update/
        or API docs: https://docker-py.readthedocs.io/en/stable/api.html#module-docker.api.container
        :return:
        """

        self.resources.update(kwargs)
        # filter out None values to avoid errors
        resources_filtered = {res:self.resources[res] for res in self.resources if self.resources[res] is not None}
        info("{1}: update resources {0}\n".format(resources_filtered, self.name))
        self.dcli.update_container(self.dc if not type(self.dc) is Container else self.dname, **resources_filtered) # Check for when the conatienr is restarted from a killed container

    def setKubeAttrs(self, is_control: bool, name: str, ip_addr: str, volume: str):
        self.k8s_name = name
        self.ip_addr = ip_addr
        if is_control:
            self.endpoint = f"{ip_addr}:6443"
        else:
            last_ip = int(ip_addr.split(".")[-1])
            self.worker_num = 255 - last_ip
        self.volume = volume
        self.is_control = is_control

    def start(self):
        # Overridden to do nothing, since the entrypoint is already manually executed when starting the container
        self.running = True
        return

    # Command support via shell process in namespace
    def startShell( self, privileged: bool = True, *args, **kwargs ):
        "Start a shell process for running commands"
        if self.shell:
            error( "%s: shell is already running\n" % self.name )
            return
        # mnexec: (c)lose descriptors, (d)etach from tty,
        # (p)rint pid, and run in (n)amespace
        # opts = '-cd' if mnopts is None else mnopts
        # if self.inNamespace:
        #     opts += 'n'
        # bash -i: force interactive
        # -s: pass $* to shell, and make process easy to find in ps
        # prompt is set to sentinel chr( 127 )
        cmd = [ 'docker', 'exec', '-it',  '%s.%s' % ( self.dnameprefix, self.name ), 'env', 'PS1=' + chr( 127 ),
                'bash', '--norc', '-is', 'mininet:' + self.name ]
        if privileged:
            cmd = [ 'docker', 'exec', '-it', '--privileged',  '%s.%s' % ( self.dnameprefix, self.name ), 'env', 'PS1=' + chr( 127 ),
                'bash', '--norc', '-is', 'mininet:' + self.name ]
        # Spawn a shell subprocess in a pseudo-tty, to disable buffering
        # in the subprocess and insulate it from signals (e.g. SIGINT)
        # received by the parent
        self.master, self.slave = pty.openpty()
        self.shell = self._popen( cmd, stdin=self.slave, stdout=self.slave, stderr=self.slave,
                                  close_fds=False )
        self.stdin = os.fdopen( self.master, 'r' )
        self.stdout = self.stdin
        self.pid = self._get_pid()
        self.pollOut = select.poll()
        self.pollOut.register( self.stdout )
        # Maintain mapping between file descriptors and nodes
        # This is useful for monitoring multiple nodes
        # using select.poll()
        self.outToNode[ self.stdout.fileno() ] = self
        self.inToNode[ self.stdin.fileno() ] = self
        self.execed = False
        self.lastCmd = None
        self.lastPid = None
        self.readbuf = ''
        # Wait for prompt
        while True:
            data = self.read( 1024 )
            if data[ -1 ] == chr( 127 ):
                break
            self.pollOut.poll()
        self.waiting = False
        # +m: disable job control notification
        self.cmd( 'unset HISTFILE; stty -echo; set +m' )
    
    def cmd( self, *args, **kwargs ):
        """Send a command, wait for output, and return it.
           cmd: string"""
        verbose = kwargs.get( 'verbose', False )
        privileged = kwargs.get('privileged', False)
        detached = kwargs.get('detached', False)
        log = info if verbose else debug
        log( '*** %s : %s\n' % ( self.name, args ) )
        if detached:
            # Run Docker exec detached!
            self.dcont.exec_run(args[0], verbose, verbose, detach=True)
        else:
            if self.shell:
                self.shell.poll()
                if self.shell.returncode is not None:
                    print("shell died on ", self.name)
                    print(f"Return code: {self.shell.returncode}")
                    self.shell = None
                    self.startShell(privileged=privileged)
                self.sendCmd( *args, **kwargs )
                return self.waitOutput( verbose )
            else:
                warn( '(%s exited - ignoring cmd%s)\n' % ( self, args ) )
        return None

    def stop( self, deleteIntfs=False ):
        """Stop node.
           deleteIntfs: delete interfaces? (False)
           Overridden to call a custom Terminate that just kills (no remove) the container"""
        if deleteIntfs:
            self.deleteIntfs()
        if not self._is_container_running():
            return
        try:
            dc: Container = self.d_client.containers.get(self.dname)
            dc.kill()
        except docker.errors.APIError as e:
            warn("Warning: API error during container kill.\n")

        self.cleanup()
    
    class KubeLink:
        n_from: Host
        n_to: Host
        ip_addr_from: str
        ip_addr_to: str
        delay: str
        loss: float
        jitter: str

        def __init__(self, n_from: Host, n_to: Host, ip_addr_from: str, ip_addr_to: str, delay: str, loss: float, jitter: str):
            self.n_from = n_from
            self.n_to = n_to
            self.ip_addr_from = ip_addr_from
            self.ip_addr_to = ip_addr_to
            self.delay = delay
            self.loss = loss
            self.jitter = jitter

    def pause(self):
        """
        Simulates a (recoverable) node failure
        """
        if self.running:
            # We need to copy some files to a location which persists between restarts, otherwise all data mounted to tmpfs will be wiped!
            self.cmd("bash /kind/backup-tmpfs.sh", verbose=True)
            self.cmd("pkill -15 tcpdump", verbose=True)
            self.cmd("while pkill -0 tcpdump 2> /dev/null; do sleep 1; done;", verbose=True)
            # Keep track of every link we need to restore later
            self.kubeLinks: list[self.KubeLink] = []
            for l in self.kubenet.links:
                link: Link = l
                if link.intf1.node == self or link.intf2.node == self:
                    self.kubeLinks.append(self.KubeLink(link.intf1.node,
                                                        link.intf2.node,
                                                        link.intf1.IP(),
                                                        link.intf2.IP(),
                                                        link.intf1.params["delay"] if link.intf1.node == self else link.intf2.params["delay"],
                                                        link.intf1.params["loss"] if link.intf1.node == self else link.intf2.params["loss"],
                                                        link.intf1.params["jitter"] if link.intf1.node == self else link.intf2.params["jitter"]))
            self.kubenet.removeHost(self)
        self.running = False
    
    def terminateAndRemove(self):
        """
        Stops the container
        """
        dc: Container = self.d_client.containers.get(self.dname)
        try:
            #dc.stop(timeout=60)
            self.cmd("pkill -15 tcpdump", verbose=True)
            self.cmd("while pkill -0 tcpdump 2> /dev/null; do sleep 1; done;", verbose=True)
            dc.kill()
        except docker.errors.APIError as e:
            if e.status_code == 500:
                print(f"ERROR while stopping container {self.dname}: {e.status_code} - {e.explanation}")
                print("Sleeping for 60 seconds before forcibly removing the container...")
                time.sleep(60)
            else:
                raise e
        dc.remove(v=True, force=True)
    
    def restart(self, cluster: list):
        if not self.running:
            # Replace the kubenode in the cluster with a new one
            newHost = self.kubenet.addDocker(self.name,
                                             ip=self.ip_addr,
                                             dimage=self.dimage,
                                             dcmd=self.dcmd, 
                                             volumes=self.volumes,
                                             tmpfs=self.tmpfs,
                                             net=self.kubenet,
                                             reloadable=True)
            newHost.cmd("bash /kind/restore-tmpfs.sh", verbose=True)
            # Add all links back
            for l in self.kubeLinks:
                link: self.KubeLink = l
                newHost.kubenet.addLink(newHost.kubenet.get(link.n_from.name), newHost.kubenet.get(link.n_to.name), delay=link.delay, los=link.loss, jitter=link.jitter, params1={'ip': f"{link.ip_addr_from}/8"}, params2={'ip': f"{link.ip_addr_to}/8"})
            self.kubeLinks = []
            old_host_idx = cluster.index(self)
            cluster[old_host_idx] = newHost
        self.running = True

    
class KuberNet (Containernet):
    def __init__(self, **params):
        Containernet.__init__(self, **params);
        self.cp_num = 0
        self.host_num = 0
        self.worker_num = 0
        self.config_dict: dict = {
            "control_plane": {},
            "workers": []
        }

    def addDocker(self, name, **params) -> KubeNode:
        return self.addHost(name, cls=KubeNode, **params)
    
    def _add_control_plane(self):
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
    
    def _add_worker_node(self):
        assert(self.cp_num > 0 and self.cp_num < 254)
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
    
    #def createCluster(self, control_planes=1, workers=2) -> list[KubeNode]:
    def createCluster(self, workers=2) -> list[KubeNode]:
        nodes: list[KubeNode] = []
        self._add_control_plane()
        if workers > 0:
            for _ in range(workers):
                self._add_worker_node()
        
        # Cleanup the logs directory
        self._deleteDirContent("/results/logs/kubenodes")
        
        # Preconfigure all nodes
        for i in range(1 + workers):
            # Generate the kubeadm config file for the node
            is_control = i == 0
            worker_idx = i - 1
            node_info = self.config_dict["control-plane"] if is_control else self.config_dict["workers"][worker_idx]
            
            # Determine the shared folders/volumes for the node
            docker_vols = ["/lib/modules:/lib/modules:ro", # Required by the KinD node image
                           "/var", # Required by the KinD node image
                           "kubenode_results:/results/logs:rw",
                           f"kubefiles_{'cp' if is_control else 'wn'+str(worker_idx + 1)}:/etc/kubernetes:rw",
                           f"containerd_snapshots_overlayfs_{'cp' if is_control else 'wn'+str(worker_idx + 1)}:/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots"]
            if is_control:
                # The control plane mounts the Docker volume of each worker's /etc/kubernetes dir
                # This way it can easily copy the config required by the KinD node to workers
                workers: list[dict] = self.config_dict["workers"]
                i = 1
                for worker in workers:
                    docker_vols.append(f"{worker['volume']}:/kind/nodedata/wn{i}")
                    i += 1
                # Add a shared directory with Reckon to share config files (for clients)
                docker_vols.append("shared_files:/kind/shared_files:rw")

            # Create the Node container
            kubenode = self.addDocker(node_info['name'],
                                      ip=node_info['ip_addr'],
                                      dimage=f"AleSassi/reckon-k8s-{'control' if is_control else 'worker'}",
                                      dcmd="/usr/local/bin/entrypoint /sbin/init && /bin/bash", 
                                      volumes=docker_vols,
                                      tmpfs={
                                          #"/var/lib/kubelet/pods": "",
                                          "/opt/cni/bin": "exec",
                                          "/var/lib/containerd": "exec",
                                          "/run/containerd": "exec"
                                          #"/etc/kubernetes/manifests": ""
                                      },
                                      net=self)
            kubenode.setKubeAttrs(is_control, node_info["name"], node_info["ip_addr"], node_info["volume"])
            kubenode.node_img = f"AleSassi/reckon-k8s-{'control' if is_control else 'worker'}"
            kubenode.docker_vols = docker_vols
            nodes.append(kubenode)
        return nodes

    def _deleteDirContent(self, dirPath: str):
        for filename in os.listdir(dirPath):
            file_path = os.path.join(dirPath, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (file_path, e))
