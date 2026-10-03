package main

import (
	"context"
	"io"
	"testing"
	"time"
)

func TestCancelOnEOFStopsWhenTheCallerClosesStdin(t *testing.T) {
	reader, writer := io.Pipe()
	ctx := cancelOnEOF(context.Background(), reader)
	select {
	case <-ctx.Done():
		t.Fatal("cancelled while stdin was still open")
	case <-time.After(50 * time.Millisecond):
	}
	_ = writer.Close()
	select {
	case <-ctx.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("closing stdin did not cancel the operation")
	}
}
