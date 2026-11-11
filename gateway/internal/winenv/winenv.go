// Package winenv builds the environment for backends from the user's registry variables, so a daemon started by a
// client with a stale environment (variables set by setup after the client started) still sees the current values.
package winenv

import (
	"os"
	"strings"

	"golang.org/x/sys/windows/registry"
)

// keep from the process: the registry PATH is only the user half, so replacing it would drop the system PATH.
var keep = map[string]bool{"PATH": true, "PATHEXT": true, "SYSTEMROOT": true, "COMSPEC": true, "TEMP": true, "TMP": true}

// UserVars reads HKCU\Environment; REG_EXPAND_SZ values are expanded.
func UserVars() map[string]string {
	out := map[string]string{}
	k, err := registry.OpenKey(registry.CURRENT_USER, `Environment`, registry.QUERY_VALUE)
	if err != nil {
		return out
	}
	defer k.Close()
	names, err := k.ReadValueNames(-1)
	if err != nil {
		return out
	}
	for _, n := range names {
		v, typ, err := k.GetStringValue(n)
		if err != nil {
			continue
		}
		if typ == registry.EXPAND_SZ {
			if x, err := registry.ExpandString(v); err == nil {
				v = x
			}
		}
		out[n] = v
	}
	return out
}

// Merged returns os.Environ() with the user's registry variables laid over it (except PATH and friends).
func Merged() []string {
	env := map[string]string{}
	order := []string{}
	for _, kv := range os.Environ() {
		i := strings.IndexByte(kv[1:], '=') + 1 // Windows has "=C:=C:\..." entries
		if i <= 0 {
			continue
		}
		k := kv[:i]
		if _, ok := env[strings.ToUpper(k)]; !ok {
			order = append(order, k)
		}
		env[strings.ToUpper(k)] = kv
	}
	for k, v := range UserVars() {
		if keep[strings.ToUpper(k)] {
			continue
		}
		if _, ok := env[strings.ToUpper(k)]; !ok {
			order = append(order, k)
		}
		env[strings.ToUpper(k)] = k + "=" + v
	}
	out := make([]string, 0, len(order))
	for _, k := range order {
		out = append(out, env[strings.ToUpper(k)])
	}
	return out
}

// Lookup finds a variable in an environment list (case-insensitive, as on Windows).
func Lookup(env []string, name string) string {
	p := strings.ToUpper(name) + "="
	for _, kv := range env {
		if strings.HasPrefix(strings.ToUpper(kv), p) {
			return kv[len(p):]
		}
	}
	return ""
}
