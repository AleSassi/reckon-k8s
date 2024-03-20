import numpy as np
from time import time
import string
import itertools as it

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
        self._keys: list[str] = []

    # TODO test that _new_key generates correct length keys
    def _new_key(self, i, save: bool = True):
        key = f"dep-rc-{i}"
        if save:
            self._keys.append(key)
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

    @property
    def prerequisites(self) -> List[t.Write]:
        return [
                t.Create(
                    kind=t.OperationKind.Create, key=self._new_key(k), value="/root/reckon/systems/kubernetes/testdep.json"
                    )
                for k in range(self._max_key)
                ]

    @property
    def workload(self) -> Iterator[Union[t.Read, t.Write, t.Create, t.Update, t.Delete]]:
        i = 0
        while True:
            kind = self._gen_op_kind()
            if kind == 0:
                yield t.Create(
                        kind=t.OperationKind.Create,
                        key=self._new_key(len(self._keys)),
                        value="/root/reckon/systems/kubernetes/testdep.json",
                        )
            elif kind == 1:
                yield t.Read(
                        kind=t.OperationKind.Read,
                        key=self._rand_key(),
                        )
            elif kind == 2:
                yield t.Update(
                        kind=t.OperationKind.Update,
                        key=self._rand_key(),
                        value=self._rng.integers(1, 5)
                        )
            else:
                yield t.Delete(
                        kind=t.OperationKind.Delete,
                        key=self._rand_key(),
                        )
            i += 1

