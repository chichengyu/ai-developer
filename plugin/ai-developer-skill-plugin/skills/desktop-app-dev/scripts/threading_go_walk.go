// walk (Go Win32) background work with cancellation + progress + safe UI bridge.
//
// Worker goroutines post updates with `MainWindow.RunSafe`, which executes
// the callback on the window's UI thread.
//
// Usage:
//   controller := &JobController{
//       window:    mainWindow,
//       onProgress: func(p float64) { progressBar.SetValue(int(p * 100)) },
//       onDone:     func(result int) { status.SetText(fmt.Sprintf("done: %d", result)) },
//       onError:    func(err error) { status.SetText("error: " + err.Error()) },
//       onCancel:   func() { status.SetText("cancelled") },
//   }
//   controller.Start(100)
//   // later: controller.Cancel()

package main

import (
	"fmt"
	"sync/atomic"
	"time"

	"github.com/lxn/walk"
)

type JobController struct {
	window    *walk.MainWindow
	onProgress func(float64)
	onDone     func(int)
	onError    func(error)
	onCancel   func()
	cancel     atomic.Bool
}

func (c *JobController) Start(total int) {
	c.cancel.Store(false)
	go func() {
		defer func() {
			if recovered := recover(); recovered != nil && c.onError != nil {
				err, _ := recovered.(error)
				if err == nil {
					err = fmt.Errorf("job panic: %v", recovered)
				}
				c.window.RunSafe(func() { c.onError(err) })
			}
		}()
		for step := 1; step <= total; step++ {
			if c.cancel.Load() {
				if c.onCancel != nil {
					c.window.RunSafe(c.onCancel)
				}
				return
			}
			if c.onProgress != nil {
				percent := float64(step) / float64(total)
				c.window.RunSafe(func() { c.onProgress(percent) })
			}
			time.Sleep(50 * time.Millisecond)
		}
		if c.onDone != nil {
			c.window.RunSafe(func() { c.onDone(total) })
		}
	}()
}

func (c *JobController) Cancel() {
	c.cancel.Store(true)
}
