from io import TextIOWrapper
import json
import time
from enum import Enum
from typing import List
from abc import ABC, abstractproperty

from pydantic import BaseModel

from reckon.workload import ArrivalType, KeyType
from reckon.systems import SystemType
from reckon.failures import FailureType
from reckon.topologies import TopologyType

import git

class CustomJSONConvertible(ABC):
    @abstractproperty
    def enums() -> dict[str, any]:
        pass

    def __dict__(self):
        obj_dict = {}
        for key, value in vars(self).items():
            if hasattr(value, "__dict__"):
                obj_dict[key] = value.__dict__()
            elif isinstance(value, list):
                obj_dict[key] = [v.__dict__() if hasattr(v, "__dict__") else v for v in value]
            elif isinstance(value, dict):
                obj_dict[key] = {k: v.__dict__() if hasattr(v, "__dict__") else v for k, v in value.items()}
            elif type(value) in self.enums().values():
                obj_dict[key] = {"__enum__": str(value)}
            else:
                obj_dict[key] = value
        return obj_dict

class ReckonConfig(BaseModel):
    system_type: SystemType = SystemType.Kubernetes
    client: str | None = "go"
    arrival_process: ArrivalType = ArrivalType.Uniform
    key_distribution: KeyType = KeyType.Uniform
    rate: float = 100
    write_ratio: float = 1
    create_ratio: float = 0
    read_ratio: float = 0.75
    update_ratio: float = 0.25
    delete_ratio: float = 0
    max_key: int = 1
    payload_size: int = 10
    key_gen_seed: int
    arrival_seed: int
    system_logs: str = "./logs"
    new_client_per_request: bool = False
    failure_timeout: float = 1.0
    delay_interval: float = 0.010
    duration: float = 60
    result_location: str = "/results/"
    data_dir: str = "./data"
    topo_type: TopologyType = TopologyType.Simple_K8s
    number_nodes: int = 3
    number_clients: int = 1
    link_loss: float = 0
    link_jitter: float = 0
    net_spec: str = "[]"
    link_latency: float = 20
    failure_type: FailureType = FailureType.FNone
    kill_n: int = 0
    mtbf: float = 1

    def enums() -> dict[str, any]:
        return {
            "ArrivalType": ArrivalType,
            "KeyType": KeyType,
            "SystemType": SystemType,
            "FailureType": FailureType,
            "TopologyType": TopologyType
        }

class GitInfo(BaseModel):
    commit_sha: str
    head_sha: str

    def create():
        try:
            repo = git.Repo(search_parent_directories=True)
            commit_sha = repo.head.commit.hexsha
            head_sha = repo.head.object.hexsha
        except Exception:
            commit_sha = "None"
            head_sha = "None"
        return GitInfo(commit_sha=commit_sha, head_sha=head_sha)

    def enums() -> dict[str, any]:
        return {}

class Config(BaseModel):
    reckonConfig: ReckonConfig
    gitInfo: GitInfo

    def enums() -> dict[str, any]:
        return ReckonConfig.enums() | GitInfo.enums()

    def toJSON(self) -> str:
        return json.dumps(self, cls=ConfigEncoder)
    
    def toJSON(self, fp: TextIOWrapper) -> None:
        return json.dump(self, fp, cls=ConfigEncoder)

    def fromJSON(jsonstr: str):
        conf: Config = json.loads(jsonstr, object_hook=_as_enum)
        return conf
    
    def fromJSON(jsonfile: TextIOWrapper):
        conf: Config = json.load(jsonfile, object_hook=_as_enum)
        return conf

class ConfigEncoder(json.JSONEncoder):
    def default(self, obj):
        if type(obj) in Config.enums().values():
            return {"__enum__": str(obj)}
        elif hasattr(obj, "__dict__"):
            return obj.__dict__()
        return json.JSONEncoder.default(self, obj)

def _as_enum(d):
    if "__enum__" in d:
        name, member = d["__enum__"].split(".")
        return getattr(Config.enums()[name], member)
    else:
        return d
