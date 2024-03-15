package rc_go

import (
	"fmt"
	"os"

	types "github.com/Cjen1/reckon/reckon/goclient/types"
	utils "github.com/Cjen1/reckon/reckon/goclient/utils"
)

type KVSClient interface {
	types.AbstractClient
	Put(k string, v string) (string, error)
	Get(k string) (string, string, error)
}

type RC_KVS_Client struct{}

func put(cli KVSClient, key string, value string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		return cli.Put(key, value)
	}, "write", clientid, expected_start)
}

func get(cli KVSClient, key string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		_, target, err := cli.Get(key)
		return target, err
	}, "read", clientid, expected_start)
}

func (RC_KVS_Client) Perform(op types.Operation, cli types.AbstractClient, clientid string, test_start_time float64, new_client_per_request bool, client_gen func() (types.AbstractClient, error)) types.Jsonmap {
	//Create a new client if desired
	cli_is_kvs := false
	switch cli.(type) {
	case KVSClient:
		cli_is_kvs = true
	default:
		break
	}
	if !cli_is_kvs {
		fmt.Fprintf(os.Stderr, "Error: Attempting to use KVS Client without a KVS client being generated\n")
		os.Exit(1)
	}

	cli_kvs := cli.(KVSClient)
	func_cli := &cli_kvs
	if new_client_per_request {
		cli, err := client_gen()
		utils.Check(err, "generating client")
		defer cli.Close()
		func_cli = &cli_kvs
	}

	expected_start := op.Time + test_start_time
	switch op.Payload["kind"] {
	case "write":
		return put(*func_cli, op.Payload["key"], op.Payload["value"], clientid, expected_start)
	case "read":
		return get(*func_cli, op.Payload["key"], clientid, expected_start)
	default:
		return types.Response(
			-1.0,
			-1.0,
			fmt.Sprintf("Error operation (%v) was not found or supported", op),
			op.Payload["kind"],
			clientid,
			nil)
	}
}

func (kvs RC_KVS_Client) Run(client_gen func() (types.AbstractClient, error), clientid string, new_client_per_request bool) {
	Run_Client(kvs, client_gen, clientid, new_client_per_request)
}
