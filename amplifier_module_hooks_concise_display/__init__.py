"""Concise Display Hooks Module

Clean, context-aware renderers for tool calls and results.

Design principles:
- Visual clarity: one glance tells you what happened
- Context-aware: adapts to sub-agents, terminal width, verbosity
- Coherent: consistent patterns across all tools
- Concise: show what matters, hide what doesn't
"""

import os
import textwrap
from dataclasses import dataclass
from typing import Any

from amplifier_core import HookResult
from rich.console import Console

# Shared console instance
_console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Display primitives
# ─────────────────────────────────────────────────────────────────────────────

def _write(text: str) -> None:
    """Write text to console with Rich markup support."""
    _console.print(text, end="", highlight=False)


def _writeln(text: str = "") -> None:
    """Write line to console with Rich markup support."""
    _console.print(text, highlight=False)


def _terminal_width() -> int:
    """Get terminal width, defaulting to 80."""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


class Icon:
    """Status icons."""
    TOOL = "→"
    OK = "✓"
    FAIL = "✗"
    WARN = "!"
    RUN = "▶"
    FILE = "◇"
    SEARCH = "○"
    THINK = "💭"
    TOKENS = "📊"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Display configuration."""
    enabled: bool = True
    max_param_len: int = 50      # Max length for inline params
    max_result_len: int = 60     # Max length for result summaries
    indent_sub_agents: bool = True
    show_agent_name: bool = True
    show_thinking: bool = True   # Show thinking block indicator
    show_token_usage: bool = True  # Show token usage after responses


# ─────────────────────────────────────────────────────────────────────────────
# Context
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolContext:
    """Context for rendering a tool call/result."""
    tool_name: str
    tool_input: dict
    result: Any
    session_id: str
    is_sub_agent: bool
    agent_name: str | None
    phase: str  # "call" or "result"
    
    @classmethod
    def from_data(cls, data: dict, phase: str) -> "ToolContext":
        """Build context from hook event data."""
        session_id = data.get("session_id", "")
        
        # Detect sub-agent from session_id pattern
        is_sub_agent = "_" in session_id and not session_id.startswith("session_")
        agent_name = None
        if is_sub_agent:
            # Extract agent name from session_id like "abc123_foundation:explorer"
            parts = session_id.rsplit("_", 1)
            if len(parts) == 2:
                agent_name = parts[1]
        
        result = data.get("tool_response", data.get("result", {}))
        if isinstance(result, dict) and "output" in result:
            result = result["output"]
        
        return cls(
            tool_name=data.get("tool_name", "unknown"),
            tool_input=data.get("tool_input", {}),
            result=result,
            session_id=session_id,
            is_sub_agent=is_sub_agent,
            agent_name=agent_name,
            phase=phase,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int) -> str:
    """Truncate with ellipsis."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


def _first_line(text: str, max_len: int = 60) -> tuple[str, int]:
    """Get first line and count of remaining lines."""
    lines = text.strip().split("\n")
    first = _truncate(lines[0], max_len)
    remaining = len(lines) - 1
    return first, remaining


def _format_count(n: int, singular: str, plural: str | None = None) -> str:
    """Format count with proper pluralization."""
    plural = plural or singular + "s"
    return f"{n} {singular if n == 1 else plural}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_file_op(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render file operations: read_file, write_file."""
    path = ctx.tool_input.get("file_path", "")
    short_path = _truncate(path, config.max_param_len)
    
    if ctx.phase == "call":
        # For write_file, mark for content preview
        if ctx.tool_name == "write_file":
            return short_path, "write_preview"
        return short_path, ""
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    if ctx.tool_name == "read_file":
        lines = r.get("lines_read") or r.get("total_lines")
        if lines:
            return _format_count(lines, "line"), ""
    
    elif ctx.tool_name == "write_file":
        bytes_w = r.get("bytes_written") or r.get("bytes")
        if bytes_w:
            return f"{bytes_w:,} bytes", ""
    
    return None


def _render_write_preview(content: str, max_width: int = 60) -> list[str]:
    """Render write_file content preview: first 7 lines, elided, last 2 lines."""
    lines = []
    content_lines = content.split("\n")
    total = len(content_lines)
    
    first_n = 7
    last_n = 2
    
    if total <= first_n + last_n:
        # Show all lines
        for line in content_lines:
            lines.append(f"[dim]  {_truncate(line, max_width)}[/dim]")
    else:
        # Show first 7
        for line in content_lines[:first_n]:
            lines.append(f"[dim]  {_truncate(line, max_width)}[/dim]")
        
        # Elided line
        elided = total - first_n - last_n
        lines.append(f"[dim]  ... ({elided} lines elided) ...[/dim]")
        
        # Show last 2
        for line in content_lines[-last_n:]:
            lines.append(f"[dim]  {_truncate(line, max_width)}[/dim]")
    
    return lines


def _format_diff_line(line: str, prefix: str, color: str, max_len: int) -> str:
    """Format a single diff line with color."""
    truncated = _truncate(line, max_len - 2)  # Account for prefix
    return f"[bold {color}]{prefix} {truncated}[/bold {color}]"


def _render_edit_file(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render edit_file with unified diff format."""
    path = ctx.tool_input.get("file_path", "")
    short_path = _truncate(path, config.max_param_len)
    
    if ctx.phase == "call":
        # Show path on first line, diff below
        old_str = ctx.tool_input.get("old_string", "")
        new_str = ctx.tool_input.get("new_string", "")
        replace_all = ctx.tool_input.get("replace_all", False)
        
        # Store diff info for multi-line output (handled specially)
        ctx.tool_input["_diff_display"] = {
            "path": short_path,
            "old": old_str,
            "new": new_str,
            "replace_all": replace_all,
        }
        return short_path, "diff"  # Special marker for diff display
    
    # Result phase
    r = ctx.result
    if isinstance(r, dict):
        n = r.get("replacements_made", 1)
        return _format_count(n, "edit"), ""
    return None


def _find_common_context(old_lines: list[str], new_lines: list[str]) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Find common leading/trailing context lines between old and new.
    
    Returns: (leading_context, old_changed, new_changed, trailing_context, _)
    """
    # Find common prefix
    prefix_len = 0
    min_len = min(len(old_lines), len(new_lines))
    while prefix_len < min_len and old_lines[prefix_len] == new_lines[prefix_len]:
        prefix_len += 1
    
    # Find common suffix (but don't overlap with prefix)
    suffix_len = 0
    while (suffix_len < min_len - prefix_len and 
           old_lines[-(suffix_len + 1)] == new_lines[-(suffix_len + 1)]):
        suffix_len += 1
    
    # Extract parts
    leading = old_lines[:prefix_len]
    trailing = old_lines[len(old_lines) - suffix_len:] if suffix_len > 0 else []
    
    old_end = len(old_lines) - suffix_len if suffix_len > 0 else len(old_lines)
    new_end = len(new_lines) - suffix_len if suffix_len > 0 else len(new_lines)
    
    old_changed = old_lines[prefix_len:old_end]
    new_changed = new_lines[prefix_len:new_end]
    
    return leading, old_changed, new_changed, trailing, []


def _render_diff_block(old_str: str, new_str: str, max_width: int = 60, context_lines: int = 2) -> list[str]:
    """Render a unified diff block with context."""
    lines = []
    
    old_lines = old_str.split("\n")
    new_lines = new_str.split("\n")
    
    # Find common context
    leading, old_changed, new_changed, trailing, _ = _find_common_context(old_lines, new_lines)
    
    # Limit context lines shown
    if len(leading) > context_lines:
        leading = leading[-context_lines:]  # Show last N of leading context
    if len(trailing) > context_lines:
        trailing = trailing[:context_lines]  # Show first N of trailing context
    
    # Limit changed lines
    max_diff_lines = 4
    old_truncated = len(old_changed) > max_diff_lines
    new_truncated = len(new_changed) > max_diff_lines
    
    # Leading context (unchanged)
    for line in leading:
        lines.append(f"[dim]  {_truncate(line, max_width - 2)}[/dim]")
    
    # Old lines (deletions)
    for line in old_changed[:max_diff_lines]:
        lines.append(_format_diff_line(line, "-", "red", max_width))
    if old_truncated:
        lines.append(f"[red]  ... (+{len(old_changed) - max_diff_lines})[/red]")
    
    # New lines (additions)  
    for line in new_changed[:max_diff_lines]:
        lines.append(_format_diff_line(line, "+", "green", max_width))
    if new_truncated:
        lines.append(f"[green]  ... (+{len(new_changed) - max_diff_lines})[/green]")
    
    # Trailing context (unchanged)
    for line in trailing:
        lines.append(f"[dim]  {_truncate(line, max_width - 2)}[/dim]")
    
    return lines


def _render_search(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render search operations: grep, glob."""
    if ctx.phase == "call":
        pattern = ctx.tool_input.get("pattern", "")
        path = ctx.tool_input.get("path", "")
        param = f"{pattern}" + (f" in {path}" if path else "")
        return _truncate(param, config.max_param_len), ""
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    if ctx.tool_name == "grep":
        matches = r.get("total_matches") or r.get("matches_count", 0)
        return _format_count(matches, "match", "matches"), ""
    
    elif ctx.tool_name == "glob":
        total = r.get("total_files", len(r.get("files", [])))
        return _format_count(total, "file"), ""
    
    return None


def _render_bash(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render bash execution."""
    if ctx.phase == "call":
        cmd = ctx.tool_input.get("command", "")
        return _truncate(cmd, config.max_param_len), ""
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    rc = r.get("returncode", 0)
    stdout = r.get("stdout", "")
    stderr = r.get("stderr", "")
    
    if rc != 0:
        # Failure - show exit code and error
        err = (stderr or stdout or "failed").strip()
        first, _ = _first_line(err, config.max_result_len - 10)
        return f"exit {rc}: {first}", "fail"
    
    # Success - show output (up to 3 lines)
    output = stdout.strip()
    if not output:
        return "(no output)", ""
    
    lines = output.split("\n")
    max_lines = 3
    shown_lines = lines[:max_lines]
    remaining = len(lines) - max_lines
    
    # Format shown lines
    result_lines = [_truncate(line, config.max_result_len) for line in shown_lines]
    result = "\n  ".join(result_lines)  # Indent continuation lines
    
    if remaining > 0:
        return f"{result}\n  (+{remaining} more)", ""
    return result, ""


def _render_python_check(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render python_check results."""
    if ctx.phase == "call":
        paths = ctx.tool_input.get("paths", [])
        if len(paths) == 1:
            return _truncate(paths[0], config.max_param_len), ""
        elif paths:
            return _format_count(len(paths), "path"), ""
        return None
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    files = r.get("files_checked", 0)
    errors = r.get("error_count", 0)
    warnings = r.get("warning_count", 0)
    
    if errors > 0:
        return f"{errors} errors, {warnings} warnings ({files} files)", "fail"
    elif warnings > 0:
        return f"{warnings} warnings ({files} files)", "warn"
    else:
        return f"clean ({files} files)", ""


def _render_todo(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render todo operations."""
    if ctx.phase == "call":
        action = ctx.tool_input.get("action", "")
        return action, ""
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    count = r.get("count", 0)
    completed = r.get("completed", 0)
    in_progress = r.get("in_progress", 0)
    pending = r.get("pending", 0)
    
    # Build concise summary
    if count == completed:
        return f"{count}/{count} done", ""
    
    parts = []
    if in_progress:
        parts.append(f"{in_progress} active")
    if pending:
        parts.append(f"{pending} pending") 
    if completed:
        parts.append(f"{completed} done")
    
    return f"{count} ({', '.join(parts)})", ""


def _render_task(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render task (agent delegation)."""
    if ctx.phase == "call":
        agent = ctx.tool_input.get("agent", "")
        instruction = ctx.tool_input.get("instruction", "")
        if agent:
            # Show agent name prominently, instruction truncated
            instr_short = _truncate(instruction, config.max_param_len - len(agent) - 2)
            return f"{agent}: {instr_short}", ""
        return _truncate(instruction, config.max_param_len), ""
    
    # Result phase
    r = ctx.result
    if isinstance(r, dict):
        response = r.get("response", "")
        if response:
            first, remaining = _first_line(response, config.max_result_len)
            if remaining > 0:
                return f"{first} (+{remaining})", ""
            return first, ""
    return "done", ""


def _render_web(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render web operations: web_fetch, web_search."""
    if ctx.phase == "call":
        if ctx.tool_name == "web_fetch":
            url = ctx.tool_input.get("url", "")
            return _truncate(url, config.max_param_len), ""
        else:  # web_search
            query = ctx.tool_input.get("query", "")
            return f'"{_truncate(query, config.max_param_len - 2)}"', ""
    
    # Result phase
    r = ctx.result
    if not isinstance(r, dict):
        return None
    
    if ctx.tool_name == "web_fetch":
        status = r.get("status_code") or r.get("status")
        content = r.get("content", "")
        if status:
            size = f"{len(content):,}" if content else "0"
            return f"[{status}] {size} chars", ""
    else:  # web_search
        results = r.get("results", [])
        return _format_count(len(results), "result"), ""
    
    return None


def _render_recipes(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render recipe operations."""
    if ctx.phase == "call":
        op = ctx.tool_input.get("operation", "")
        recipe = ctx.tool_input.get("recipe_path", "")
        session = ctx.tool_input.get("session_id", "")
        
        if recipe:
            return f"{op} {_truncate(recipe, config.max_param_len - len(op) - 1)}", ""
        elif session:
            return f"{op} {session[:12]}…", ""
        return op, ""
    
    # Result phase
    r = ctx.result
    if isinstance(r, dict):
        status = r.get("status", "")
        session_id = r.get("session_id", "")
        if status and session_id:
            return f"{status} ({session_id[:12]}…)", ""
        elif status:
            return status, ""
    return None


def _render_shadow(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render shadow environment operations."""
    if ctx.phase == "call":
        op = ctx.tool_input.get("operation", "")
        shadow_id = ctx.tool_input.get("shadow_id", "")
        cmd = ctx.tool_input.get("command", "")
        
        if cmd:
            return f"{op}: {_truncate(cmd, config.max_param_len - len(op) - 2)}", ""
        elif shadow_id:
            return f"{op} {shadow_id}", ""
        return op, ""
    
    # Result phase
    r = ctx.result
    if isinstance(r, dict):
        shadow_id = r.get("shadow_id", "")
        stdout = r.get("stdout", "")
        exit_code = r.get("exit_code")
        
        if exit_code is not None:
            if exit_code != 0:
                first, _ = _first_line(r.get("stderr", "") or stdout, 40)
                return f"exit {exit_code}: {first}", "fail"
            if stdout:
                first, remaining = _first_line(stdout, config.max_result_len)
                if remaining > 0:
                    return f"{first} (+{remaining})", ""
                return first, ""
            return "(no output)", ""
        elif shadow_id:
            return shadow_id, ""
    return None


def _render_load_skill(ctx: ToolContext, config: Config) -> tuple[str, str] | None:
    """Render skill loading."""
    if ctx.phase == "call":
        skill = ctx.tool_input.get("skill_name", "")
        if skill:
            return skill, ""
        if ctx.tool_input.get("list"):
            return "list", ""
        if ctx.tool_input.get("search"):
            return f'search "{ctx.tool_input["search"]}"', ""
        if ctx.tool_input.get("info"):
            return f'info "{ctx.tool_input["info"]}"', ""
        return None
    
    # Result phase  
    r = ctx.result
    if isinstance(r, dict):
        if "skills" in r:
            return _format_count(len(r["skills"]), "skill"), ""
    return "loaded", ""


# Registry of tool renderers
RENDERERS: dict[str, Any] = {
    # File operations
    "read_file": _render_file_op,
    "write_file": _render_file_op,
    "edit_file": _render_edit_file,
    # Search
    "grep": _render_search,
    "glob": _render_search,
    # Execution
    "bash": _render_bash,
    "python_check": _render_python_check,
    # Task management
    "todo": _render_todo,
    "task": _render_task,
    # Web
    "web_fetch": _render_web,
    "web_search": _render_web,
    # Recipes
    "recipes": _render_recipes,
    # Shadow
    "shadow": _render_shadow,
    # Skills
    "load_skill": _render_load_skill,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main hook class
# ─────────────────────────────────────────────────────────────────────────────

def _format_compact_number(n: int) -> str:
    """Format number compactly: 1234 -> 1.2k, 1234567 -> 1.2M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip('0').rstrip('.')  + "M" if n >= 1_000_000 else f"{n / 1_000:.0f}k"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _parse_agent_from_session_id(session_id: str) -> str | None:
    """Extract agent name from session_id like 'abc123_foundation:explorer'."""
    if not session_id or "_" not in session_id:
        return None
    parts = session_id.rsplit("_", 1)
    if len(parts) == 2 and ":" in parts[1]:
        return parts[1]
    return None


class ConciseDisplayHooks:
    """Context-aware concise display for tool calls and results."""

    def __init__(self, config: Config):
        self.config = config
        self.thinking_blocks: dict[int, dict] = {}  # Track active thinking blocks

    def _format_line(
        self,
        ctx: ToolContext,
        content: str,
        status: str = "",
    ) -> str:
        """Format a display line with proper styling and indentation."""
        parts = []
        
        # Sub-agent indentation and name
        if ctx.is_sub_agent and self.config.indent_sub_agents:
            parts.append("  ")
            if self.config.show_agent_name and ctx.agent_name:
                parts.append(f"[dim]\\[{ctx.agent_name}][/dim] ")
        
        # Icon and tool name for calls, icon only for results
        if ctx.phase == "call":
            parts.append(f"[blue]{Icon.TOOL} {ctx.tool_name}:[/blue]")
            if content:
                parts.append(f" [dim]{content}[/dim]")
        else:
            # Result - icon based on status
            if status == "fail":
                parts.append(f"[red]{Icon.FAIL}[/red]")
            elif status == "warn":
                parts.append(f"[yellow]{Icon.WARN}[/yellow]")
            else:
                parts.append(f"[green]{Icon.OK}[/green]")
            
            if content:
                if status == "fail":
                    parts.append(f" [red]{content}[/red]")
                elif status == "warn":
                    parts.append(f" [yellow]{content}[/yellow]")
                else:
                    parts.append(f" [dim]{content}[/dim]")
        
        return "".join(parts)

    def _render_generic(self, ctx: ToolContext) -> tuple[str, str] | None:
        """Generic fallback renderer."""
        if ctx.phase == "call":
            # Extract first string param
            for key in ["file_path", "path", "pattern", "command", "query", "url", "instruction"]:
                if key in ctx.tool_input:
                    val = ctx.tool_input[key]
                    if isinstance(val, str):
                        return _truncate(val, self.config.max_param_len), ""
            return None
        
        # Result - try to summarize
        r = ctx.result
        if isinstance(r, str):
            first, remaining = _first_line(r, self.config.max_result_len)
            if remaining > 0:
                return f"{first} (+{remaining})", ""
            return first, ""
        elif isinstance(r, dict):
            if "error" in r:
                return _truncate(str(r["error"]), self.config.max_result_len), "fail"
            if "count" in r:
                return f"{r['count']} items", ""
        return None

    def _get_indent_prefix(self, ctx: ToolContext) -> str:
        """Get indentation prefix for sub-agents."""
        if ctx.is_sub_agent and self.config.indent_sub_agents:
            if self.config.show_agent_name and ctx.agent_name:
                return f"  [dim]\\[{ctx.agent_name}][/dim] "
            return "  "
        return ""

    async def handle_tool_pre(self, _event: str, data: dict[str, Any]) -> HookResult:
        """Render tool call."""
        if not self.config.enabled:
            return HookResult(action="continue")
        
        # Skip todo - let the dedicated todo UI hook handle it
        tool_name = data.get("tool_name", "")
        if tool_name == "todo":
            return HookResult(action="continue")
        
        ctx = ToolContext.from_data(data, "call")
        
        # Get renderer
        renderer = RENDERERS.get(ctx.tool_name, self._render_generic)
        result = renderer(ctx, self.config)
        
        content, status = result if result else ("", "")
        
        # Special handling for diff display (edit_file)
        if status == "diff":
            line = self._format_line(ctx, content)
            _write(f"\n{line}\n")
            
            # Render the diff block
            old_str = ctx.tool_input.get("old_string", "")
            new_str = ctx.tool_input.get("new_string", "")
            if old_str or new_str:
                indent = self._get_indent_prefix(ctx)
                diff_lines = _render_diff_block(old_str, new_str, self.config.max_result_len)
                for diff_line in diff_lines:
                    _write(f"{indent}  {diff_line}\n")
        
        # Special handling for write_file content preview
        elif status == "write_preview":
            line = self._format_line(ctx, content)
            _write(f"\n{line}\n")
            
            # Render content preview
            file_content = ctx.tool_input.get("content", "")
            if file_content:
                indent = self._get_indent_prefix(ctx)
                preview_lines = _render_write_preview(file_content, self.config.max_result_len)
                for preview_line in preview_lines:
                    _write(f"{indent}{preview_line}\n")
        else:
            line = self._format_line(ctx, content)
            _write(f"\n{line}\n")  # Add leading newline for spacing
        
        # Use "modify" action to pass metadata to subsequent hooks
        modified_data = {**data, "hook_metadata": {"concise_displayed": True}}
        return HookResult(action="modify", data=modified_data)

    async def handle_tool_post(self, _event: str, data: dict[str, Any]) -> HookResult:
        """Render tool result."""
        if not self.config.enabled:
            return HookResult(action="continue")
        
        # Skip todo - let the dedicated todo UI hook handle it
        tool_name = data.get("tool_name", "")
        if tool_name == "todo":
            return HookResult(action="continue")
        
        ctx = ToolContext.from_data(data, "result")
        
        # Get renderer
        renderer = RENDERERS.get(ctx.tool_name, self._render_generic)
        result = renderer(ctx, self.config)
        
        content, status = result if result else ("", "")
        line = self._format_line(ctx, content, status)
        _write(f"{line}\n")
        
        # Use "modify" action to pass metadata to subsequent hooks
        modified_data = {**data, "hook_metadata": {"concise_displayed": True}}
        return HookResult(action="modify", data=modified_data)

    async def handle_content_block_start(self, _event: str, data: dict[str, Any]) -> HookResult:
        """Show thinking indicator when thinking block starts."""
        if not self.config.enabled or not self.config.show_thinking:
            return HookResult(action="continue")
        
        block_type = data.get("block_type")
        block_index = data.get("block_index")
        
        if block_type in {"thinking", "reasoning"} and block_index is not None:
            session_id = data.get("session_id", "")
            agent_name = _parse_agent_from_session_id(session_id)
            self.thinking_blocks[block_index] = {"agent": agent_name}
            
            # Show condensed thinking indicator (with leading newline for spacing)
            if agent_name:
                _write(f"\n  [dim]\\[{agent_name}][/dim] [blue]{Icon.THINK} Thinking...[/blue]\n")
            else:
                _write(f"\n[blue]{Icon.THINK} Thinking...[/blue]\n")
        
        return HookResult(action="continue")

    async def handle_content_block_end(self, _event: str, data: dict[str, Any]) -> HookResult:
        """Show thinking content and token usage."""
        if not self.config.enabled:
            return HookResult(action="continue")
        
        block_index = data.get("block_index")
        total_blocks = data.get("total_blocks")
        block = data.get("block", {})
        block_type = block.get("type")
        usage = data.get("usage")
        is_last_block = block_index == total_blocks - 1 if total_blocks else False
        
        # Display thinking content if we were tracking this block
        if (
            block_type in {"thinking", "reasoning"}
            and block_index is not None
            and block_index in self.thinking_blocks
        ):
            thinking_text = (
                block.get("thinking", "")
                or block.get("text", "")
                or ""
            )
            
            if thinking_text and self.config.show_thinking:
                agent_info = self.thinking_blocks[block_index]
                agent_name = agent_info.get("agent")
                indent = "  " if agent_name else ""
                
                # Show condensed thinking (first few lines, wrapped to terminal width)
                lines = thinking_text.strip().split("\n")
                max_lines = 5
                width = _terminal_width() - 7  # Leave room for indent + "   "
                base_indent = f"{indent}   "  # 3 spaces for thinking content
                
                shown = 0
                for line in lines:
                    if shown >= max_lines:
                        break
                    # Wrap long lines
                    wrapped = textwrap.wrap(line, width=width) or [""]
                    for wrapped_line in wrapped:
                        if shown >= max_lines:
                            break
                        _write(f"[dim]{base_indent}{wrapped_line}[/dim]\n")
                        shown += 1
                
                if len(lines) > max_lines:
                    _write(f"[dim]{base_indent}(+{len(lines) - max_lines} more lines)[/dim]\n")
            
            del self.thinking_blocks[block_index]
        
        # Show token usage after last block
        if is_last_block and self.config.show_token_usage and usage:
            session_id = data.get("session_id", "")
            agent_name = _parse_agent_from_session_id(session_id)
            indent = "  " if agent_name else ""
            
            # Get token counts
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_create = usage.get("cache_creation_input_tokens", 0)
            
            # Compute total input (with caching, input_tokens is just uncacheable portion)
            total_input = input_tokens + cache_read + cache_create
            
            # Format compactly
            input_str = _format_compact_number(total_input)
            output_str = _format_compact_number(output_tokens)
            
            # Cache info
            cache_info = ""
            if cache_read > 0 or cache_create > 0:
                cache_pct = int((cache_read / total_input) * 100) if total_input > 0 else 0
                if cache_read > 0:
                    cache_info = f" ({cache_pct}% cached)"
                else:
                    cache_info = " (caching...)"
            
            _write(f"[dim]{indent}└─ {input_str} tokens in{cache_info} · {output_str} out[/dim]\n\n")
        
        return HookResult(action="continue")


# ─────────────────────────────────────────────────────────────────────────────
# Module mount
# ─────────────────────────────────────────────────────────────────────────────

async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mount concise display hooks.
    
    Config:
        enabled: bool = True
        max_param_len: int = 50
        max_result_len: int = 60
        indent_sub_agents: bool = True
        show_agent_name: bool = True
    """
    config = config or {}
    
    display_config = Config(
        enabled=config.get("enabled", True),
        max_param_len=config.get("max_param_len", 50),
        max_result_len=config.get("max_result_len", 60),
        indent_sub_agents=config.get("indent_sub_agents", True),
        show_agent_name=config.get("show_agent_name", True),
        show_thinking=config.get("show_thinking", True),
        show_token_usage=config.get("show_token_usage", True),
    )
    
    hooks = ConciseDisplayHooks(display_config)
    
    # Tool events
    coordinator.hooks.register("tool:pre", hooks.handle_tool_pre, priority=4)
    coordinator.hooks.register("tool:post", hooks.handle_tool_post, priority=4)
    
    # Content block events (thinking, token usage)
    coordinator.hooks.register("content_block:start", hooks.handle_content_block_start, priority=4)
    coordinator.hooks.register("content_block:end", hooks.handle_content_block_end, priority=4)
    
    return {
        "name": "hooks-concise-display",
        "version": "0.1.0",
        "tools": list(RENDERERS.keys()),
    }
