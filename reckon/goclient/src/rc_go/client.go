package rc_go

import (
	"bufio"
	"log"
	"os"
	"sync"
	"time"

	types "github.com/Cjen1/reckon/reckon/goclient/types"
	utils "github.com/Cjen1/reckon/reckon/goclient/utils"
)

func result_loop(res_ch chan types.Jsonmap, done chan struct{}) {
	var results []types.Jsonmap
	log.Print("Starting result loop")
	for res := range res_ch {
		results = append(results, res)
	}

	log.Print("Got all results, writing to load generator")
	for _, res := range results {
		utils.Send(res)
	}
	close(done)
}

func Run_Client(client types.Client, client_gen func() (types.AbstractClient, error), clientid string, new_client_per_request bool) {
	log.Print("Client: Starting run")

	cli, err := client_gen()
	defer cli.Close()
	utils.Check(err, "create client")

	reader := bufio.NewReader(os.Stdin)

	//Phase 1: preload
	log.Print("Phase 1: preload")
	var ops []types.Operation
	preloads := make([]map[string]interface{}, 0)
	got_finalise := false
	for !got_finalise {
		op := utils.Recv(reader)

		switch op["kind"] {
		case "preload":
			preload := types.Decode_preload(op)
			if preload.Prereq {
				preload_res := client.Perform(preload.Operation, cli, clientid, utils.Unix_seconds(time.Now()), false, client_gen)
				preloads = append(preloads, preload_res)
			} else {
				ops = append(ops, preload.Operation)
			}
		case "finalise":
			got_finalise = true
		default:
			log.Print("Got unrecognised message...")
			log.Print(op)
			log.Fatal("Quitting due to unrecognised message")
		}
	}

	//Phase 2: Readying
	log.Print("Phase 2: Readying")

	//Dispatch results loop
	final_res_ch := make(chan types.Jsonmap)
	results_complete := make(chan struct{})
	go result_loop(final_res_ch, results_complete)
	res_ch := make(chan types.Jsonmap, 50000)
	messenger_complete := utils.Make_messenger(res_ch, final_res_ch)

	//signal ready
	log.Print("Sending ready")
	utils.Send(map[string]interface{}{"kind": "ready"})
	log.Print("Sent ready")

	got_start := false
	for !got_start {
		op := utils.Recv(reader)
		switch op["kind"] {
		case "start":
			log.Print("Got start_request")
			got_start = true
		default:
			log.Fatal("Got a message which wasn't a start!")
		}
	}

	//Phase 3: Execute
	log.Print("Phase 3: Execute")
	log.Print("Phase 3.1: Sending all Prereq results")
	for _, prereq_res := range preloads {
		res_ch <- prereq_res
	}
	log.Print("Phase 3.2: Executing true ops")
	var wg_perform sync.WaitGroup
	stopCh := make(chan struct{})
	op_ch := make(chan types.Operation)
	log.Print("Starting to perform ops")
	start_time := time.Now()
	for _, op := range ops {
		end_time := start_time.Add(time.Duration(op.Time * float64(time.Second)))
		t := time.Now()
		time.Sleep(end_time.Sub(t))

		select {
		case op_ch <- op:
			continue
		default:
			wg_perform.Add(1)
			//If can't start op currently create a new worker to do so
			go func(op_ch <-chan types.Operation, wg *sync.WaitGroup) {
				defer wg.Done()
				for op := range op_ch {
					resp := client.Perform(op, cli, clientid, utils.Unix_seconds(start_time), new_client_per_request, client_gen)
					select {
					case <-stopCh:
						continue
					case res_ch <- resp:
					}
				}
			}(op_ch, &wg_perform)
			op_ch <- op
		}
	}
	log.Print("Finished sending ops")
	log.Print("Phase 4: Collate")

	// Tell threads that there are no more ops
	close(op_ch)

	select {
	case <-utils.WaitGroupChannel(&wg_perform):
	case <-time.After(30 * time.Second):
	}

	// Cut off trailing results
	close(stopCh)

	log.Print("Closing result pipe")
	//Signal end of results and force any remaining clients to not write to it
	close(messenger_complete)

	log.Print("Waiting for results to be sent")
	//Wait for results to be returned to generator
	<-results_complete
	utils.Send(map[string]interface{}{"kind": "finished"})
	log.Print("Results sent, exiting")
}
