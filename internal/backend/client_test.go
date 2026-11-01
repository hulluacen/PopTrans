package backend

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTranslationPreservesReferenceCandidates(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"choices":[{"message":{"content":"译文"}}],"glossary_info":{"enabled":true,"groups":[{"source":"web","candidates":[{"target":"薄膜","context":"材料"},{"target":"网页","context":"浏览器"}]}],"omitted":2}}`)
	}))
	defer server.Close()
	result, info, err := NewClient(server.URL).TranslateWithInfo(context.Background(), "web")
	if err != nil || result != "译文" || !info.Enabled || info.Omitted != 2 || len(info.Groups) != 1 || len(info.Groups[0].Candidates) != 2 {
		t.Fatalf("lost response reference info: %q %+v %v", result, info, err)
	}
}

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
