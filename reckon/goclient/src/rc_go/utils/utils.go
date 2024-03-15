package utils

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"io"
	"log"
	"os"
	"sync"
	"time"

	types "github.com/Cjen1/reckon/reckon/goclient/types"
)

func Unix_seconds(t time.Time) float64 {
	return float64(t.UnixNano()) / 1e9
}

func Check(e error, s string) {
	if e != nil {
		log.Fatal("Fatal error: %s: %v", s, e)
	}
}

func Recv(reader *bufio.Reader) types.Jsonmap {
	var size int32
	if err := binary.Read(reader, binary.LittleEndian, &size); err != nil {
		log.Fatal(err)
	}

	payload := make([]byte, size)
	if _, err := io.ReadFull(reader, payload); err != nil {
		log.Fatal(err)
	}

	var msg map[string]interface{}
	json.Unmarshal(payload, &msg)

	return msg

}

func Send(msg types.Jsonmap) {
	payload, err := json.Marshal(msg)
	Check(err, "marshalling json")

	var size int32
	size = int32(len(payload))
	size_part := make([]byte, 4)
	binary.LittleEndian.PutUint32(size_part, uint32(size))

	output := append(size_part[:], payload[:]...)
	_, err = os.Stdout.Write(output)
	Check(err, "writing packet")
}

func Init() {
	log.SetOutput(os.Stderr)
}

func WaitGroupChannel(wg *sync.WaitGroup) <-chan struct{} {
	complete := make(chan struct{})
	go func() {
		wg.Wait()
		close(complete)
	}()
	return complete
}

// Buffering channel, to force delayed clients to quit
func Make_messenger(input <-chan types.Jsonmap, output chan types.Jsonmap) chan struct{} {
	close_this := make(chan struct{})
	go func(messenger_close chan struct{}, input <-chan types.Jsonmap, output chan types.Jsonmap) {
		for {
			select {
			case <-close_this:
				close(output)
				return
			case result := <-input:
				output <- result
			}
		}
	}(close_this, input, output)
	return close_this
}

func Perform_Client_Operation(op func() (string, error), op_type string, clientid string, expected_start float64) types.Jsonmap {
	st := Unix_seconds(time.Now())
	target, err := op()
	end := Unix_seconds(time.Now())

	err_msg := "Success"
	if err != nil {
		err_msg = err.Error()
	}

	resp := types.Response(st, end, err_msg, op_type, clientid, map[string]interface{}{
		"target":         target,
		"expected_start": expected_start,
	})

	return resp
}
