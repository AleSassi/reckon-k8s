import argparse
from pathlib import Path
import sys

from reckon.client_runner import run_test
from reckon.workload   import register_ops_args,     get_ops_provider, ArrivalType, KeyType
from reckon.failures   import register_failure_args, get_failure_provider, FailureType
from reckon.topologies import register_topo_args,    get_topology_provider, TopologyType
from reckon.systems    import register_system_args,  get_system, SystemType
from reckon.config_loader import Config, GitInfo

import logging, time, os

import json, git

logging.basicConfig(
  format="%(asctime)s %(message)s", datefmt="%I:%M:%S %p", level=logging.DEBUG
)

class ArgsEncoder(json.JSONEncoder):
  def default(self, obj):
    if isinstance(obj, ArrivalType):
        return str(obj)
    if isinstance(obj, KeyType):
        return str(obj)
    if isinstance(obj, TopologyType):
        return str(obj)
    if isinstance(obj, SystemType):
        return str(obj)
    if isinstance(obj, FailureType):
        return str(obj)
    return super(ArgsEncoder, self).default(obj)

if __name__ == "__main__":
    # ------- Parse arguments --------------------------
    parser = argparse.ArgumentParser(
        description="Runs a benchmark of a local fault tolerant datastore"
    )
    parser.add_argument("--config", type=str, default="", help="The full config file to load arguments from", required=False)

    register_system_args(parser)
    register_topo_args(parser)
    register_ops_args(parser)
    register_failure_args(parser)

    arg_group = parser.add_argument_group("benchmark")
    arg_group.add_argument("-d", action="store_true", help="Debug mode")
    arg_group.add_argument("--duration", type=float, default=60)
    arg_group.add_argument("--result-location", default="/results/")

    args = parser.parse_args()

    # Load the config file JSON, then give the config as a namespace
    try:
      inconfig: Config = Config.parse_file(args.config)
      for attr, val in vars(args).items():
        if hasattr(inconfig.reckonConfig, attr) and val == parser.get_default(attr):
          setattr(args, attr, getattr(inconfig.reckonConfig, attr))
      try:
        repo = git.Repo(search_parent_directories=True)
        commit_sha = repo.head.commit.hexsha
        head_sha = repo.head.object.hexsha
        in_commit_sha = inconfig.gitInfo.commit_sha
        in_head_sha = inconfig.gitInfo.head_sha
        if commit_sha != in_commit_sha or head_sha != in_head_sha:
          logging.warning(f"you are using a version of Reckon which is not the one used to generate the supplied config file. To be sure you are obtaining the same results as the experiment of this config file, please use the version with commit ref {in_commit_sha} and head ref {in_head_sha}.")
      except Exception:
        commit_sha = "None"
        head_sha = "None"
    except Exception:
      pass

    print(f"Args = {args}")

    # Write the full args config to disk
    with open(os.path.join(args.result_location, "config_full.json"), "w") as outconf:
      confdict = Config(reckonConfig=vars(args), gitInfo=GitInfo.create())
      outconf.write(confdict.json())

    if args.d:
        from mininet.cli import CLI

        system = get_system(args)
        topo_provider = get_topology_provider(args)
        failure_provider = get_failure_provider(args)
        ops_provider = get_ops_provider(args)

        net, cluster, _ = topo_provider.setup()

        _, _, killers = system.start_nodes(cluster)

        CLI(net)

        for stopper in killers.values():
            stopper()
    else:
        stoppers = {}
        killers = {}
        try:
          system = get_system(args)
          topo_provider = get_topology_provider(args)
          failure_provider = get_failure_provider(args)
          ops_provider = get_ops_provider(args)

          net, cluster, clients = get_topology_provider(args).setup()

          restarters, stoppers_prime, killers = system.start_nodes(cluster)
          stoppers = stoppers_prime

          failures = failure_provider.get_failures(cluster, system, restarters, stoppers)

          print("BENCHMARK: testing connectivity, and allowing network to settle")
          if str(os.environ["NETSIM_RUNTIME"]) == "containernet":
            print("Waiting 60s for the network to start up and settle...")
            time.sleep(60) # Sleeping for some time allows all COntainernet hosts to start up
          print("Pinging all hosts")
          net.pingAll()

          print("BENCHMARK: Starting Test")

          from multiprocessing import Process

          p = Process(target = run_test, args=(
              args.result_location,
              clients,
              ops_provider,
              args.duration,
              system,
              cluster,
              failures,
          ))
          p.start()
          p.join(max(args.duration * 10, 600))
          p.terminate()
        except Exception as e:
          print(e)
          for stopper in killers.values():
              stopper()
          sys.exit(1)
        finally:
          for stopper in killers.values():
              stopper()
          logging.info("Finished Test")
