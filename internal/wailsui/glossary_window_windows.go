package wailsui

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
	"golang.org/x/sys/windows"
)

func glossaryObjectName(baseDir, suffix string) *uint16 {
	sum := sha256.Sum256([]byte(strings.ToLower(filepath.Clean(baseDir))))
	name, _ := windows.UTF16PtrFromString(fmt.Sprintf("Local\\PopTransGlossary-%x-%s", sum[:12], suffix))
	return name
}

// AcquireGlossaryWindow keeps one manager per installation. A second launch
// wakes the existing manager without touching the translation window.
func AcquireGlossaryWindow(baseDir string) (func(), bool, error) {
	handle, err := windows.CreateMutex(nil, false, glossaryObjectName(baseDir, "mutex"))
	if errors.Is(err, windows.ERROR_ALREADY_EXISTS) {
		windows.CloseHandle(handle)
		for i := 0; i < 20; i++ {
			event, openErr := windows.OpenEvent(windows.EVENT_MODIFY_STATE, false, glossaryObjectName(baseDir, "wake"))
			if openErr == nil {
				windows.SetEvent(event)
				windows.CloseHandle(event)
				break
			}
			time.Sleep(50 * time.Millisecond)
		}
		return func() {}, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return func() { windows.CloseHandle(handle) }, true, nil
}

func (a *App) watchGlossaryWake(ctx context.Context) {
	event, err := windows.CreateEvent(nil, 0, 0, glossaryObjectName(a.baseDir, "wake"))
	if err != nil && !errors.Is(err, windows.ERROR_ALREADY_EXISTS) {
		return
	}
	defer windows.CloseHandle(event)
	for ctx.Err() == nil {
		status, err := windows.WaitForSingleObject(event, 300)
		if err != nil {
			return
		}
		if status == windows.WAIT_OBJECT_0 {
			runtime.WindowUnminimise(ctx)
			runtime.WindowShow(ctx)
		}
	}
}

func (a *App) OpenGlossary() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	cmd := exec.Command(exe, "--glossary")
	cmd.Dir = a.baseDir
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	if err = cmd.Start(); err != nil {
		return errors.New("无法打开术语库窗口")
	}
	return cmd.Process.Release()
}

func (a *App) BeforeClose(ctx context.Context) bool {
	a.mu.Lock()
	block := a.glossaryMode && !a.glossaryClosing
	a.mu.Unlock()
	if block {
		runtime.EventsEmit(ctx, "glossary:request-close")
	}
	return block
}

func (a *App) FinishGlossaryClose() {
	if !a.glossaryMode {
		return
	}
	a.mu.Lock()
	a.glossaryClosing = true
	a.mu.Unlock()
	runtime.Quit(a.ctx)
}
