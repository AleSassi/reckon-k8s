import numpy as np
from time import time
import string
import itertools as it
import json

from typing import List, Iterator, Tuple, Union
import reckon.reckon_types as t

class UniformCRUD(t.AbstractKeyGenerator):
    def __init__(
        self,
        op_ratio: Tuple[float, float, float, float],
        max_key: int,
        rand_seed=int(time()),
    ):
        assert op_ratio[0] + op_ratio[1] + op_ratio[2] + op_ratio[3] == 1
        self._op_ratio = op_ratio
        self._max_key = max_key
        self._rng = np.random.default_rng(rand_seed)
        self._keys: list[tuple[str, str]] = []

    def _new_key(self, i, dep, save: bool = True):
        key = f"dep-rc-{i}"
        if save:
            self._keys.append((key, dep))
        return key

    def _rand_key(self):
        return self._keys[self._rng.integers(0, len(self._keys))]

    def _gen_op_kind(self):
        rand = self._rng.random()
        cum = 0
        for i in range(4):
            if cum <= rand <= (self._op_ratio[i] + cum):
                return i
            cum += self._op_ratio[i]
        return 3

    def _gen_create_deployment(self, i: int, depfile: str) -> t.Create:
        with open(depfile, "r") as jsondep:
            deployment_data = json.load(jsondep)
            metadata = deployment_data["metadata"]
            if metadata is not None:
                namespace = metadata["namespace"]
                if namespace is not None:
                    return t.Create(kind=t.OperationKind.Create, key=self._new_key(i, namespace), value=depfile)
        return t.Create(kind=t.OperationKind.Create, key=self._new_key(i, "default"), value=depfile)

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
            if kind == 0:
                yield self._gen_create_deployment(len(self._keys), "/root/reckon/systems/kubernetes/testdep.json")
            elif kind == 1:
                dep, ns = self._rand_key()
                yield t.Read(
                        kind=t.OperationKind.Read,
                        key=f"{ns}:{dep}",
                        )
            elif kind == 2:
                dep, ns = self._rand_key()
                yield t.Update(
                        kind=t.OperationKind.Update,
                        key=f"{ns}:{dep}",
                        value=json.dumps({ "replicaDelta": int(self._rng.integers(1, 5)) })
                        )
            else:
                dep, ns = self._rand_key()
                yield t.Delete(
                        kind=t.OperationKind.Delete,
                        key=f"{ns}:{dep}",
                        )
            i += 1

