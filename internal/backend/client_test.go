package backend

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTranslationTimeoutAllowsLargerModels(t *testing.T) {
	client := NewClient("http://127.0.0.1:0")
	if client.httpClient.Timeout != TranslationTimeout || TranslationTimeout <= 35*time.Second {
		t.Fatal("translation still uses the old short timeout")
	}
}

func TestTranslateStillHonorsCallerCancellation(t *testing.T) {
	done := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-done }))
	defer server.Close()
	defer close(done)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	_, err := NewClient(server.URL).Translate(ctx, "test")
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected caller timeout, got %v", err)
	}
}
