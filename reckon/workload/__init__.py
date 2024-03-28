from enum import Enum
from time import time
from typing import List, Iterator
import itertools as it
from reckon.workload.uniform_crud import UniformCRUD
from reckon.workload.uniform import UniformKeys, UniformArrival
from reckon.workload.poisson import PoissonArrival

import reckon.reckon_types as t
import reckon.systems as s

class KeyType(Enum):
    Uniform = "uniform"

    def __str__(self):
        return self.value

class ArrivalType(Enum):
    Uniform = "uniform"
    Poisson = "poisson"

    def __str__(self):
        return self.value

def register_ops_args(parser):
    workload_group = parser.add_argument_group("workload")

    workload_group.add_argument(
        "--arrival-process",
        type=ArrivalType,
        choices=list(ArrivalType),
        default=ArrivalType.Uniform,
        help="The process type to approximate for the arrival times of requests",
        )

    workload_group.add_argument(
        "--key-distribution",
        type=KeyType,
        choices=list(KeyType),
        default=KeyType.Uniform,
        help="The distribution of keys",
        )

    workload_group.add_argument(
        "--rate",
        type=float,
        default=100,
        help="rate of requests, defaults to %(default)s",
    )

    workload_group.add_argument(
        "--write-ratio",
        type=float,
        default=1,
        help="percentage of client's write operation, defaults to %(default)s",
    )

    workload_group.add_argument(
        "--create-ratio",
        type=float,
        default=0,
        help="percentage of a CRUD client's create operation (if requested by the system, currently only Kubernetes is CRUD), defaults to %(default)s",
    )

    workload_group.add_argument(
        "--read-ratio",
        type=float,
        default=0.75,
        help="percentage of client's read operation (if requested by the system, currently only Kubernetes is CRUD), defaults to %(default)s",
    )

    workload_group.add_argument(
        "--update-ratio",
        type=float,
        default=0.25,
        help="percentage of client's update operation (if requested by the system, currently only Kubernetes is CRUD), defaults to %(default)s",
    )

    workload_group.add_argument(
        "--delete-ratio",
        type=float,
        default=0,
        help="percentage of client's delete operation (if requested by the system, currently only Kubernetes is CRUD), defaults to %(default)s",
    )

    workload_group.add_argument(
        "--max-key",
        type=int,
        default=1,
        help="maximum size of the integer key, defaults to %(default)s",
    )

    workload_group.add_argument(
        "--payload-size",
        type=int,
        default=10,
        help="upper bound of write operation's payload size in bytes, defaults to %(default)s",
    )

    workload_group.add_argument(
       "--key-gen-seed",
        type=int,
        default=int(time),
        help="The seed used when initializing the RNG for the key generator. Defaults to time().",
    )

    workload_group.add_argument(
       "--arrival-seed",
        type=int,
        default=int(time),
        help="The seed used when initializing the RNG for the arrival process. Defaults to time().",
    )

class Workload(t.AbstractWorkload):
  def __init__(self, keys : t.AbstractKeyGenerator, proc : t.AbstractArrivalProcess):
    self._keys = keys
    self._proc = proc

  @property
  def prerequisites(self) -> List[t.Operation]:
    op_iter = map( 
        lambda op: t.Operation(time=0, payload=op),
        self._keys.prerequisites
        )
    return list(op_iter)

  @property
  def workload(self) -> Iterator[t.WorkloadOperation]:
    operations = self._keys.workload
    arrival_times = self._proc.arrival_times

    op_iter : Iterator[t.Operation] = map(
        lambda op, time: t.Operation(time=time, payload = op),
        operations,
        arrival_times,
    )
    
    # Uniformly distribute requests from and to all clients
    wo_iter : Iterator[t.WorkloadOperation] = zip(
        it.cycle(self.clients),
        op_iter
        )

    return wo_iter

def get_key_provider(args) -> t.AbstractKeyGenerator:
    if args.key_distribution is KeyType.Uniform:
        if args.system_type is s.SystemType.Kubernetes:
            return UniformCRUD(
                op_ratio=(args.create_ratio, args.read_ratio, args.update_ratio, args.delete_ratio),
                max_key=args.max_key,
                rand_seed=args.key_gen_seed if args.key_gen_seed is not None else int(time())
                )
        else:
            return UniformKeys(
                    write_ratio=args.write_ratio,
                    max_key=args.max_key,
                    payload_size=args.payload_size,
                    restrict_RW=args.system is not s.SystemType.Kubernetes,
                    rand_seed=args.key_gen_seed if args.key_gen_seed is not None else int(time())
                    )
    else:
        raise Exception("Not supported key distribution: " + str(args.key_distribution))

def get_arrival_provider(args) -> t.AbstractArrivalProcess:
  if args.arrival_process is ArrivalType.Uniform:
    return UniformArrival(rate = args.rate)
  elif args.arrival_process is ArrivalType.Poisson:
    return PoissonArrival(rate = args.rate, rand_seed=args.arrival_seed if args.arrival_seed is not None else int(time()))
  else:
    raise Exception("Not supported arrival process: " + str(args.key_distribution))

def get_ops_provider(args) -> t.AbstractWorkload:
  keys = get_key_provider(args)
  arrival = get_arrival_provider(args)
  return Workload(keys, arrival)
