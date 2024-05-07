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
    system_type: SystemType
    client: str
    arrival_process: ArrivalType
    key_distribution: KeyType
    rate: float
    write_ratio: float
    create_ratio: float
    read_ratio: float
    update_ratio: float
    delete_ratio: float
    max_key: int
    payload_size: int
    key_gen_seed: int
    arrival_seed: int
    system_logs: str
    new_client_per_request: bool
    failure_timeout: float
    delay_interval: float
    duration: float
    result_location: str
    data_dir: str
    topo_type: TopologyType
    number_nodes: int
    number_clients: int
    link_loss: float
    link_jitter: float
    net_spec: str
    link_latency: float
    failure_type: FailureType

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
