import json
import logging
import subprocess
from threading import Thread
import time
import sys
import selectors
import itertools as it

from typing import List, Tuple
import itertools as it

import reckon.reckon_types as t

from tqdm import tqdm


def preload(ops_provider: t.AbstractWorkload, duration: float) -> Tuple[int, list[dict]]:
    logging.debug("PRELOAD: begin")

    ops_log: list[dict] = []
    for op, client in zip(ops_provider.prerequisites, it.cycle(ops_provider.clients)):
        rcclient: t.Client = client
        ops_log.append({
            "operation": op.json(),
            "type": "prereq",
            "client": rcclient.id
        })
        client.send(t.preload(prereq=True, operation=op))

    sim_t = 0
    total_reqs = 0
    with tqdm(total=duration) as pbar:
        for client, op in ops_provider.workload:
            if op.time >= duration:
                break

            total_reqs += 1
            ops_log.append({
                "operation": op.json(),
                "type": "req",
                "client": rcclient.id
            })
            client.send(t.preload(prereq=False, operation=op))

            pbar.update(op.time - sim_t)
            sim_t = op.time

    for client in ops_provider.clients:
        client.send(t.finalise())

    logging.debug("PRELOAD: end")
    return total_reqs, ops_log


def ready(clients: List[t.Client]):
    logging.debug("READY: begin")

    sel = selectors.DefaultSelector()

    for i, cli in enumerate(clients):
        cli.register_selector(sel, selectors.EVENT_READ, i)

    for _ in range(len(clients)):
        i = sel.select()[0][0].data

        msg = clients[i].recv()
        assert msg.__root__.kind == "ready"

    logging.debug("READY: end")

def sleep_til(x):
    diff = x - time.time() 
    if diff > 0:
        time.sleep(diff)

def roundrobin(*iterables):
    from itertools import cycle, islice
    "roundrobin('ABC', 'D', 'EF') --> A D E B F C"
    # Recipe credited to George Sakkis
    num_active = len(iterables)
    nexts = cycle(iter(it).__next__ for it in iterables)
    while num_active:
        try:
            for next in nexts:
                yield next()
        except StopIteration:
            # Remove the iterator we just exhausted from the cycle.
            num_active -= 1
            nexts = cycle(islice(nexts, num_active))

def execute(clients: List[t.Client], failures: List[t.AbstractFault], duration: float):
    logging.debug("EXECUTE: begin")
    assert(len(failures) >= 2) # fence pole style, one at start, one at end, some in the middle

    sleep_dur = duration / (len(failures) - 1)

    start_time = time.time()

    fault_times = [start_time + i * sleep_dur for i, _ in enumerate(failures)]
    sleep_funcs = [lambda t=t: sleep_til(t) for t in fault_times][1:]
    fault_funcs = [lambda f=f: f.apply_fault() for f in failures]

    for client in clients:
        client.send(t.start())

    for f in roundrobin(fault_funcs, sleep_funcs): # alternate between sleeping and 
        f()

    logging.debug("EXECUTE: end")

def collate(clients: List[t.Client], total_reqs: int) -> t.Results:
    logging.debug("COLLATE: begin")

    sel = selectors.DefaultSelector()

    for i, client in enumerate(clients):
        client.register_selector(sel, selectors.EVENT_READ, i)

    resps = []
    remaining_clients = len(clients)
    print(f"rem_cli: {remaining_clients}")
    with tqdm(total=total_reqs, desc="Results") as pbar: # TODO: Check if total_reqs has to consider also preload requests!
        while remaining_clients > 0:
            i = sel.select()[0][0].data
            msg = clients[i].recv()
            if msg.__root__.kind == "finished":
                remaining_clients -= 1
                clients[i].unregister_selector(sel, selectors.EVENT_READ)
            elif msg.__root__.kind == "result":
                pbar.update(1)
                assert type(msg.__root__) is t.Result
                resps.append(msg.__root__)
            else:
                print(f"Unexpected message: |{msg}|")
    print("finished collate")
    return t.Results(__root__=resps)


def test_steps(
    clients: List[t.Client],
    workload: t.AbstractWorkload,
    failures: List[t.AbstractFault],
    duration: float,
) -> Tuple[t.Results, list[dict]]:

    assert(len(failures) >= 2)

    workload.clients = clients
    total_reqs, req_log = preload(workload, duration)
    ready(clients)

    t_execute = Thread(
        target=execute,
        args=[clients, failures, duration],
    )
    t_execute.daemon = True
    t_execute.start()

    resps = collate(clients, total_reqs)

    t_execute.join()

    return resps, req_log


def run_test(
    test_results_location: str,
    mininet_clients: List[t.MininetHost],
    ops_provider: t.AbstractWorkload,
    duration: int,
    system: t.AbstractSystem,
    cluster: List[t.MininetHost],
    failures: List[t.AbstractFault],
):
    duration = int(duration)

    logging.debug("Setting up clients")
    sys.stdout.flush()
    clients = [
        system.start_client(client, str(client_id), cluster)
        for client_id, client in enumerate(mininet_clients)
    ]
    logging.debug("Microclients started")

    pre_res = system.prepare_test_start(cluster=cluster)

    resps, req_log = test_steps(clients, ops_provider, failures, duration)
    resps.__root__.insert(0, pre_res)

    logging.debug(f"COLLATE: received, writing to {test_results_location}")
    with open(f"{test_results_location}/test_resps.json", "w") as fres:
        fres.write(resps.json())
    with open(f"{test_results_location}/test_ops.json", "w") as fres:
        fres.write(json.dumps(req_log))
    #kubecluster: list[str] = [c.IP() for c in cluster]
    #idx = 0
    logging.debug("COLLATE: collecting logs from cluster machines")
    for node in cluster:
        node.cmd("pkill -15 tcpdump", verbose=True)
        node.cmd("while pkill -0 tcpdump 2> /dev/null; do sleep 1; done;", verbose=True)
    subprocess.run(f"cp -r /results/logs/kubenodes/* {test_results_location}/", shell=True).check_returncode()
    subprocess.run(f"cp -r /results/logs/*.err {test_results_location}/", shell=True).check_returncode()
    logging.debug("COLLATE: end")
