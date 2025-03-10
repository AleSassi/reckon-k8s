from enum import Enum
from reckon.failures.leader import LeaderFailure
from reckon.failures.leader_only import LeaderOnlyFailure
from reckon.failures.none import NoFailure
from reckon.failures.partialpartition import PPartitionFailure
from reckon.failures.intermittent_partial import IntermittentPPartitionFailure
from reckon.failures.intermittent_full import IntermittentFPartitionFailure
from reckon.failures.k8s_worker_offline import IntermittentWorkerOfflineFailure
from reckon.failures.k8s_control_offline import IntermittentControlOfflineFailure
from reckon.failures.k8s_leader_region_offline import LeaderRegionOfflineFaultFailure
from reckon.failures.kill_n import KillN
from reckon.failures.stat import StatFault

import reckon.reckon_types as t


class FailureType(Enum):
    FNone = "none"
    FLeaderOnly = "leader"
    FLeaderRecovery = "leader-recovery"
    FPartialPartition = "partial-partition"
    FIntermittentPP = "intermittent-partial"
    FIntermittentFP = "intermittent-full"
    FK8sControlOffline = "k8s_cp_offline"
    FK8sWorkerOffline = "k8s_wn_offline"
    FK8sRegionOffline = "k8s_leadreg_offline"
    FKillN = "kill-n"
    Stat = "stat"

    def __str__(self):
        return self.value


def register_failure_args(parser):
    dist_group = parser.add_argument_group("failures")

    dist_group.add_argument("failure_type", type=FailureType, choices=list(FailureType))

    dist_group.add_argument("--mtbf", type=float, default=1)

    dist_group.add_argument("--kill-n", type=int, default=0)


def get_failure_provider(args) -> t.AbstractFailureGenerator:
    if args.failure_type is FailureType.FNone:
        return NoFailure()
    elif args.failure_type is FailureType.FLeaderRecovery:
        return LeaderFailure()
    elif args.failure_type is FailureType.FLeaderOnly:
        return LeaderOnlyFailure()
    elif args.failure_type is FailureType.FPartialPartition:
        return PPartitionFailure()
    elif args.failure_type is FailureType.FIntermittentPP:
        return IntermittentPPartitionFailure(args.mtbf)
    elif args.failure_type is FailureType.FIntermittentFP:
        return IntermittentFPartitionFailure(args.mtbf)
    elif args.failure_type is FailureType.FK8sWorkerOffline:
        return IntermittentWorkerOfflineFailure(args.mtbf)
    elif args.failure_type is FailureType.FK8sControlOffline:
        return IntermittentControlOfflineFailure(args.mtbf)
    elif args.failure_type is FailureType.FK8sRegionOffline:
        return LeaderRegionOfflineFaultFailure()
    elif args.failure_type is FailureType.FKillN:
        return KillN(args.kill_n)
    elif args.failure_type is FailureType.Stat:
        return StatFault()
    else:
        raise Exception("Not supported failure type: " + str(args.dist_type))
