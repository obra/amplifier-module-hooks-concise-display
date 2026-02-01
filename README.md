# amplifier-module-hooks-concise-display

Cleaner, more condensed terminal output for Amplifier sessions.

## Features

- **Condensed tool calls**: `→ bash: ls /tmp` with colorized output
- **Compact thinking blocks**: Shows first few lines with `(+N more lines)` indicator
- **Unified diff display**: File edits shown as colored diffs with context
- **Token stats**: Minimal `└─ 54k tokens in (97% cached) · 646 out` format
- **Rich colors**: Blue for tools/thinking, green/red for diffs, dim for secondary info

## Installation

Add to your bundle:

```yaml
hooks:
  - module: hooks-concise-display
    source: git+https://github.com/jnewland/amplifier-module-hooks-concise-display@main
```

Or via CLI:

```bash
amplifier module add hooks-concise-display \
  --source git+https://github.com/jnewland/amplifier-module-hooks-concise-display@main
```

## Configuration

```yaml
hooks:
  - module: hooks-concise-display
    source: git+https://github.com/jnewland/amplifier-module-hooks-concise-display@main
    config:
      enabled: true
      show_thinking: true
      max_param_len: 50
      max_result_len: 60
```

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable/disable the hook |
| `show_thinking` | `true` | Show condensed thinking blocks |
| `max_param_len` | `50` | Max length for tool parameters |
| `max_result_len` | `60` | Max length for result content |

## Example Output

```
💭 Thinking...
   The user wants to list the current directory...
   (+3 more lines)
└─ 54k tokens in (97% cached) · 646 out

→ bash: ls -la
✓ total 32
  drwxr-xr-x  12 jesse  staff   384 Jan 31 21:11 .
  (+10 more)

→ edit_file: ./config.py
  - old_value = "foo"
  + new_value = "bar"
✓ 1 edit
```

## License

MIT
