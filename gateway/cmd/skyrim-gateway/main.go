// skyrim-gateway is the SkyrimTools MCP facade (phase 0: a shared proxy over the existing backends).
//
//	skyrim-gateway                 stdio MCP server for a client: relays to the per-user daemon, starting it if needed
//	skyrim-gateway daemon          run the daemon in the foreground (normally the shim starts it detached)
//	skyrim-gateway status          print gateway_status of the running daemon (exit 1 when none runs)
//	skyrim-gateway stop            stop the running daemon and its backends
//	skyrim-gateway version
//
// Common flags: --pipe NAME (default skyrim-gateway-<user>), --config FILE (JSON array of backend specs instead of the
// built-in houseCARL / Ghidra / SkyLink table). See docs/design/gateway.md.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Se4u01a/SkyrimTools/gateway/internal/backend"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/config"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/daemon"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/pipe"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/winenv"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

var version = "0.1.0-dev" // set by -ldflags "-X main.version=..."

func main() {
	cmd := ""
	args := os.Args[1:]
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		cmd, args = args[0], args[1:]
	}
	fs := flag.NewFlagSet("skyrim-gateway", flag.ExitOnError)
	pipeName := fs.String("pipe", pipe.DefaultName(), "daemon pipe name")
	cfgPath := fs.String("config", "", "JSON file with backend specs (default: the repo launchers)")
	idle := fs.Duration("idle-exit", 30*time.Minute, "daemon exits after this long with no sessions and no backends")
	_ = fs.Parse(args)

	var err error
	switch cmd {
	case "":
		err = shim(*pipeName, *cfgPath, *idle)
	case "daemon":
		err = runDaemon(*pipeName, *cfgPath, *idle)
		if errors.Is(err, daemon.ErrAlreadyRunning) {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(0)
		}
	case "status":
		err = status(*pipeName)
	case "stop":
		err = stop(*pipeName)
	case "version":
		fmt.Println("skyrim-gateway", version)
	default:
		err = fmt.Errorf("unknown command %q (shim is the default; daemon, status, stop, version)", cmd)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "skyrim-gateway:", err)
		os.Exit(1)
	}
}

// ---------------------------------------------------------------------------------------------------- shim

// shim relays the client's stdio to the daemon, byte for byte; all MCP logic lives in the daemon.
func shim(name, cfgPath string, idle time.Duration) error {
	conn, err := pipe.Dial(name, 500*time.Millisecond)
	if err != nil {
		if err := spawnDaemon(name, cfgPath, idle); err != nil {
			return fmt.Errorf("start daemon: %w", err)
		}
		deadline := time.Now().Add(40 * time.Second)
		for {
			conn, err = pipe.Dial(name, 500*time.Millisecond)
			if err == nil {
				break
			}
			if time.Now().After(deadline) {
				return fmt.Errorf("daemon did not open %s: %w (log: %s)", pipe.Path(name), err, logPath())
			}
			time.Sleep(150 * time.Millisecond)
		}
	}
	defer conn.Close()
	var once sync.Once
	done := make(chan struct{})
	finish := func() { once.Do(func() { close(done) }) }
	go func() { _, _ = io.Copy(conn, os.Stdin); finish() }()
	go func() { _, _ = io.Copy(os.Stdout, conn); finish() }()
	<-done
	return nil
}

func spawnDaemon(name, cfgPath string, idle time.Duration) error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	args := []string{"daemon", "--pipe", name, "--idle-exit", idle.String()}
	if cfgPath != "" {
		args = append(args, "--config", cfgPath)
	}
	const (
		detached         = 0x00000008
		newGroup         = 0x00000200
		breakawayFromJob = 0x01000000
		noWindow         = 0x08000000
	)
	try := func(flags uint32) error {
		c := exec.Command(exe, args...)
		c.SysProcAttr = &syscall.SysProcAttr{CreationFlags: flags, HideWindow: true}
		if err := c.Start(); err != nil {
			return err
		}
		return c.Process.Release()
	}
	// Outlive the client's job object when it allows it, so the daemon is shared by later sessions too.
	if err := try(detached | newGroup | breakawayFromJob | noWindow); err == nil {
		return nil
	}
	return try(detached | newGroup | noWindow)
}

// ---------------------------------------------------------------------------------------------------- daemon

func logPath() string {
	return filepath.Join(config.Home(winenv.Merged()), "gateway", "gateway.log")
}

func runDaemon(name, cfgPath string, idle time.Duration) error {
	env := winenv.Merged()
	home := config.Home(env)
	var specs []backend.Spec
	if cfgPath != "" {
		s, err := config.LoadSpecs(cfgPath)
		if err != nil {
			return err
		}
		specs = s
	} else {
		repo, err := config.RepoRoot(env)
		if err != nil {
			return err
		}
		specs = config.DefaultSpecs(repo)
	}
	logger := log.New(os.Stderr, "", log.LstdFlags)
	if err := os.MkdirAll(filepath.Join(home, "gateway"), 0o755); err == nil {
		if f, err := os.OpenFile(logPath(), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644); err == nil {
			defer f.Close()
			logger = log.New(io.MultiWriter(f, os.Stderr), "", log.LstdFlags)
		}
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	err := daemon.Run(ctx, daemon.Options{PipeName: name, Specs: specs, Env: env,
		CacheDir: filepath.Join(home, "gateway"), IdleExit: idle, Version: version, Logger: logger})
	if err != nil && !errors.Is(err, daemon.ErrAlreadyRunning) {
		logger.Printf("daemon: %v", err)
	}
	return err
}

// ---------------------------------------------------------------------------------------------------- status / stop

func connectClient(name string) (*mcp.ClientSession, error) {
	conn, err := pipe.Dial(name, 2*time.Second)
	if err != nil {
		return nil, fmt.Errorf("no daemon on %s", pipe.Path(name))
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "skyrim-gateway-cli", Version: version}, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return client.Connect(ctx, &mcp.IOTransport{Reader: conn, Writer: conn.(net.Conn)}, nil)
}

func callText(name, tool string, args map[string]any) (string, error) {
	cs, err := connectClient(name)
	if err != nil {
		return "", err
	}
	defer cs.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	res, err := cs.CallTool(ctx, &mcp.CallToolParams{Name: tool, Arguments: args})
	if err != nil {
		return "", err
	}
	var b strings.Builder
	for _, c := range res.Content {
		if t, ok := c.(*mcp.TextContent); ok {
			b.WriteString(t.Text)
		}
	}
	if res.IsError {
		return "", errors.New(b.String())
	}
	return b.String(), nil
}

func status(name string) error {
	text, err := callText(name, "gateway_status", nil)
	if err != nil {
		return err
	}
	fmt.Println(text)
	return nil
}

func stop(name string) error {
	_, err := callText(name, "gateway_restart", map[string]any{"daemon": true})
	if err != nil {
		return err
	}
	fmt.Println("daemon stopping")
	return nil
}
