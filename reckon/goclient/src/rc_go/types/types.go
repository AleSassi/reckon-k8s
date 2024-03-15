package types

type Jsonmap = map[string]interface{}

type Operation struct {
	Payload map[string]string `json:"payload"`
	Time    float64           `json:"time"`
}

type Preload struct {
	Prereq    bool      `json:"prereq"`
	Operation Operation `json:"operation"`
}

type Client interface {
	Perform(op Operation, cli AbstractClient, clientid string, test_start_time float64, new_client_per_request bool, client_gen func() (AbstractClient, error)) Jsonmap
	Run(client_gen func() (AbstractClient, error), clientid string, new_client_per_request bool)
}

type AbstractClient interface {
	Close()
}

func Response(
	t_submitted float64,
	t_result float64,
	result string,
	kind string,
	clientid string,
	other Jsonmap) Jsonmap {
	return map[string]interface{}{
		"kind":        "result",
		"t_submitted": t_submitted,
		"t_result":    t_result,
		"result":      result,
		"op_kind":     kind,
		"clientid":    clientid,
		"other":       other,
	}
}
