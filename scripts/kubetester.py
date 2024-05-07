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
        'repeat':-1,
        'failure_timeout':1,
        'delay_interval':0.1,
        'net_spec': '[]',
        'notes':{},
        }

def run_test(folder_path, config : Dict[str, Any]):
    run('rm -rf /data/*', shell=True).check_returncode()
    run('rm -rf /results/logs/*.log.*', shell=True).check_returncode()
    run('mn -c', shell=True).check_returncode()
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
        f"--system_logs {log_path} --result-location {result_path} --data-dir=/data",
        f"--failure_timeout {params['failure_timeout']}",
        f"--delay_interval {params['delay_interval']}",
        f"--net-spec \'{params['net_spec']}\'"
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
    run(f'cp /results/logs/kubenodes/* {log_path}/', shell=True).check_returncode()

def run_pi4_test_from_config(folder_path, config_full: str, config:str):
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

def kubetest():
    systems = ['kubernetes']
    fd_timeouts = [0.01, 0.03]#, 0.06, 0.11, 0.21, 0.41, 0.81]

    low_repeat = 10
    high_repeat = 50

    base_latencies = np.array([10, 20, 30, 50])
    per_test_deltas = np.array([10, 5, 10, 2])

    def simple_topo(latencies: tuple[float, float, float, float]):
        links = ["cp", "wn", "wn2", "mc1"]
        specs: list[dict] = []
        i = 0
        for latency in latencies:
            specs.append({
                'n_from': links[i],
                'n_to': "sw",
                'latency_ms': latency,
                'loss_perc': 0,
                'jitter_ms': 0,
            })
        return {
            'topo':'simple_k8s',
            'nn': 3,
            'delay': 50,
            'net_spec': json.dumps(specs, cls=NpEncoder)
            }

    # steady state erroneous election cost
    last_latencies = np.subtract(base_latencies, per_test_deltas)
    for (fd_timeout, repeat) in it.product(
        fd_timeouts,
        range(low_repeat),
        ):
        last_latencies = np.add(last_latencies, per_test_deltas)
        actions.append(
                lambda params = simple_topo(tuple(last_latencies)) | {
                    'system':'kubernetes',
                    'rate': 100,
                    'failure_timeout':fd_timeout,
                    'delay_interval': 0.1,
                    'repeat':repeat,
                    'failure':'none',
                    'duration':10,
                    }:
                run_test(folder_path, params)
                )

def kubetest_repro_pi4(rootdir: str = "/reckon/to_reproduce"):
    for run in os.listdir(rootdir):
        full_entry_path = os.path.join(rootdir, run)
        if os.path.isdir(full_entry_path) and is_valid_uuid(run):
            # We found a run config directory. Replicate the experiment
            for config in os.listdir(full_entry_path):
                if config.find(".json") >= 0:
                    config_file_reckon = os.path.join(full_entry_path, "config.json")
                    config_file_params = os.path.join(full_entry_path, "config_full.json")
                    actions.append(lambda params = default_parameters: run_pi4_test_from_config(folder_path, config_file_params, config_file_reckon))
                    break
        elif full_entry_path.find(".json") >= 0:
            actions.append(lambda params = default_parameters: run_pi4_test_from_config(folder_path, full_entry_path, ""))

def kubetest_repro_pi4_multi():
    global actions, run_time, folder_path
    i = 0
    bar = '##################################################'
    batch_total = len(os.listdir("/reckon/to_reproduce"))
    for run in os.listdir("/reckon/to_reproduce"):
        full_entry_path = os.path.join("/reckon/to_reproduce", run)
        if os.path.isdir(full_entry_path) and is_valid_timeFormat(run):
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
    print(bar, flush=True)
    print(f"TESTING DONE", flush=True)
    print(bar, flush=True)

#kubetest_repro_pi4()

kubetest_repro_pi4_multi()

#kubetest()

# Shuffle to isolate ordering effects
#rng.shuffle(actions)
#
#bar = '##################################################'
#
#total = len(actions)
#for i, act in enumerate(actions):
#    print(bar, flush=True)
#    print(f"TEST-{i} out of {total}, {total - i} remaining", flush=True)
#    print(bar, flush=True)
#    act()
#
#print(bar, flush=True)
#print(f"TESTING DONE", flush=True)
#print(bar, flush=True)
