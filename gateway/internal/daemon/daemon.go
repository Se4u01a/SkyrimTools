// Package daemon is the shared facade process: one per user, one MCP server for every connected client session,
// one child process per backend.
package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/Se4u01a/SkyrimTools/gateway/internal/backend"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/pipe"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ErrAlreadyRunning means another daemon owns the pipe; the caller just exits.
var ErrAlreadyRunning = errors.New("another skyrim-gateway daemon is already running")

// Options configure one daemon.
type Options struct {
	PipeName string
	Specs    []backend.Spec
	Env      []string // backend environment
	CacheDir string   // schema cache; "" disables it
	IdleExit time.Duration
	Version  string
	Logger   *log.Logger
}

type route struct {
	b    *backend.Backend
	name string // the backend's own tool name
}

type progressTarget struct {
	ss    *mcp.ServerSession
	token any
}

// Daemon is exported for tests; Run is the normal entry point.
type Daemon struct {
	opts     Options
	server   *mcp.Server
	backends []*backend.Backend
	log      *log.Logger

	mu       sync.Mutex
	routes   map[string]route    // facade name -> backend tool
	owned    map[string][]string // backend name -> facade names
	sessions int
	lastSeen time.Time

	progSeq  atomic.Int64
	progress sync.Map // rewritten token -> progressTarget
	quit     chan struct{}
	quitOnce sync.Once
}

// New builds the daemon and registers the cached tools; it starts nothing.
func New(opts Options) *Daemon {
	if opts.Logger == nil {
		opts.Logger = log.New(io.Discard, "", 0)
	}
	if opts.Version == "" {
		opts.Version = "dev"
	}
	d := &Daemon{opts: opts, log: opts.Logger, routes: map[string]route{}, owned: map[string][]string{},
		lastSeen: time.Now(), quit: make(chan struct{})}
	d.server = mcp.NewServer(&mcp.Implementation{Name: "skyrim-gateway", Version: opts.Version}, &mcp.ServerOptions{
		Instructions: "SkyrimTools facade over several backends; every tool description starts with its backend in " +
			"brackets: [housecarl] MO2 load order, records, patches, Papyrus, BSA, NIF, Nexus; [ghidra] decompile " +
			"SkyrimSE.exe and DLLs; [skylink] the RUNNING game (read freely, change it only when the user asks). " +
			"gateway_status shows which backends are installed, running or missing and how to install them; a backend " +
			"starts on its first call, so the first call to Ghidra can take a minute.",
	})
	d.addGatewayTools()
	for _, s := range opts.Specs {
		b := backend.New(s, opts.Env, opts.Version)
		b.OnProgress = d.forwardProgress
		b.OnStarted = d.refreshTools
		d.backends = append(d.backends, b)
		if tools := d.loadCache(s.Name); tools != nil {
			d.setTools(b, tools)
		}
	}
	return d
}

// Server exposes the MCP server (tests connect to it in memory).
func (d *Daemon) Server() *mcp.Server { return d.server }

// Discover lists the tools of every backend that has no cached schema yet. A backend that is started for this stays
// up until its idle timer stops it, so the first real call does not pay for a second start. The returned channel is
// closed when every backend whose start timeout is at most quick has been listed (or has failed).
func (d *Daemon) Discover(ctx context.Context, quick time.Duration) <-chan struct{} {
	var wg sync.WaitGroup
	for _, b := range d.backends {
		d.mu.Lock()
		_, have := d.owned[b.Name]
		d.mu.Unlock()
		if have {
			continue
		}
		fast := time.Duration(b.StartTimeoutS)*time.Second <= quick
		if fast {
			wg.Add(1)
		}
		go func(b *backend.Backend, fast bool) {
			if fast {
				defer wg.Done()
			}
			if _, err := b.Ensure(ctx); err != nil {
				d.log.Printf("discover %s: %v", b.Name, err)
				return
			}
			d.refreshTools(b) // OnStarted does the same in the background; this one is waited for
		}(b, fast)
	}
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	return done
}

// refreshTools runs after every backend start: it re-lists the tools and reconciles the facade (new tools appear,
// vanished ones go) and the cache. This is what keeps a cached schema from going stale after a backend update.
func (d *Daemon) refreshTools(b *backend.Backend) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	tools, err := b.ListTools(ctx)
	if err != nil {
		d.log.Printf("tools/list %s: %v", b.Name, err)
		return
	}
	d.setTools(b, tools)
	d.saveCache(b.Name, tools)
}

func (d *Daemon) facadeName(b *backend.Backend, name string) string {
	return b.Prefix + strings.TrimPrefix(name, b.Strip)
}

func (d *Daemon) setTools(b *backend.Backend, tools []*mcp.Tool) {
	d.mu.Lock()
	defer d.mu.Unlock()
	keep := map[string]bool{}
	for _, t := range tools {
		if t == nil || t.Name == "" {
			continue
		}
		name := d.facadeName(b, t.Name)
		if other, taken := d.routes[name]; taken && other.b != b {
			// two backends offer the same name: this one gets "<backend>_<name>"; the first keeps the plain name
			name = b.Name + "_" + name
			d.log.Printf("tool name %s is taken by %s: %s exposes it as %s", t.Name, other.b.Name, b.Name, name)
		}
		keep[name] = true
		schema := t.InputSchema
		if schema == nil {
			schema = map[string]any{"type": "object"}
		}
		desc := "[" + b.Name + "] " + t.Description
		d.routes[name] = route{b: b, name: t.Name}
		d.server.AddTool(&mcp.Tool{Name: name, Title: t.Title, Description: desc, InputSchema: schema,
			OutputSchema: t.OutputSchema, Annotations: t.Annotations}, d.forward(name))
	}
	var gone []string
	for _, name := range d.owned[b.Name] {
		if !keep[name] {
			gone = append(gone, name)
			delete(d.routes, name)
		}
	}
	if len(gone) > 0 {
		d.server.RemoveTools(gone...)
	}
	names := make([]string, 0, len(keep))
	for n := range keep {
		names = append(names, n)
	}
	d.owned[b.Name] = names
}

func (d *Daemon) forward(facade string) mcp.ToolHandler {
	return func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		d.mu.Lock()
		r, ok := d.routes[facade]
		d.lastSeen = time.Now()
		d.mu.Unlock()
		if !ok {
			return errResult(&backend.Error{Code: "UNKNOWN_TOOL", Message: facade + " is no longer provided by its backend"}), nil
		}
		var meta mcp.Meta
		if tok := req.Params.GetProgressToken(); tok != nil {
			rewritten := fmt.Sprintf("gw-%d", d.progSeq.Add(1))
			d.progress.Store(rewritten, progressTarget{ss: req.Session, token: tok})
			defer d.progress.Delete(rewritten)
			meta = mcp.Meta{"progressToken": rewritten}
		}
		res, err := r.b.Call(ctx, r.name, req.Params.Arguments, meta)
		if err != nil {
			d.log.Printf("%s: %v", facade, err)
			return errResult(err), nil
		}
		return res, nil
	}
}

func (d *Daemon) forwardProgress(ctx context.Context, req *mcp.ProgressNotificationClientRequest) {
	key := fmt.Sprint(req.Params.ProgressToken)
	v, ok := d.progress.Load(key)
	if !ok {
		return
	}
	t := v.(progressTarget)
	p := *req.Params
	p.ProgressToken = t.token
	_ = t.ss.NotifyProgress(ctx, &p)
}

func errResult(err error) *mcp.CallToolResult {
	var ge *backend.Error
	if !errors.As(err, &ge) {
		ge = &backend.Error{Code: "INTERNAL", Message: err.Error()}
	}
	body, _ := json.MarshalIndent(ge, "", "  ")
	return &mcp.CallToolResult{IsError: true, Content: []mcp.Content{&mcp.TextContent{Text: string(body)}}}
}

// ---------------------------------------------------------------------------------------------------- gateway tools

type statusOut struct {
	Version  string           `json:"version"`
	Pid      int              `json:"pid"`
	Sessions int              `json:"sessions"`
	Backends []backend.Status `json:"backends"`
}

type restartIn struct {
	Backend string `json:"backend,omitempty" jsonschema:"backend name to restart; empty restarts every backend"`
	Daemon  bool   `json:"daemon,omitempty" jsonschema:"stop the whole daemon; the next client session starts a fresh one"`
}

func (d *Daemon) Status() statusOut {
	d.mu.Lock()
	out := statusOut{Version: d.opts.Version, Pid: os.Getpid(), Sessions: d.sessions}
	counts := map[string]int{}
	for n, names := range d.owned {
		counts[n] = len(names)
	}
	d.mu.Unlock()
	for _, b := range d.backends {
		s := b.Snapshot()
		s.Tools = counts[b.Name]
		out.Backends = append(out.Backends, s)
	}
	return out
}

func (d *Daemon) addGatewayTools() {
	mcp.AddTool(d.server, &mcp.Tool{Name: "gateway_status",
		Description: "Which SkyrimTools backends exist, whether each is installed, running or stopped, how many tools it " +
			"provides, and the command that installs a missing one. Starts nothing."},
		func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, statusOut, error) {
			return nil, d.Status(), nil
		})
	mcp.AddTool(d.server, &mcp.Tool{Name: "gateway_restart",
		Description: "Stop a backend (or all of them) and clear its failure count; it starts again on its next call. " +
			"Use after reinstalling a backend or when one is stuck in BACKEND_FAILED."},
		func(ctx context.Context, req *mcp.CallToolRequest, in restartIn) (*mcp.CallToolResult, statusOut, error) {
			if in.Daemon {
				go func() { time.Sleep(200 * time.Millisecond); d.Shutdown() }()
				return nil, d.Status(), nil
			}
			found := false
			for _, b := range d.backends {
				if in.Backend == "" || strings.EqualFold(in.Backend, b.Name) {
					b.Reset()
					found = true
				}
			}
			if !found {
				return nil, statusOut{}, fmt.Errorf("no backend named %q", in.Backend)
			}
			return nil, d.Status(), nil
		})
}

// ---------------------------------------------------------------------------------------------------- schema cache

type cacheFile struct {
	Backend string      `json:"backend"`
	Saved   string      `json:"saved"`
	Tools   []*mcp.Tool `json:"tools"`
}

func (d *Daemon) cachePath(name string) string {
	return filepath.Join(d.opts.CacheDir, "schemas", name+".json")
}

func (d *Daemon) loadCache(name string) []*mcp.Tool {
	if d.opts.CacheDir == "" {
		return nil
	}
	data, err := os.ReadFile(d.cachePath(name))
	if err != nil {
		return nil
	}
	var c cacheFile
	if json.Unmarshal(data, &c) != nil || len(c.Tools) == 0 {
		return nil
	}
	return c.Tools
}

func (d *Daemon) saveCache(name string, tools []*mcp.Tool) {
	if d.opts.CacheDir == "" || len(tools) == 0 {
		return
	}
	p := d.cachePath(name)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return
	}
	data, err := json.MarshalIndent(cacheFile{Backend: name, Saved: time.Now().Format(time.RFC3339), Tools: tools}, "", " ")
	if err != nil {
		return
	}
	tmp := p + ".tmp"
	if os.WriteFile(tmp, data, 0o644) == nil {
		_ = os.Rename(tmp, p)
	}
}

// ---------------------------------------------------------------------------------------------------- serving

// Serve accepts client sessions on l until Shutdown or ctx ends.
func (d *Daemon) Serve(ctx context.Context, l net.Listener) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	go func() {
		select {
		case <-ctx.Done():
		case <-d.quit:
		}
		_ = l.Close()
	}()
	go d.idleWatch(ctx)
	for {
		conn, err := l.Accept()
		if err != nil {
			select {
			case <-d.quit:
				return nil
			default:
			}
			if ctx.Err() != nil {
				return nil
			}
			d.log.Printf("accept: %v", err)
			time.Sleep(100 * time.Millisecond)
			continue
		}
		go d.serveConn(ctx, conn)
	}
}

func (d *Daemon) serveConn(ctx context.Context, conn net.Conn) {
	defer conn.Close()
	d.mu.Lock()
	d.sessions++
	d.lastSeen = time.Now()
	d.mu.Unlock()
	defer func() {
		d.mu.Lock()
		d.sessions--
		d.lastSeen = time.Now()
		d.mu.Unlock()
	}()
	ss, err := d.server.Connect(ctx, &mcp.IOTransport{Reader: conn, Writer: conn}, nil)
	if err != nil {
		d.log.Printf("session: %v", err)
		return
	}
	_ = ss.Wait()
}

func (d *Daemon) idleWatch(ctx context.Context) {
	if d.opts.IdleExit <= 0 {
		return
	}
	t := time.NewTicker(time.Minute)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-d.quit:
			return
		case <-t.C:
		}
		d.mu.Lock()
		idle := d.sessions == 0 && time.Since(d.lastSeen) > d.opts.IdleExit
		d.mu.Unlock()
		for _, b := range d.backends {
			if b.Busy() {
				idle = false
			}
		}
		if idle {
			d.log.Printf("no sessions and no running backends for %s: exiting", d.opts.IdleExit)
			d.Shutdown()
			return
		}
	}
}

// Shutdown stops every backend and makes Serve return.
func (d *Daemon) Shutdown() {
	d.quitOnce.Do(func() {
		for _, b := range d.backends {
			b.Stop()
		}
		close(d.quit)
	})
}

// Run listens on the pipe, discovers uncached backends and serves until idle exit or Shutdown.
func Run(ctx context.Context, opts Options) error {
	l, err := pipe.Listen(opts.PipeName)
	if err != nil {
		if probe, derr := pipe.Dial(opts.PipeName, time.Second); derr == nil {
			probe.Close()
			return ErrAlreadyRunning
		}
		return fmt.Errorf("listen on %s: %w", pipe.Path(opts.PipeName), err)
	}
	d := New(opts)
	d.log.Printf("skyrim-gateway %s daemon pid %d on %s; backends: %s", opts.Version, os.Getpid(),
		pipe.Path(opts.PipeName), names(opts.Specs))
	// Wait briefly for the quick backends, so the first session's tools/list already carries them.
	select {
	case <-d.Discover(ctx, 90*time.Second):
	case <-time.After(20 * time.Second):
	}
	err = d.Serve(ctx, l)
	d.Shutdown()
	return err
}

func names(specs []backend.Spec) string {
	n := make([]string, 0, len(specs))
	for _, s := range specs {
		n = append(n, s.Name)
	}
	sort.Strings(n)
	return strings.Join(n, ", ")
}
