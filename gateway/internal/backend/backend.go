// Package backend runs one downstream MCP server (houseCARL, pyghidra-mcp, SkyLink, ...) as a child process:
// started on first use, shared by every caller, stopped after an idle period, restarted after a crash.
package backend

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Spec describes a backend. It is plain data so a JSON config can override the built-in table.
type Spec struct {
	Name           string   `json:"name"`            // housecarl
	Prefix         string   `json:"prefix"`          // facade tool prefix, e.g. "hc_"
	Strip          string   `json:"strip"`           // removed from backend tool names before the prefix, e.g. "housecarl_"
	Command        []string `json:"command"`         // argv; the launcher .cmd for the real backends
	IdleMinutes    int      `json:"idle_minutes"`    // stop after this long without calls (0 = 30)
	StartTimeoutS  int      `json:"start_timeout_s"` // initialize handshake deadline (0 = 60)
	MissingMarkers []string `json:"missing_markers"` // stderr text that means "not installed"
	GameMarkers    []string `json:"game_markers"`    // result text that means "the game is not running"
	LockedMarkers  []string `json:"locked_markers"`  // stderr text that means "another process holds its data"
	LockedRemedy   string   `json:"locked_remedy"`   // what to do about that
	Remedy         string   `json:"remedy"`          // what installs it
	Description    string   `json:"description"`     // one line for gateway_status
}

// State of a backend as gateway_status reports it.
type State string

const (
	NotInstalled State = "not_installed"
	Stopped      State = "stopped"
	Starting     State = "starting"
	Ready        State = "ready"
	Failed       State = "failed"
	Locked       State = "locked" // another process holds the backend's data (Ghidra project lock)
)

// Error is a structured facade error; it becomes the JSON body of an isError tool result.
type Error struct {
	Code    string `json:"code"`
	Backend string `json:"backend,omitempty"`
	Message string `json:"message"`
	Remedy  string `json:"remedy,omitempty"`
	Detail  string `json:"detail,omitempty"`
}

func (e *Error) Error() string { return e.Code + ": " + e.Message }

const maxFailures = 3
const failureCooldown = 60 * time.Second

// Backend is safe for concurrent use. Start is serialised: concurrent first calls wait for one start.
type Backend struct {
	Spec
	Env        []string
	Version    string
	OnProgress func(context.Context, *mcp.ProgressNotificationClientRequest)
	OnStarted  func(*Backend) // called (in its own goroutine) after every successful start

	mu        sync.Mutex
	startMu   sync.Mutex
	state     State
	detail    string
	session   *mcp.ClientSession
	starts    int
	failures  int
	lastFail  time.Time
	lastUse   time.Time
	inflight  int
	idleTimer *time.Timer
	stderr    *tail
	remedy    string // of the last failure
}

// New returns a stopped backend.
func New(spec Spec, env []string, version string) *Backend {
	return &Backend{Spec: spec, Env: env, Version: version, state: Stopped}
}

func (b *Backend) idle() time.Duration {
	if b.IdleMinutes > 0 {
		return time.Duration(b.IdleMinutes) * time.Minute
	}
	return 30 * time.Minute
}

func (b *Backend) startTimeout() time.Duration {
	if b.StartTimeoutS > 0 {
		return time.Duration(b.StartTimeoutS) * time.Second
	}
	return 60 * time.Second
}

// Ensure returns a live session, starting the process if needed.
func (b *Backend) Ensure(ctx context.Context) (*mcp.ClientSession, error) {
	b.startMu.Lock()
	defer b.startMu.Unlock()

	b.mu.Lock()
	if b.session != nil {
		s := b.session
		b.mu.Unlock()
		return s, nil
	}
	if b.failures >= maxFailures && time.Since(b.lastFail) < failureCooldown {
		err := &Error{Code: "BACKEND_FAILED", Backend: b.Name, Message: fmt.Sprintf("%s failed to start %d times in a row; retry after %s or call gateway_restart", b.Name, b.failures, failureCooldown), Detail: b.detail}
		b.mu.Unlock()
		return nil, err
	}
	b.state = Starting
	b.mu.Unlock()

	if len(b.Command) == 0 {
		return nil, b.fail(Failed, &Error{Code: "BACKEND_FAILED", Backend: b.Name, Message: "no command configured"})
	}
	cmd := exec.Command(b.Command[0], b.Command[1:]...)
	cmd.Env = b.Env
	errTail := newTail(4096)
	cmd.Stderr = errTail
	hideWindow(cmd)

	client := mcp.NewClient(&mcp.Implementation{Name: "skyrim-gateway", Version: b.Version},
		&mcp.ClientOptions{ProgressNotificationHandler: b.OnProgress})
	cctx, cancel := context.WithTimeout(ctx, b.startTimeout())
	defer cancel()
	cs, err := client.Connect(cctx, &mcp.CommandTransport{Command: cmd, TerminateDuration: 3 * time.Second}, nil)
	if err != nil {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
		text := strings.TrimSpace(errTail.String())
		for _, m := range b.MissingMarkers {
			if m != "" && strings.Contains(text, m) {
				return nil, b.fail(NotInstalled, &Error{Code: "NOT_INSTALLED", Backend: b.Name,
					Message: b.Name + " is not installed", Remedy: b.Remedy, Detail: lastLines(text, 3)})
			}
		}
		for _, m := range b.LockedMarkers {
			if m != "" && strings.Contains(text, m) {
				return nil, b.fail(Locked, &Error{Code: "BACKEND_LOCKED", Backend: b.Name,
					Message: b.Name + " could not open its data: another process holds the lock", Remedy: b.LockedRemedy,
					Detail: lastLines(text, 3)})
			}
		}
		code := "BACKEND_FAILED"
		if errors.Is(err, context.DeadlineExceeded) {
			code = "BACKEND_START_TIMEOUT"
		}
		return nil, b.fail(Failed, &Error{Code: code, Backend: b.Name, Message: "could not start " + b.Name + ": " + err.Error(), Detail: lastLines(text, 5)})
	}

	b.mu.Lock()
	b.session, b.state, b.detail, b.failures, b.stderr = cs, Ready, "", 0, errTail
	b.starts++
	b.lastUse = time.Now()
	b.armIdleLocked()
	b.mu.Unlock()
	go b.watch(cs)
	if b.OnStarted != nil {
		go b.OnStarted(b)
	}
	return cs, nil
}

func (b *Backend) fail(state State, err *Error) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.state, b.detail, b.remedy = state, err.Detail, err.Remedy
	if state == Failed || state == Locked {
		b.failures++
		b.lastFail = time.Now()
	}
	return err
}

// watch notices a backend that exited on its own (crash, killed) so the next call restarts it.
func (b *Backend) watch(cs *mcp.ClientSession) {
	_ = cs.Wait()
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.session == cs {
		b.session = nil
		b.state = Stopped
		if b.stderr != nil {
			b.detail = lastLines(strings.TrimSpace(b.stderr.String()), 3)
		}
	}
}

func (b *Backend) armIdleLocked() {
	if b.idleTimer != nil {
		b.idleTimer.Stop()
	}
	b.idleTimer = time.AfterFunc(b.idle(), b.stopIfIdle)
}

func (b *Backend) stopIfIdle() {
	b.mu.Lock()
	if b.session == nil || b.inflight > 0 || time.Since(b.lastUse) < b.idle() {
		if b.session != nil {
			b.armIdleLocked()
		}
		b.mu.Unlock()
		return
	}
	b.mu.Unlock()
	b.Stop()
}

// Stop closes the session (the SDK closes stdin, then kills the process after TerminateDuration).
func (b *Backend) Stop() {
	b.mu.Lock()
	cs := b.session
	b.session = nil
	if b.state != NotInstalled {
		b.state = Stopped
	}
	if b.idleTimer != nil {
		b.idleTimer.Stop()
	}
	b.mu.Unlock()
	if cs != nil {
		_ = cs.Close()
	}
}

// Reset clears the failure counter, so a backend in cooldown can be started again.
func (b *Backend) Reset() {
	b.Stop()
	b.mu.Lock()
	b.failures, b.detail = 0, ""
	if b.state == NotInstalled || b.state == Failed || b.state == Locked {
		b.state = Stopped
	}
	b.mu.Unlock()
}

// ListTools starts the backend if needed and returns its tools.
func (b *Backend) ListTools(ctx context.Context) ([]*mcp.Tool, error) {
	cs, err := b.Ensure(ctx)
	if err != nil {
		return nil, err
	}
	var out []*mcp.Tool
	for t, err := range cs.Tools(ctx, nil) {
		if err != nil {
			return nil, &Error{Code: "BACKEND_FAILED", Backend: b.Name, Message: "tools/list failed: " + err.Error()}
		}
		out = append(out, t)
	}
	b.touch()
	return out, nil
}

func (b *Backend) touch() {
	b.mu.Lock()
	b.lastUse = time.Now()
	if b.session != nil {
		b.armIdleLocked()
	}
	b.mu.Unlock()
}

// Call forwards one tools/call. meta carries the rewritten progress token, if any.
func (b *Backend) Call(ctx context.Context, name string, args json.RawMessage, meta mcp.Meta) (*mcp.CallToolResult, error) {
	cs, err := b.Ensure(ctx)
	if err != nil {
		return nil, err
	}
	b.mu.Lock()
	b.inflight++
	b.mu.Unlock()
	defer func() {
		b.mu.Lock()
		b.inflight--
		b.mu.Unlock()
		b.touch()
	}()
	params := &mcp.CallToolParams{Name: name, Meta: meta}
	if len(args) > 0 && string(args) != "null" {
		params.Arguments = args
	}
	res, err := cs.CallTool(ctx, params)
	if err != nil {
		if ctx.Err() != nil {
			return nil, &Error{Code: "CANCELLED", Backend: b.Name, Message: "the call was cancelled"}
		}
		b.mu.Lock()
		detail := ""
		if b.stderr != nil {
			detail = lastLines(strings.TrimSpace(b.stderr.String()), 3)
		}
		b.mu.Unlock()
		return nil, &Error{Code: "BACKEND_FAILED", Backend: b.Name, Message: name + ": " + err.Error(), Detail: detail}
	}
	if res.IsError && len(b.GameMarkers) > 0 {
		for _, c := range res.Content {
			if tc, ok := c.(*mcp.TextContent); ok {
				for _, m := range b.GameMarkers {
					if strings.Contains(tc.Text, m) {
						return nil, &Error{Code: "GAME_NOT_RUNNING", Backend: b.Name,
							Message: "the game is not running with this bridge loaded", Remedy: b.Remedy, Detail: tc.Text}
					}
				}
			}
		}
	}
	return res, nil
}

// Status is what gateway_status prints for one backend.
type Status struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	State       State  `json:"state"`
	Prefix      string `json:"prefix"`
	Tools       int    `json:"tools"`
	Starts      int    `json:"starts"`
	Inflight    int    `json:"inflight"`
	IdleMinutes int    `json:"idle_minutes"`
	LastUse     string `json:"last_use,omitempty"`
	Detail      string `json:"detail,omitempty"`
	Remedy      string `json:"remedy,omitempty"`
}

// Snapshot reports the current state; tools is filled in by the caller (it owns the registry).
func (b *Backend) Snapshot() Status {
	b.mu.Lock()
	defer b.mu.Unlock()
	s := Status{Name: b.Name, Description: b.Description, State: b.state, Prefix: b.Prefix, Starts: b.starts,
		Inflight: b.inflight, IdleMinutes: int(b.idle() / time.Minute), Detail: b.detail}
	if !b.lastUse.IsZero() {
		s.LastUse = b.lastUse.Format(time.RFC3339)
	}
	if b.state == NotInstalled || b.state == Failed || b.state == Locked {
		s.Remedy = b.remedy
		if s.Remedy == "" {
			s.Remedy = b.Remedy
		}
	}
	return s
}

// Busy reports a running process or a call in flight.
func (b *Backend) Busy() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.session != nil || b.inflight > 0
}

// tail keeps the last n bytes written to it (a child's stderr).
type tail struct {
	mu  sync.Mutex
	n   int
	buf []byte
}

func newTail(n int) *tail { return &tail{n: n} }

func (t *tail) Write(p []byte) (int, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.buf = append(t.buf, p...)
	if len(t.buf) > t.n {
		t.buf = append([]byte(nil), t.buf[len(t.buf)-t.n:]...)
	}
	return len(p), nil
}

func (t *tail) String() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return string(t.buf)
}

func lastLines(s string, n int) string {
	lines := strings.Split(strings.ReplaceAll(s, "\r\n", "\n"), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, " | ")
}
