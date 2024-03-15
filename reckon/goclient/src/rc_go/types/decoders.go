package types

import "log"

func Decode_operation(m Jsonmap) Operation {
	var res Operation
	payload := make(map[string]string)
	for key, value := range m {
		switch key {
		case "payload":
			for k, v := range value.(map[string]interface{}) {
				payload[k] = v.(string)
			}
			res.Payload = payload
		case "time":
			res.Time = value.(float64)
		default:
			log.Fatal("Cannot parse operation: %v", m)
			panic("Failed to parse packet")
		}

	}
	return res
}

func Decode_preload(m Jsonmap) Preload {
	var res Preload
	for key, value := range m {
		switch key {
		case "prereq":
			res.Prereq = value.(bool)
		case "operation":
			res.Operation = Decode_operation(value.(Jsonmap))
		case "kind":
		default:
			log.Fatal("Cannot parse preload: %v", m)
			panic("Failed to parse packet")
		}
	}
	return res
}
