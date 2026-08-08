// Wails v2 background work with cancellation + progress + safe UI bridge.
//
// The goroutine never touches frontend objects. Every event is emitted
// through Wails runtime, which marshals it to the renderer event bus.
//
// Usage (in a Wails service):
//   type App struct { jobs *JobController }
//   func (a *App) Startup(ctx context.Context) { a.jobs.ctx = ctx }
//   func (a *App) StartJob(total int) { a.jobs.Start(total) }
//   func (a *App) CancelJob() { a.jobs.Cancel() }

package main

import (
	"context"
	"fmt"
	"sync/atomic"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

type JobController struct {
	ctx    context.Context
	cancel atomic.Bool
}

func (c *JobController) Start(total int) {
	c.cancel.Store(false)
	go func() {
		defer func() {
			if recovered := recover(); recovered != nil {
				runtime.EventsEmit(c.ctx, "job:error", fmt.Sprint(recovered))
			}
		}()
		for step := 1; step <= total; step++ {
			if c.cancel.Load() {
				runtime.EventsEmit(c.ctx, "job:cancelled")
				return
			}
			runtime.EventsEmit(c.ctx, "job:progress", map[string]any{
				"step":  step,
				"total": total,
			})
			time.Sleep(50 * time.Millisecond)
		}
		runtime.EventsEmit(c.ctx, "job:done", total)
	}()
}

func (c *JobController) Cancel() {
	c.cancel.Store(true)
}
