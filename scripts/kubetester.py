import shutil
import sys
sys.path.append('../reckon')


from subprocess import call, Popen, run
import shlex
import itertools as it
import uuid
from datetime import datetime
import json
import os
import numpy as np

from typing import Dict, Any, AnyStr

from reckon.config_loader import *
from reckon.reckon_types import LinkSpec
from pydantic.json import pydantic_encoder
from pydantic import parse_obj_as

import math

from uuid import UUID

def is_valid_uuid(uuid_to_test, version=4):
    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test

def is_valid_timeFormat(input):
    try:
        time.strptime(input, '%Y%m%d%H%M%S')
        return True
    except ValueError:
        return False

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


default_parameters = {
        'system':'kubernetes',
        'client':'go',
        'topo':'simple_k8s',
        'failure':'none',
        'nn':3,
        'nc':1,
        'delay':20,
        'loss':0,
        'jitter':0,
        'ncpr':'False',
        'mtbf':1,
        'kill_n':0,
        'write_ratio': 0,
        'read_ratio': 1,
        'create_ratio': 0,
        'update_ratio': 0,
        'delete_ratio': 0,
        'rate':100,
        'duration':10,
        'tag':'tag',
        'tcpdump':False,
        'arrival_process':'uniform',
        'key_distrib': 'uniform',
        'repeat':-1,
        'failure_timeout':1,
        'delay_interval':0.1,
        'net_spec': '[]',
        'notes':{},
        'variant': 0,
        'light_read':False
        }

completed_test_seeds: list[int] = []

def run_test(folder_path, config : Dict[str, Any]):
    run('rm -rf /data/*', shell=True).check_returncode()
    run('rm -rf /results/logs/*.log.*', shell=True).check_returncode()
    run('mn -c --switch lxbr,stp=1', shell=True).check_returncode()
    #run('pkill client', shell=True)

    uid = uuid.uuid4()

    # Set params
    params = default_parameters.copy()
    for k,v in config.items():
        params[k] = v
    del config

    print(params)

    assert (params['repeat'] != -1)

    result_folder = f"{folder_path}/{uid}/"
    log_path    = result_folder + f"logs"
    config_path = result_folder + f"config.json"
    result_path = result_folder

    cmd = " ".join([
        f"python -m reckon {params['system']} {params['topo']} {params['failure']}",
        f"--number-nodes {params['nn']} --number-clients {params['nc']} --client {params['client']}",
        f"--link-latency {params['delay']} --link-loss {params['loss']} --link-jitter {params['jitter']}",
        f"--new_client_per_request {params['ncpr']}",
        f"--mtbf {params['mtbf']} --kill-n {params['kill_n']}",
        f"--write-ratio {params['write_ratio']}",
        f"--read-ratio {params['read_ratio']}",
        f"--create-ratio {params['create_ratio']}",
        f"--update-ratio {params['update_ratio']}",
        f"--delete-ratio {params['delete_ratio']}",
        f"--rate {params['rate']} --duration {params['duration']}",
        f"--arrival-process {params['arrival_process']}",
        f"--key-distribution {params['key_distrib']}",
        f"--system_logs {log_path} --result-location {result_path} --data-dir=/data",
        f"--failure_timeout {params['failure_timeout']}",
        f"--delay_interval {params['delay_interval']}",
        f"--net-spec \'{params['net_spec']}\'",
        f"--sys_variant {params['variant']}",
        f"--light_reads {params['light_read']}"
        ])

    run(f'mkdir -p {result_folder}', shell=True).check_returncode()
    run(f'mkdir -p {log_path}', shell=True).check_returncode()

    with open(config_path, "w") as of:
        json.dump(params, of)

    print(f"RUNNING TEST")
    print(cmd)

    cmd = shlex.split(cmd)

    retcode = call(cmd)
    if retcode != 0:
        sys.exit(1)

    # Move kubernetes logs out of their location and into the log path
    #run(f'cp -r /results/logs/kubenodes/* {log_path}/', shell=True).check_returncode()

def run_pi4_test_from_config(folder_path, config_full: str, config:str):
    global completed_test_seeds
    run('rm -rf /results/logs/*.log.*', shell=True).check_returncode()
    #run('pkill client', shell=True)

    uid = uuid.uuid4()

    result_folder = f"{folder_path}/{uid}/"
    log_path    = result_folder + f"logs"
    config_path = result_folder + f"config.json"
    result_path = result_folder

    # Load the config file JSON, then give the config as a namespace
    try:
        inconfig: Config = Config.parse_file(config_full)
        net_spec: list[LinkSpec] = []
        with open(config, "r") as conf:
            conf_obj = json.load(conf)
            links: list = conf_obj["links"]
            nodes = {
                "128.232.60.138": "cp",
                "128.232.60.140": "wn",
                "128.232.60.146": "wn2",
                "128.232.60.145": "mc1"
            }
            for link in links:
                net_spec.append(LinkSpec(n_from=nodes[link["node"]], n_to="s1", latency_ms=float(link["delay"]), loss_perc=float(link["loss"]), jitter_ms=float(link["jitter"])))
        
        try:
            idx = completed_test_seeds.index(inconfig.reckonConfig.key_gen_seed)
            if idx >= 0:
                print("Skipping since already performed in previous run...")
                return
        except Exception as e:
            pass

        cmd = " ".join([
            f"python -m reckon kubernetes simple_k8s none",
            f"--number-nodes 3 --number-clients 1 --client go",
            f"--link-latency 2 --link-loss 0 --link-jitter 0",
            f"--new_client_per_request {inconfig.reckonConfig.new_client_per_request}",
            f"--write-ratio {inconfig.reckonConfig.write_ratio}",
            f"--read-ratio {inconfig.reckonConfig.read_ratio}",
            f"--create-ratio {inconfig.reckonConfig.create_ratio}",
            f"--update-ratio {inconfig.reckonConfig.update_ratio}",
            f"--delete-ratio {inconfig.reckonConfig.delete_ratio}",
            f"--rate {inconfig.reckonConfig.rate} --duration {inconfig.reckonConfig.duration}",
            f"--arrival-process {inconfig.reckonConfig.arrival_process}",
            f"--system_logs {log_path} --result-location {result_path} --data-dir=/data",
            f"--failure_timeout {inconfig.reckonConfig.failure_timeout}",
            f"--delay_interval {inconfig.reckonConfig.delay_interval}",
            f"--key-gen-seed {inconfig.reckonConfig.key_gen_seed}",
            f"--arrival-seed {inconfig.reckonConfig.arrival_seed}",
            f"--payload-size {inconfig.reckonConfig.payload_size}",
            f"--key-distribution {inconfig.reckonConfig.key_distribution}",
            f"--max-key {inconfig.reckonConfig.max_key}",
            f"--net-spec \'{json.dumps(net_spec, default=pydantic_encoder)}\'"
            ])

        run(f'mkdir -p {result_folder}', shell=True).check_returncode()
        run(f'mkdir -p {log_path}', shell=True).check_returncode()

        print(f"RUNNING TEST")
        print(cmd)

        #cmd = shlex.split(cmd)

        run(cmd, env=os.environ, shell=True).check_returncode()

        # Compress everything into a nice archive
        #run(f"tar cvJf {result_path}.tar.xz {result_path}", shell=True).check_returncode()
        #run(f"rm -rf {result_path}", shell=True).check_returncode()
    except Exception as e:
        print(e)
        sys.exit(1)

from numpy.random import default_rng
rng = default_rng()

run_time = datetime.now().strftime("%Y%m%d%H%M%S")
folder_path = f"/results/{run_time}"

actions = []

def ha_topo(topo_variant: int, loss_enable=False, loss_variant: int = 0, sys_variant: int = 0): # 0 = DC K8s, 1 = Edgy K8s, with 2 out-of-region workers and 1 in-region, 2 = Edgy K8s all out-of-region, 3 = Full-Edge K8s, with 1 CP+WN per region
    losses = [0, 1]
    if topo_variant != 3:
        net_spec = {
            "cp": {
                "dst": "s1",
                "lat": [0.5, 0.5, 0.5, 0.5] # 500 µs = 0.5 ms. When distributed, cp is in West Europe
            },
            "cp2": {
                "dst": "s1",
                "lat": [0.3, 0.3, 0.3, 83] # When distributed, cp1 is in East US
            },
            "cp3": {
                "dst": "s1",
                "lat": [0.6, 0.6, 0.6, 226] # When distributed, cp1 is in Japan East
            },
            "lb": {
                "dst": "s1",
                "lat": [0.6, 0.6, 0.6, 0.6] # When distributed, lb is colocated with cp
            },
            "wn": {
                "dst": "s1",
                "lat": [0.6, 85, 85, 85], #When distributed, wn is in East US
            },
            "wn2": {
                "dst": "s1",
                "lat": [0.6, 0.6, 146, 146], #When distributed, wn2 is colocated with cp or sent to UK West (same area as cp) or West US if all far apart
            },
            "wn3": {
                "dst": "s1",
                "lat": [0.6, 235, 235, 235], #When distributed, wn3 is in Japan West
            },
            "mc1": {
                "dst": "s1",
                "lat": [0.2, 0.2, 0.2, 0.2] #The load generator is assumed to always be close to the load balancer
            }
        }
    else:
        net_spec = {
            "cp": {
                "dst": "s2",
                "lat": 0.5 # 500 µs = 0.5 ms. When distributed, cp is in West Europe
            },
            "cp2": {
                "dst": "s3",
                "lat": 0.3 # When distributed, cp1 is in East US
            },
            "cp3": {
                "dst": "s4",
                "lat": 0.6 # When distributed, cp1 is in Japan East
            },
            "lb": {
                "dst": "s2",
                "lat": 0.6 # When distributed, lb is colocated with cp
            },
            "wn": {
                "dst": "s2",
                "lat": 1.1 #When distributed, wn is in East US
            },
            "wn2": {
                "dst": "s3",
                "lat": 2.3 #When distributed, wn2 is colocated with cp or sent to UK West (same area as cp) or West US if all far apart
            },
            "wn3": {
                "dst": "s4",
                "lat": 1.5 #When distributed, wn3 is in Japan West
            },
            "mc1": {
                "dst": "s2",
                "lat": 2 #The load generator is assumed to always be close to the load balancer
            },
            "s2": {
                "dst": "s1",
                "lat": 0.2 #s2 and s1 are in the same region (Europe)
            },
            "s3": {
                "dst": "s1",
                "lat": 85 #s3 is in US
            },
            "s4": {
                "dst": "s1",
                "lat": 235, #s4 is in Japan
            },
            "s3": {
                "dst": "s4",
                "lat": 165 #s3 is in US
            }
        }
    
    specs: list[dict] = []
    for link, link_spec in net_spec.items():
        loss = 0
        latency_rtt = link_spec["lat"][topo_variant] if topo_variant != 3 else link_spec["lat"]
        if loss_enable:# and latency_rtt > 5:
            loss = losses[loss_variant]
        specs.append({
            'n_from': link,
            'n_to': link_spec["dst"],
            'latency_ms': latency_rtt * 0.5, # Half the latency since we use RTT latency while Mininet wants Link latency
            'loss_perc': loss,
            'jitter_ms': 0,
        })
    return {
        'topo': 'ha_reg_k8s' if topo_variant == 3 else 'ha_k8s',
        'nn': 6,
        'delay': 0.2,
        'net_spec': json.dumps(specs, cls=NpEncoder),
        'variant': sys_variant
        }

def kubetest(topo_variant: int = 0, loss_variant: int | None = None, avoid_completed: bool = True):
    global folder_path

    systems = ['kubernetes']
    fd_timeouts = [0.01]#[0.01, 0.03]#, 0.06, 0.11, 0.21, 0.41, 0.81]

    low_repeat = 250
    # Modify the repeat if we find completed runs
    if avoid_completed:
        for run in os.listdir(folder_path):
            full_run_path = os.path.join(folder_path, run)
            if os.path.isdir(full_run_path) and is_valid_uuid(run):
                # Load the config JSON and find the seed (if it exists)
                if os.path.exists(os.path.join(full_run_path, "config_full.json")):
                    all_tcpdump_exist = True
                    for subdir in os.listdir(full_run_path):
                        if subdir.find("node") >= 0 and not os.path.exists(os.path.join(full_run_path, subdir, "tcpdump.pcap")):
                            all_tcpdump_exist = False
                            break
                    if os.path.exists(os.path.join(full_run_path, "test_ops.json")) and os.path.exists(os.path.join(full_run_path, "test_resps.json")) and all_tcpdump_exist:
                        low_repeat -= 1
                    else:
                        # The directory is a broken dir! Remove it...
                        print(f"Test directory {full_run_path} is broken! Removing...")
                        shutil.rmtree(full_run_path)
            else:
                # The directory is a broken dir! Remove it...
                print(f"Test directory {full_run_path} is broken! Removing...")
                shutil.rmtree(full_run_path)
    if low_repeat <= 0:
        return

    # steady state erroneous election cost
    for (fd_timeout, repeat) in it.product(
        fd_timeouts,
        range(low_repeat),
        ):
        actions.append(
                lambda params = ha_topo(topo_variant, loss_enable=loss_variant is not None, loss_variant=loss_variant) | {
                    'system':'kubernetes',
                    'rate': 20,
                    'failure_timeout':fd_timeout,
                    'delay_interval': 0.1,
                    'repeat':repeat,
                    'failure':'none',
                    'duration':100,
                    'arrival_process':'poisson'
                    }:
                run_test(folder_path, params)
                )
        
def kubetest_throughput(topo_variant: int = 0):
    global folder_path

    systems = ['kubernetes']
    fd_timeouts = [0.01]#[0.01, 0.03]#, 0.06, 0.11, 0.21, 0.41, 0.81]

    tp_repeat = [5000, 6000, 7000, 8000, 9000]

    # steady state erroneous election cost
    for (fd_timeout, repeat) in it.product(
        fd_timeouts,
        tp_repeat,
        ):
        actions.append(
                lambda params = ha_topo(topo_variant) | {
                    'system':'kubernetes',
                    'rate': repeat,
                    'failure_timeout':fd_timeout,
                    'delay_interval': 0.1,
                    'repeat':1,
                    'failure':'none',
                    'duration':60,
                    'key_distrib':'tptest',
                    'ncpr': 'True'
                    }:
                run_test(folder_path, params)
                )
        
def kubetest_withfailures(topo_variant: int = 0, loss_variant: int | None = None, failure: str = "none", throughput: int = 5000, sys_variant: int = 0):
    global folder_path

    systems = ['kubernetes']
    fd_timeouts = [0.01]#[0.01, 0.03]#, 0.06, 0.11, 0.21, 0.41, 0.81]
    repeats = 20

    # steady state erroneous election cost
    for (fd_timeout, repeat) in it.product(
        fd_timeouts,
        range(repeats),
        ):
        actions.append(
                lambda params = ha_topo(topo_variant, loss_enable=(loss_variant is not None), loss_variant=loss_variant, sys_variant=sys_variant) | {
                    'system':'kubernetes',
                    'rate': throughput,
                    'failure_timeout': fd_timeout,
                    'delay_interval': 0.1,
                    'repeat':repeat,
                    'failure':failure,
                    'duration':60,
                    'key_distrib':'tptest',
                    'ncpr': 'True',
                    'mtbf': 5,
                    'light_read': True
                    }:
                run_test(folder_path, params)
                )

def run_edge_test_from_config(folder_path, config_full: str, config:str, round: int, loss_round: int | None, loss_en = False):
    global completed_test_seeds
    run('rm -rf /results/logs/*.log.*', shell=True).check_returncode()
    #run('pkill client', shell=True)

    uid = uuid.uuid4()

    result_folder = f"{folder_path}/{uid}/"
    log_path    = result_folder + f"logs"
    config_path = result_folder + f"config.json"
    result_path = result_folder

    # Load the config file JSON, then give the config as a namespace
    try:
        inconfig: Config = Config.parse_file(config_full)
        new_topo = ha_topo(round, loss_enable=loss_en, loss_variant=loss_round)
        net_spec = new_topo['net_spec']
        topo_type = new_topo['topo']
        
        try:
            idx = completed_test_seeds.index(inconfig.reckonConfig.key_gen_seed)
            if idx >= 0:
                print("Skipping since already performed in previous run...")
                return
        except Exception as e:
            pass

        cmd = " ".join([
            f"python -m reckon {inconfig.reckonConfig.system_type.value} {topo_type} {inconfig.reckonConfig.failure_type.value}",
            f"--number-nodes {inconfig.reckonConfig.number_nodes} --number-clients {inconfig.reckonConfig.number_clients} --client go",
            f"--link-latency {inconfig.reckonConfig.link_latency} --link-loss {inconfig.reckonConfig.link_loss} --link-jitter {inconfig.reckonConfig.link_jitter}",
            f"--new_client_per_request {inconfig.reckonConfig.new_client_per_request}",
            f"--write-ratio {inconfig.reckonConfig.write_ratio}",
            f"--read-ratio {inconfig.reckonConfig.read_ratio}",
            f"--create-ratio {inconfig.reckonConfig.create_ratio}",
            f"--update-ratio {inconfig.reckonConfig.update_ratio}",
            f"--delete-ratio {inconfig.reckonConfig.delete_ratio}",
            f"--rate {inconfig.reckonConfig.rate} --duration {inconfig.reckonConfig.duration}",
            f"--arrival-process {inconfig.reckonConfig.arrival_process}",
            f"--system_logs {log_path} --result-location {result_path} --data-dir=/data",
            f"--failure_timeout {inconfig.reckonConfig.failure_timeout}",
            f"--delay_interval {inconfig.reckonConfig.delay_interval}",
            f"--key-gen-seed {inconfig.reckonConfig.key_gen_seed}",
            f"--arrival-seed {inconfig.reckonConfig.arrival_seed}",
            f"--payload-size {inconfig.reckonConfig.payload_size}",
            f"--key-distribution {inconfig.reckonConfig.key_distribution}",
            f"--max-key {inconfig.reckonConfig.max_key}",
            f"--net-spec \'{net_spec}\'"
            ])

        run(f'mkdir -p {result_folder}', shell=True).check_returncode()
        run(f'mkdir -p {log_path}', shell=True).check_returncode()

        print(f"RUNNING TEST REPRODUCING PREVIOUS RUNS")
        print(cmd)

        #cmd = shlex.split(cmd)

        run(cmd, env=os.environ, shell=True).check_returncode()

        # Compress everything into a nice archive
        #run(f"tar cvJf {result_path}.tar.xz {result_path}", shell=True).check_returncode()
        #run(f"rm -rf {result_path}", shell=True).check_returncode()
    except Exception as e:
        print(e)
        sys.exit(1)

def kubetest_repro_edge(rootdir: str, round: int, loss_round: int | None = None):
    for run in os.listdir(rootdir):
        full_entry_path = os.path.join(rootdir, run)
        if os.path.isdir(full_entry_path) and is_valid_uuid(run):
            # We found a run config directory. Replicate the experiment
            for config in os.listdir(full_entry_path):
                if config.find(".json") >= 0:
                    config_file_reckon = os.path.join(full_entry_path, "config.json")
                    config_file_params = os.path.join(full_entry_path, "config_full.json")
                    actions.append(lambda params = default_parameters, config_file_params=config_file_params, config_file_reckon=config_file_reckon, round=round, loss_round=loss_round: run_edge_test_from_config(folder_path, config_file_params, config_file_reckon, round, loss_round, loss_en=loss_round is not None))
                    break
        elif full_entry_path.find(".json") >= 0:
            actions.append(lambda params = default_parameters, full_entry_path=full_entry_path, round=round, loss_round=loss_round: run_edge_test_from_config(folder_path, full_entry_path, "", round, loss_round, loss_en=loss_round is not None))

def kubetest_repro_pi4(rootdir: str = "/reckon/to_reproduce"):
    for run in os.listdir(rootdir):
        full_entry_path = os.path.join(rootdir, run)
        if os.path.isdir(full_entry_path) and is_valid_uuid(run):
            # We found a run config directory. Replicate the experiment
            for config in os.listdir(full_entry_path):
                if config.find(".json") >= 0:
                    config_file_reckon = os.path.join(full_entry_path, "config.json")
                    config_file_params = os.path.join(full_entry_path, "config_full.json")
                    actions.append(lambda params = default_parameters, config_file_params=config_file_params, config_file_reckon=config_file_reckon: run_pi4_test_from_config(folder_path, config_file_params, config_file_reckon))
                    break
        elif full_entry_path.find(".json") >= 0:
            actions.append(lambda params = default_parameters, full_entry_path=full_entry_path: run_pi4_test_from_config(folder_path, full_entry_path, ""))

def kubetest_repro_pi4_multi():
    global actions, run_time, folder_path
    i = 0
    batch_total = len(os.listdir("/reckon/to_reproduce"))
    bar = '##################################################'

    for run in os.listdir("/reckon/to_reproduce"):
        full_entry_path = os.path.join("/reckon/to_reproduce", run)
        if os.path.isdir(full_entry_path): # and is_valid_timeFormat(run):
            # We found a run config directory. Replicate the experiment
            run_time = datetime.now().strftime("%Y%m%d%H%M%S")
            folder_path = f"/results/{run_time}"
            actions = []
            kubetest_repro_pi4(rootdir=full_entry_path)

            # Shuffle to isolate ordering effects
            rng.shuffle(actions)

            total = len(actions)
            for j, act in enumerate(actions):
                print(bar, flush=True)
                print(f"BATCH {i+1}/{batch_total}: TEST-{j} out of {total}, {total - j} remaining", flush=True)
                print(bar, flush=True)
                act()

            print(bar, flush=True)
            print(f"BATCH {i+1}/{batch_total}: TESTING DONE", flush=True)
            print(bar, flush=True)
        i += 1
    print(bar, flush=True)
    print(f"TESTING DONE", flush=True)
    print(bar, flush=True)

def load_partial_completed_tests():
    global completed_test_seeds
    for run in os.listdir("/reckon/partial"):
        full_run_path = os.path.join("/reckon/partial", run)
        if os.path.isdir(full_run_path) and is_valid_uuid(run):
            # Load the config JSON and find the seed (if it exists)
            try:
                with open(os.path.join(full_run_path, "config_full.json"), "r") as conf:
                    conf_dict = json.load(conf)
                    seed = conf_dict["reckonConfig"]["key_gen_seed"]
                    all_tcpdump_exist = True
                    for subdir in os.listdir(full_run_path):
                        if subdir.find("node") >= 0 and not os.path.exists(os.path.join(full_run_path, subdir, "tcpdump.pcap")):
                            all_tcpdump_exist = False
                            break
                    if os.path.exists(os.path.join(full_run_path, "test_ops.json")) and os.path.exists(os.path.join(full_run_path, "test_resps.json")) and all_tcpdump_exist:
                        completed_test_seeds.append(seed)
                    else:
                        # The directory is a broken dir! Remove it...
                        print(f"Test directory {full_run_path} is broken! Removing...")
                        shutil.rmtree(full_run_path)
            except Exception as e:
                print(f"Test directory {full_run_path} is broken! Removing...")
                shutil.rmtree(full_run_path)

#kubetest_repro_pi4()

#load_partial_completed_tests()
#kubetest_repro_pi4_multi()

#for loss_variant in range(2):
#    run_time = datetime.now().strftime("%Y%m%d%H%M%S")
#    folder_path = f"/results/perf-eval-final/final-tests/batch1-perf-sys0-topo3-loss{loss_variant}-{run_time}"
#    actions = []
#    kubetest(topo_variant=3, loss_variant=loss_variant)
#    base_folder_path = folder_path
#    # Shuffle to isolate ordering effects
#    rng.shuffle(actions)
#    bar = '##################################################'
#    total = len(actions)
#    for i, act in enumerate(actions):
#        print(bar, flush=True)
#        print(f"TESTING BATCH 1 VARIANT 3 - TEST {i + 1} out of {total}, {total - i - 1} remaining afterwards", flush=True)
#        print(bar, flush=True)
#        act()
#    print(bar, flush=True)
#    print(f"TESTING DONE FOR BATCH 1 VARIANT 3", flush=True)
#    print(bar, flush=True)

base_folder_path = "/results/perf-eval-final/chosen-tp-checks/20240524154916-perf-topo0"
tp_repeat = [[600], [600], [600], [300]]

for sys_variant in [0]:#range(2):
    for variant in [0]:#range(4):
        for repeat in tp_repeat[variant]:
            if variant == 0:
                run_time = datetime.now().strftime("%Y%m%d%H%M%S")
                folder_path = "/results/perf-eval-final/final-newtpmulti-tests/perf-sys0-topo0-none-600-20240701153052"#f"/results/perf-eval-final/final-newtpmulti-tests/perf-sys{sys_variant}-topo{variant}-none-{repeat}-{run_time}"

                actions = []

                kubetest(topo_variant=variant, loss_variant=1)
                #kubetest_withfailures(topo_variant=variant, loss_variant=1, failure="none", throughput=repeat, sys_variant=sys_variant)
                base_folder_path = folder_path

                # Shuffle to isolate ordering effects
                rng.shuffle(actions)

                bar = '##################################################'

                total = len(actions)
                for i, act in enumerate(actions):
                    print(bar, flush=True)
                    print(f"TESTING SYS_VARIANT {sys_variant} VARIANT {variant} REQ. TP {repeat} - TEST {i + 1} out of {total}, {total - i - 1} remaining afterwards", flush=True)
                    print(bar, flush=True)
                    act()

                print(bar, flush=True)
                print(f"TESTING DONE FOR SYS_VARIANT {sys_variant} VARIANT {variant} REQ. TP {repeat}", flush=True)
                print(bar, flush=True)
            else:
                failure_types: list[str] = ["none"]
                if variant != 3:
                    failure_types = ["none", "k8s_wn_offline"]
                else:
                    failure_types = ["none", "k8s_cp_offline", "k8s_wn_offline", "k8s_leadreg_offline"]
                
                for loss_variant in range(2):
                    for failure_type in failure_types:
                        run_time = datetime.now().strftime("%Y%m%d%H%M%S")
                        folder_path = f"/results/perf-eval-final/final-newtpmulti-tests/perf-sys{sys_variant}-topo{variant}-loss{loss_variant}-{failure_type}-{repeat}-{run_time}"

                        actions = []

                        kubetest_withfailures(topo_variant=variant, loss_variant=loss_variant, failure=failure_type, throughput=repeat, sys_variant=sys_variant)
                        #base_folder_path = folder_path

                        # Shuffle to isolate ordering effects
                        rng.shuffle(actions)

                        bar = '##################################################'

                        total = len(actions)
                        for i, act in enumerate(actions):
                            print(bar, flush=True)
                            print(f"TESTING SYS_VARIANT {sys_variant} VARIANT {variant} LOSS {loss_variant} FAILURE {failure_type} REQ. TP {repeat} - TEST {i + 1} out of {total}, {total - i - 1} remaining afterwards", flush=True)
                            print(bar, flush=True)
                            act()

                        print(bar, flush=True)
                        print(f"TESTING SYS_VARIANT {sys_variant} DONE FOR VARIANT {variant} LOSS {loss_variant} FAILURE {failure_type} REQ. TP {repeat}", flush=True)
                        print(bar, flush=True)

# Immediately run the analysis scripts
run("sh /result_analyzer/batch-analyze.sh", shell=True)