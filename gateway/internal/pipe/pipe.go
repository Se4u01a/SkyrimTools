// Package pipe is the shim <-> daemon transport: a named pipe only the current user can open.
package pipe

import (
	"fmt"
	"net"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/Microsoft/go-winio"
	"golang.org/x/sys/windows"
)

// DefaultName is per user, so two accounts on one machine get two daemons.
func DefaultName() string {
	u := os.Getenv("USERNAME")
	if u == "" {
		u = "user"
	}
	return "skyrim-gateway-" + strings.ToLower(regexp.MustCompile(`[^A-Za-z0-9_.-]`).ReplaceAllString(u, "_"))
}

// Path turns a pipe name into \\.\pipe\name.
func Path(name string) string {
	if strings.HasPrefix(name, `\\.\pipe\`) {
		return name
	}
	return `\\.\pipe\` + name
}

func userSDDL() (string, error) {
	tok := windows.GetCurrentProcessToken()
	u, err := tok.GetTokenUser()
	if err != nil {
		return "", err
	}
	// protected DACL: full access for this user only (SYSTEM and administrators are not listed on purpose).
	return fmt.Sprintf("D:P(A;;GA;;;%s)", u.User.Sid.String()), nil
}

// Listen creates the pipe; it fails when another daemon already owns the name.
func Listen(name string) (net.Listener, error) {
	sddl, err := userSDDL()
	if err != nil {
		return nil, err
	}
	return winio.ListenPipe(Path(name), &winio.PipeConfig{SecurityDescriptor: sddl, InputBufferSize: 65536, OutputBufferSize: 65536})
}

// Dial connects to a running daemon.
func Dial(name string, timeout time.Duration) (net.Conn, error) {
	return winio.DialPipe(Path(name), &timeout)
}
