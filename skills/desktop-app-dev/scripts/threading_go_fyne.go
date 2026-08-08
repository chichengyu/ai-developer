// Fyne v2.4+ background work with cancellation + progress + safe UI bridge.
//
// `fyne.Do` posts a function to the UI goroutine; worker goroutines must
// never call widget methods directly.
//
// Usage:
//   controller := &JobController{
//       onProgress: func(p float64) { progressBar.SetValue(p) },
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

	"fyne.io/fyne/v2"
)

type JobController struct {
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
				fyne.Do(func() { c.onError(err) })
			}
		}()
		for step := 1; step <= total; step++ {
			if c.cancel.Load() {
				if c.onCancel != nil {
					fyne.Do(c.onCancel)
				}
				return
			}
			if c.onProgress != nil {
				percent := float64(step) / float64(total)
				fyne.Do(func() { c.onProgress(percent) })
			}
			time.Sleep(50 * time.Millisecond)
		}
		if c.onDone != nil {
			fyne.Do(func() { c.onDone(total) })
		}
	}()
}

func (c *JobController) Cancel() {
	c.cancel.Store(true)
}
