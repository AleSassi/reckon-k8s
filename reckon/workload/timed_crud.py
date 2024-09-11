import numpy as np
from time import time
import string
import itertools as it
import json

from typing import List, Iterator, Tuple, Union
import reckon.reckon_types as t

class TimedCRUD(t.AbstractKeyGenerator):
    def __init__(
        self,
        max_key: int,
        rand_seed=int(time()),
    ):
        self._max_key = max_key
        self._rng = np.random.default_rng(rand_seed)
        self._keys: list[tuple[str, str]] = []
        self._op_count = 0
        self._op_index = 0
        req_per_sec = 20
        # 20 req/s * 100 sec
        self._op_timers = [
            # Stabilizing read
            {
                "op": "r",
                "cnt": req_per_sec * 15
            },
            # Scale Up + Stabilizing Read sequence (x5)
            {
                "op": "u-u",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 10
            },
            {
                "op": "u-d",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 10
            },
            {
                "op": "u-u",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 10
            },
            {
                "op": "u-d",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 10
            },
            {
                "op": "u-u",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 10
            },
            # Delete + Stabilizing Read
            {
                "op": "d",
                "cnt": 1
            },
            {
                "op": "r",
                "cnt": req_per_sec * 200 # Padding to fill the test time (whatever it is)
            }
        ]

    def _new_key(self, i, dep, save: bool = True):
        key = f"dep-rc-{i}"
        if save:
            self._keys.append((key, dep))
        return key

    def _rand_key(self):
        return self._keys[self._rng.integers(0, len(self._keys))]

    def _gen_op_kind(self):
        curr_op = self._op_timers[self._op_index]
        if self._op_count < curr_op["cnt"]:
            self._op_count += 1
            return curr_op["op"]
        else:
            self._op_count = 0
            self._op_index += 1
            return self._gen_op_kind()

    def _gen_create_deployment(self, i: int, depfile: str) -> t.Create:
        with open(depfile, "r") as jsondep:
            deployment_data = json.load(jsondep)
            metadata = deployment_data["metadata"]
            if metadata is not None:
                namespace = metadata["namespace"]
                if namespace is not None:
                    return t.Create(kind=t.OperationKind.Create, key=self._new_key(i, namespace), value=depfile)
        return t.Create(kind=t.OperationKind.Create, key=self._new_key(i, "default"), value=depfile)
    
    def _gen_replica_delta(self, up: bool = True) -> int:
        min = 1 if up else -2
        max = 4 if up else -1
        rand_delta = int(self._rng.integers(min, max))
        return rand_delta

    @property
    def prerequisites(self) -> List[t.Write | t.Create]:
        deps = [
                self._gen_create_deployment(k, "/root/reckon/systems/kubernetes/testdep.json")
                for k in range(self._max_key)
                ]
        deps.insert(0, t.Create(kind=t.OperationKind.Create, key="namespace", value="reckon-ns"))
        return deps

    @property
    def workload(self) -> Iterator[Union[t.Read, t.Write, t.Create, t.Update, t.Delete]]:
        i = 0
        while True:
            kind = self._gen_op_kind()
            if kind == "c":
                self._op_count += 1
                yield self._gen_create_deployment(len(self._keys), "/root/reckon/systems/kubernetes/testdep.json")
            elif kind == "r":
                dep, ns = self._rand_key()
                self._op_count += 1
                yield t.Read(
                        kind=t.OperationKind.Read,
                        key=f"{ns}:{dep}",
                        )
            elif kind == "u-u" or kind == "u-d":
                dep, ns = self._rand_key()
                self._op_count += 1
                yield t.Update(
                        kind=t.OperationKind.Update,
                        key=f"{ns}:{dep}",
                        value=json.dumps({ "replicaDelta": self._gen_replica_delta(kind == "u-u") })
                        )
            else:
                dep, ns = self._rand_key()
                self._op_count += 1
                yield t.Delete(
                        kind=t.OperationKind.Delete,
                        key=f"{ns}:{dep}",
                        )
            i += 1

