package daemon

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Se4u01a/SkyrimTools/gateway/internal/backend"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/pipe"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// The test binary doubles as the fake backend: GW_FAKE=<mode> makes TestMain run an MCP server on stdio.
func TestMain(m *testing.M) {
	if mode := os.Getenv("GW_FAKE"); mode != "" {
		os.Exit(runFake(mode))
	}
	os.Exit(m.Run())
}

func runFake(mode string) int {
	if f := os.Getenv("GW_FAKE_STARTS"); f != "" {
		fh, _ := os.OpenFile(f, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
		fmt.Fprintf(fh, "%d\n", os.Getpid())
		fh.Close()
	}
	if mode == "locked" {
		fmt.Fprintln(os.Stderr, "ghidra.framework.store.LockException: Unable to lock project! C:/fake/projects/skyrim")
		return 1
	}
	if mode == "missing" {
		fmt.Fprintln(os.Stderr, `Fake backend not found at "C:\nowhere\fake.exe". Run setup.`)
		return 1
	}
	s := mcp.NewServer(&mcp.Implementation{Name: "fake", Version: "1"}, nil)
	type echoIn struct {
		Text string `json:"text"`
	}
	mcp.AddTool(s, &mcp.Tool{Name: "fake_echo", Description: "echo"},
		func(ctx context.Context, req *mcp.CallToolRequest, in echoIn) (*mcp.CallToolResult, any, error) {
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: "echo:" + in.Text}}}, nil, nil
		})
	mcp.AddTool(s, &mcp.Tool{Name: "fake_slow", Description: "two progress notifications, then done"},
		func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, any, error) {
			if tok := req.Params.GetProgressToken(); tok != nil {
				for i := 1; i <= 2; i++ {
					_ = req.Session.NotifyProgress(ctx, &mcp.ProgressNotificationParams{ProgressToken: tok, Progress: float64(i), Total: 2})
					time.Sleep(50 * time.Millisecond)
				}
			}
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: "slow done"}}}, nil, nil
		})
	mcp.AddTool(s, &mcp.Tool{Name: "fake_die", Description: "the backend crashes"},
		func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, any, error) {
			os.Exit(3)
			return nil, nil, nil
		})
	mcp.AddTool(s, &mcp.Tool{Name: "fake_nogame", Description: "answers like SkyLink with the game closed"},
		func(ctx context.Context, req *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, any, error) {
			return nil, nil, fmt.Errorf("Cannot connect to Skyrim. Make sure the game is running with SKSE")
		})
	if err := s.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		return 1
	}
	return 0
}

type harness struct {
	t      *testing.T
	pipe   string
	starts string
	cache  string
	d      *Daemon
	cancel context.CancelFunc
	done   chan error
}

func fakeSpec(name, mode string) backend.Spec {
	return backend.Spec{Name: name, Prefix: name + "_", Strip: "fake_", Command: []string{os.Args[0]},
		StartTimeoutS: 20, IdleMinutes: 5, MissingMarkers: []string{"not found at"},
		GameMarkers: []string{"Cannot connect to Skyrim"}, Remedy: "install the fake",
		LockedMarkers: []string{"LockException"}, LockedRemedy: "close the other one"}
}

var pipeSeq atomic.Int64

func start(t *testing.T, cache string, mode string) *harness {
	t.Helper()
	h := &harness{t: t, pipe: fmt.Sprintf("skyrim-gateway-test-%d-%d", os.Getpid(), pipeSeq.Add(1)), cache: cache,
		starts: filepath.Join(t.TempDir(), "starts.txt"), done: make(chan error, 1)}
	env := append(os.Environ(), "GW_FAKE="+mode, "GW_FAKE_STARTS="+h.starts)
	h.d = New(Options{PipeName: h.pipe, Specs: []backend.Spec{fakeSpec("f", mode)}, Env: env, CacheDir: cache})
	l, err := pipe.Listen(h.pipe)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	h.cancel = cancel
	h.d.Discover(ctx, 0)
	go func() { h.done <- h.d.Serve(ctx, l) }()
	t.Cleanup(func() {
		h.d.Shutdown()
		cancel()
		<-h.done
	})
	return h
}

func (h *harness) client(onProgress func()) *mcp.ClientSession {
	h.t.Helper()
	conn, err := pipe.Dial(h.pipe, 5*time.Second)
	if err != nil {
		h.t.Fatal(err)
	}
	opts := &mcp.ClientOptions{}
	if onProgress != nil {
		opts.ProgressNotificationHandler = func(context.Context, *mcp.ProgressNotificationClientRequest) { onProgress() }
	}
	c := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "1"}, opts)
	cs, err := c.Connect(context.Background(), &mcp.IOTransport{Reader: conn, Writer: conn}, nil)
	if err != nil {
		h.t.Fatal(err)
	}
	h.t.Cleanup(func() { cs.Close() })
	return cs
}

func (h *harness) startCount() int {
	data, _ := os.ReadFile(h.starts)
	return len(strings.Fields(string(data)))
}

func toolNames(t *testing.T, cs *mcp.ClientSession) map[string]bool {
	t.Helper()
	out := map[string]bool{}
	for tool, err := range cs.Tools(context.Background(), nil) {
		if err != nil {
			t.Fatal(err)
		}
		out[tool.Name] = true
	}
	return out
}

func waitTools(t *testing.T, cs *mcp.ClientSession, name string) map[string]bool {
	t.Helper()
	deadline := time.Now().Add(20 * time.Second)
	for {
		names := toolNames(t, cs)
		if names[name] {
			return names
		}
		if time.Now().After(deadline) {
			t.Fatalf("tool %s never appeared; have %v", name, names)
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func text(res *mcp.CallToolResult) string {
	var b strings.Builder
	for _, c := range res.Content {
		if t, ok := c.(*mcp.TextContent); ok {
			b.WriteString(t.Text)
		}
	}
	return b.String()
}

func call(t *testing.T, cs *mcp.ClientSession, name string, args any) *mcp.CallToolResult {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: name, Arguments: args})
	if err != nil {
		t.Fatalf("%s: %v", name, err)
	}
	return res
}

func errCode(t *testing.T, res *mcp.CallToolResult) string {
	t.Helper()
	if !res.IsError {
		t.Fatalf("want an error result, got %q", text(res))
	}
	var e backend.Error
	if err := json.Unmarshal([]byte(text(res)), &e); err != nil {
		t.Fatalf("error body is not JSON: %q", text(res))
	}
	return e.Code
}

// Two sessions share one backend process; tools carry the facade prefix; gateway tools are always there.
func TestSharedBackendAndPrefix(t *testing.T) {
	h := start(t, t.TempDir(), "ok")
	a, b := h.client(nil), h.client(nil)
	names := waitTools(t, a, "f_echo")
	for _, want := range []string{"gateway_status", "gateway_restart", "f_echo", "f_slow", "f_die"} {
		if !names[want] {
			t.Errorf("missing tool %s in %v", want, names)
		}
	}
	waitTools(t, b, "f_echo")
	var wg sync.WaitGroup
	for i, cs := range []*mcp.ClientSession{a, b, a, b} {
		wg.Add(1)
		go func(i int, cs *mcp.ClientSession) {
			defer wg.Done()
			res := call(t, cs, "f_echo", map[string]any{"text": fmt.Sprint(i)})
			if res.IsError || text(res) != fmt.Sprintf("echo:%d", i) {
				t.Errorf("call %d: %q", i, text(res))
			}
		}(i, cs)
	}
	wg.Wait()
	if n := h.startCount(); n != 1 {
		t.Errorf("backend started %d times, want 1 (discovery start reused by the calls)", n)
	}
	var st statusOut
	if err := json.Unmarshal([]byte(text(call(t, a, "gateway_status", nil))), &st); err != nil {
		t.Fatal(err)
	}
	if st.Sessions != 2 || len(st.Backends) != 1 || st.Backends[0].State != backend.Ready || st.Backends[0].Tools != 4 {
		t.Errorf("status: %+v", st)
	}
}

// A second daemon with the same cache lists the tools without starting the backend; the first call starts it.
func TestCacheMakesListingLazy(t *testing.T) {
	cache := t.TempDir()
	h1 := start(t, cache, "ok")
	waitTools(t, h1.client(nil), "f_echo")
	deadline := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(filepath.Join(cache, "schemas", "f.json")); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("schema cache was not written")
		}
		time.Sleep(50 * time.Millisecond)
	}
	h1.d.Shutdown()

	h2 := start(t, cache, "ok")
	cs := h2.client(nil)
	if names := toolNames(t, cs); !names["f_echo"] {
		t.Fatalf("cached tools not listed: %v", names)
	}
	if n := h2.startCount(); n != 0 {
		t.Fatalf("listing started the backend %d times, want 0", n)
	}
	if res := call(t, cs, "f_echo", map[string]any{"text": "x"}); text(res) != "echo:x" {
		t.Fatalf("call: %q", text(res))
	}
	if n := h2.startCount(); n != 1 {
		t.Errorf("starts after the first call: %d, want 1", n)
	}
}

// A backend whose launcher says "not found" is reported NOT_INSTALLED, with the remedy, and lists no tools.
func TestNotInstalled(t *testing.T) {
	h := start(t, t.TempDir(), "missing")
	cs := h.client(nil)
	deadline := time.Now().Add(15 * time.Second)
	for {
		var st statusOut
		_ = json.Unmarshal([]byte(text(call(t, cs, "gateway_status", nil))), &st)
		if len(st.Backends) == 1 && st.Backends[0].State == backend.NotInstalled {
			if st.Backends[0].Remedy != "install the fake" {
				t.Errorf("remedy: %+v", st.Backends[0])
			}
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("never reported not_installed: %+v", st)
		}
		time.Sleep(100 * time.Millisecond)
	}
	if names := toolNames(t, cs); names["f_echo"] {
		t.Errorf("a missing backend must list no tools: %v", names)
	}
	// Calling through the backend directly gives the structured error.
	b := backend.New(fakeSpec("f", "missing"), append(os.Environ(), "GW_FAKE=missing"), "t")
	_, err := b.Call(context.Background(), "fake_echo", nil, nil)
	if e, ok := err.(*backend.Error); !ok || e.Code != "NOT_INSTALLED" {
		t.Errorf("direct call: %v", err)
	}
}

// A crash mid-call is a BACKEND_FAILED result, and the next call restarts the backend.
func TestCrashRestart(t *testing.T) {
	h := start(t, t.TempDir(), "ok")
	cs := h.client(nil)
	waitTools(t, cs, "f_die")
	if code := errCode(t, call(t, cs, "f_die", nil)); code != "BACKEND_FAILED" {
		t.Errorf("crash code %s", code)
	}
	deadline := time.Now().Add(10 * time.Second)
	for {
		res := call(t, cs, "f_echo", map[string]any{"text": "again"})
		if !res.IsError && text(res) == "echo:again" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("no restart: %q", text(res))
		}
		time.Sleep(100 * time.Millisecond)
	}
	if n := h.startCount(); n != 2 {
		t.Errorf("starts %d, want 2", n)
	}
}

// Progress notifications from the backend reach the client that made the call, under its own token.
func TestProgressPassthrough(t *testing.T) {
	h := start(t, t.TempDir(), "ok")
	var got atomic.Int64
	cs := h.client(func() { got.Add(1) })
	waitTools(t, cs, "f_slow")
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: "f_slow", Meta: mcp.Meta{"progressToken": "mine"}})
	if err != nil || text(res) != "slow done" {
		t.Fatalf("slow: %v %v", err, res)
	}
	time.Sleep(200 * time.Millisecond)
	if got.Load() < 2 {
		t.Errorf("progress notifications: %d, want 2", got.Load())
	}
}

// SkyLink's "Cannot connect to Skyrim" becomes GAME_NOT_RUNNING with the remedy.
func TestGameNotRunning(t *testing.T) {
	h := start(t, t.TempDir(), "ok")
	cs := h.client(nil)
	waitTools(t, cs, "f_nogame")
	if code := errCode(t, call(t, cs, "f_nogame", nil)); code != "GAME_NOT_RUNNING" {
		t.Errorf("code %s", code)
	}
}

// Only one daemon can own a pipe name.
func TestSecondListenerRefused(t *testing.T) {
	h := start(t, "", "ok")
	if _, err := pipe.Listen(h.pipe); err == nil {
		t.Fatal("a second listener on the same pipe was allowed")
	}
}

// A backend that cannot take its lock is "locked" with the lock remedy, not a generic failure.
func TestLocked(t *testing.T) {
	b := backend.New(fakeSpec("f", "locked"), append(os.Environ(), "GW_FAKE=locked"), "t")
	_, err := b.Call(context.Background(), "fake_echo", nil, nil)
	if e, ok := err.(*backend.Error); !ok || e.Code != "BACKEND_LOCKED" || e.Remedy != "close the other one" {
		t.Fatalf("call: %v", err)
	}
	if s := b.Snapshot(); s.State != backend.Locked || s.Remedy != "close the other one" {
		t.Errorf("snapshot: %+v", s)
	}
}
