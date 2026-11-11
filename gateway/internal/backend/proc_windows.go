package backend

import (
	"os/exec"
	"syscall"
)

// hideWindow keeps a console child (cmd.exe running a launcher) from flashing a window.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000} // CREATE_NO_WINDOW
}
