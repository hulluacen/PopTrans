package app

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
	"translate-plugin/internal/backend"
)

func TestIdleStopDoesNotInterruptWorkbenchInference(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"status":"ok","translator_ready":true,"busy":true}`)
	}))
	defer server.Close()
	client := backend.NewClient(server.URL)
	app := &App{client: client, supervisor: backend.NewSupervisor(t.TempDir(), client)}
	app.stopBackendForIdleTimeout(time.Minute)
	if app.backendIdleTimer == nil {
		t.Fatal("busy engine was not kept alive")
	}
	app.backendIdleTimer.Stop()
}
