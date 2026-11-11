// Package config resolves the repo, the install folder and the backend table.
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Se4u01a/SkyrimTools/gateway/internal/backend"
	"github.com/Se4u01a/SkyrimTools/gateway/internal/winenv"
)

// RepoRoot is SKYRIM_TOOLS_REPO, else the first parent of the executable that holds .claude-plugin/plugin.json.
func RepoRoot(env []string) (string, error) {
	if r := winenv.Lookup(env, "SKYRIM_TOOLS_REPO"); r != "" && isRepo(r) {
		return r, nil
	}
	exe, err := os.Executable()
	if err == nil {
		dir := filepath.Dir(exe)
		for i := 0; i < 6; i++ {
			if isRepo(dir) {
				return dir, nil
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return "", fmt.Errorf("SkyrimTools repo not found: set SKYRIM_TOOLS_REPO (setup.cmd does) or run the exe from inside the repo")
}

func isRepo(dir string) bool {
	_, err := os.Stat(filepath.Join(dir, ".claude-plugin", "plugin.json"))
	return err == nil
}

// Home is SKYRIM_TOOLS_HOME, else %LOCALAPPDATA%\SkyrimTools.
func Home(env []string) string {
	if h := winenv.Lookup(env, "SKYRIM_TOOLS_HOME"); h != "" {
		return h
	}
	return filepath.Join(winenv.Lookup(env, "LOCALAPPDATA"), "SkyrimTools")
}

// DefaultSpecs wraps the repo's .cmd launchers, which already resolve every path and fallback.
func DefaultSpecs(repo string) []backend.Spec {
	launcher := func(rel ...string) []string {
		return []string{"cmd.exe", "/c", filepath.Join(append([]string{repo, "scripts"}, rel...)...)}
	}
	return []backend.Spec{
		{Name: "housecarl", Prefix: "hc_", Strip: "housecarl_", Command: launcher("run_housecarl.cmd"),
			IdleMinutes: 30, StartTimeoutS: 90, MissingMarkers: []string{"houseCARL not found"},
			Remedy: "setup.cmd", Description: "MO2 load order: records, conflicts, patches, Papyrus, BSA, NIF, SKSE, Nexus"},
		{Name: "ghidra", Prefix: "ghidra_", Command: launcher("re", "run_ghidra_mcp.cmd"),
			IdleMinutes: 60, StartTimeoutS: 300, MissingMarkers: []string{"Ghidra workspace is incomplete"},
			LockedMarkers: []string{"LockException", "Unable to lock project"},
			LockedRemedy: "another pyghidra-mcp has the Ghidra project open (usually the plugin's own pyghidra-mcp entry " +
				"in the same client): keep only one of them, then call gateway_restart",
			Remedy: "setup.cmd -Ghidra", Description: "headless Ghidra: decompile, disassemble, xrefs of SkyrimSE.exe and DLLs"},
		{Name: "skylink", Prefix: "live_", Command: launcher("run_skylink.cmd"),
			IdleMinutes: 30, StartTimeoutS: 60, MissingMarkers: []string{"SkyLink AI not found"},
			GameMarkers: []string{"Cannot connect to Skyrim"},
			Remedy:      "setup.cmd -SkyLink, enable the 'SkyLink AI' mod in MO2, start the game through SKSE",
			Description: "SkyLink AI: the RUNNING game (read freely; change only when the user asks)"},
	}
}

// LoadSpecs reads a JSON array of backend specs (tests and custom setups).
func LoadSpecs(path string) ([]backend.Spec, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var specs []backend.Spec
	if err := json.Unmarshal(data, &specs); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return specs, nil
}
