package rc_go

import (
	"fmt"
	"os"

	types "github.com/Cjen1/reckon/reckon/goclient/types"
	utils "github.com/Cjen1/reckon/reckon/goclient/utils"
)

type CRUDClient interface {
	types.AbstractClient
	Create(k string, v string) (string, error)
	Read(k string) (string, string, error)
	Update(k string, v string) (string, error)
	Delete(k string) (string, error)
}

type RC_CRUD_Client struct{}

func create(cli CRUDClient, key string, value string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		return cli.Create(key, value)
	}, "create", clientid, expected_start)
}

func read(cli CRUDClient, key string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		_, target, error := cli.Read(key)
		return target, error
	}, "read", clientid, expected_start)
}

func update(cli CRUDClient, key string, value string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		return cli.Update(key, value)
	}, "update", clientid, expected_start)
}

func delete(cli CRUDClient, key string, clientid string, expected_start float64) types.Jsonmap {
	return utils.Perform_Client_Operation(func() (string, error) {
		return cli.Delete(key)
	}, "delete", clientid, expected_start)
}

func (RC_CRUD_Client) Perform(op types.Operation, cli types.AbstractClient, clientid string, test_start_time float64, new_client_per_request bool, client_gen func() (types.AbstractClient, error)) types.Jsonmap {
	//Create a new client if desired
	cli_is_crud := false
	switch cli.(type) {
	case CRUDClient:
		cli_is_crud = true
	default:
		break
	}
	if !cli_is_crud {
		fmt.Fprintf(os.Stderr, "Error: Attempting to use CRUD Client without a CRUD client being generated\n")
		os.Exit(1)
	}

	cli_kvs := cli.(CRUDClient)
	func_cli := &cli_kvs
	if new_client_per_request {
		cli, err := client_gen()
		utils.Check(err, "generating client")
		defer cli.Close()
		func_cli = &cli_kvs
	}

	expected_start := op.Time + test_start_time
	switch op.Payload["kind"] {
	case "create":
		return create(*func_cli, op.Payload["key"], op.Payload["value"], clientid, expected_start)
	case "read":
		return read(*func_cli, op.Payload["key"], clientid, expected_start)
	case "update":
		return update(*func_cli, op.Payload["key"], op.Payload["value"], clientid, expected_start)
	case "delete":
		return delete(*func_cli, op.Payload["key"], clientid, expected_start)
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

func (crud RC_CRUD_Client) Run(client_gen func() (types.AbstractClient, error), clientid string, new_client_per_request bool) {
	Run_Client(crud, client_gen, clientid, new_client_per_request)
}
