# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Schema, frontmatter, and shlex-based command-safety linting for Cluster Toolkit agent skills."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any, Dict, FrozenSet, List, NoReturn, Optional, Set, Tuple
import yaml

REPO_ROOT = str(Path(__file__).resolve().parents[2])
NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_REGEX = re.compile(r"^\ufeff?[ \t]*---[ \t]*\r?\n(.*?)\r?\n[ \t]*---[ \t]*(?:\r?\n(.*))?$", re.DOTALL)
VALID_STATUSES: Tuple[str, ...] = ("experimental", "stable")
VALID_MODES: Tuple[str, ...] = ("gated", "autonomous")
VALID_COMMUNITY_SUPPORTS: Tuple[str, ...] = ("community", "partner")
VALID_EXEMPTION_LABELS: FrozenSet[str] = frozenset({"skip-tool-checks", "skip-eval-safety-checks"})
REQUIRED_FRONTMATTER: Tuple[str, ...] = ("name", "description")

MULTI_COMMAND_CLIS: FrozenSet[str] = frozenset({
    "kubectl", "gcloud", "gcluster", "ghpc", "xpk", "scontrol", "sacctmgr", "helm", "terraform", "git",
})
COMMAND_WRAPPERS: FrozenSet[str] = frozenset({"sudo", "env", "nohup", "nice", "xargs", "stdbuf", "time", "timeout"})
_WRAPPER_FLAGS_WITH_ARGS: Dict[str, FrozenSet[str]] = {
    "sudo": frozenset({
        "-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt",
        "-C", "--close-from", "-D", "--chdir", "-r", "--role", "-t", "--type",
        "-U", "--other-user", "-T", "--command-timeout",
    }),
    "env": frozenset({
        "-u", "--unset", "-C", "--chdir", "-S", "--split-string",
        "--block-signal", "--default-signal", "--ignore-signal",
    }),
    "nice": frozenset({"-n", "--adjustment"}),
    "timeout": frozenset({"-k", "--kill-after", "-s", "--signal"}),
    "xargs": frozenset({
        "-a", "--arg-file", "-d", "--delimiter", "-E", "-e", "-I", "-L",
        "--max-lines", "-n", "--max-args", "-P", "--max-procs", "-s", "--max-chars",
    }),
    "stdbuf": frozenset({"-i", "--input", "-o", "--output", "-e", "--error"}),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
    "nohup": frozenset(),
}
_VERSIONED_ESCAPE_RE = re.compile(r"^(?:python|perl|ruby|php|node)\d+(?:\.\d+)*$")
_TOOL_DECL_METACHAR_RE = re.compile(r"[;&|`$<>()\r\n]")
_CLI_FLAGS_WITH_ARGS: FrozenSet[str] = frozenset({
    "-n", "--namespace", "-l", "--selector", "-c", "--container", "--context", "--cluster", "--clusters",
    "--kubeconfig", "-f", "--filename", "-u", "--user", "-o", "--output", "-p", "--patch", "--type",
    "--project", "--zone", "--region", "--format", "--filter", "--limit", "-chdir", "-M", "-d",
    "--deployment-file", "--vars",
})
SHELL_ESCAPE_PRIMITIVES: FrozenSet[str] = frozenset({
    "bash", "sh", "zsh", "dash", "ksh", "csh", "tcsh",
    "python", "python3", "perl", "ruby", "node", "php", "busybox",
    "curl", "wget", "nc", "ncat", "netcat", "socat",
    "sudo", "su", "eval", "exec", "source", "env", "xargs",
    "ssh", "scp", "nohup", "nice", "time", "timeout", "stdbuf", "iptables", "systemctl",
})
HOST_WIPE_BINARIES: FrozenSet[str] = frozenset({
    "mkfs", "mkswap", "fdisk", "gdisk", "parted", "shred", "wipefs",
    "shutdown", "reboot", "poweroff", "umount", "killall",
})
CATASTROPHIC_TOOL_BINARIES: FrozenSet[str] = HOST_WIPE_BINARIES | frozenset({"rm", "rmdir", "dd", "init"})
_SAFE_DEV_REDIRECTS: FrozenSet[str] = frozenset({"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr"})
_SYSTEM_RM_TARGETS: FrozenSet[str] = frozenset({
    "/", "/*", "*", "..", "~", "~/", "~/*",
    "/etc", "/usr", "/var", "/boot", "/dev", "/bin", "/sbin", "/lib", "/lib64", "/opt", "/proc", "/sys", "/root", "/home",
})
_SYSTEM_RM_PREFIXES: Tuple[str, ...] = (
    "/etc/", "/usr/", "/var/", "/boot/", "/dev/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/proc/", "/sys/", "/root/",
)
_KUBECTL_CATASTROPHIC_DELETE_KINDS: FrozenSet[str] = frozenset({
    "namespace", "namespaces", "ns", "node", "nodes", "no",
    "crd", "crds", "customresourcedefinition", "customresourcedefinitions",
    "pv", "pvs", "persistentvolume", "persistentvolumes",
    "pvc", "pvcs", "persistentvolumeclaim", "persistentvolumeclaims",
    "storageclass", "storageclasses", "sc",
    "clusterrole", "clusterroles", "clusterrolebinding", "clusterrolebindings",
})
_KUBECTL_READONLY_VERBS: FrozenSet[str] = frozenset({
    "get", "describe", "logs", "explain", "top", "version", "api-resources", "api-versions", "cluster-info", "diff", "auth",
})
_KUBECTL_EXEC_ESCAPE_VERBS: FrozenSet[str] = frozenset({"exec", "run", "cp", "attach"})
_KUBECTL_MUTATING_ROLLOUT: FrozenSet[str] = frozenset({"restart", "undo", "pause", "resume"})
_SCONTROL_MUTATING_VERBS: FrozenSet[str] = frozenset({
    "update", "delete", "reboot", "drain", "resume", "requeue", "hold", "release", "reconfigure",
})
_GIT_MUTATING_VERBS: FrozenSet[str] = frozenset({
    "reset", "clean", "checkout", "restore", "push", "commit", "merge", "rebase", "cherry-pick", "revert",
})
_STANDALONE_MUTATING_BINARIES: FrozenSet[str] = frozenset({"scancel", "sbatch", "kill", "pkill", "rm", "rmdir"})
MUTATING_VERBS: FrozenSet[str] = frozenset({
    "patch", "delete", "update", "create", "apply", "deploy", "submit", "cancel",
    "stop", "start", "resume", "reset", "reboot", "scale", "drain", "cordon", "uncordon",
    "taint", "label", "annotate", "set", "upgrade", "rollback", "install",
    "kill", "pkill", "scancel", "sbatch", "requeue", "hold", "release", "reconfigure",
    "restart-instances", "recreate-instances", "add-metadata", "resize",
    "edit", "replace", "restart", "suspend", "destroy", "exec", "run", "cp", "attach",
    "import", "purge", "remove", "drop", "modify",
})
_WARNING_CALLOUT_RE = re.compile(r"(?:\[!(?:WARNING|CAUTION)\]|^[ \t>#*_-]*\b(?:warning|caution)\b)", re.IGNORECASE | re.MULTILINE)
_GOOGLE_IMPERSONATION_RE = re.compile(r"\b(?:google|alphabet)\w*|\bgcp\b|googlecloud|alphabetinc", re.IGNORECASE)
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECT_TOKEN_RE = re.compile(r"^(?:\d*>>?|\d*>&\d+|&>>?)")
_NEGATIVE_ADVICE_RE = re.compile(
    r"\b(?:do\s+not\s+(?:run|execute)|don't\s+(?:run|execute)|never\s+(?:run|execute)|avoid\s+(?:running|executing))[ \t]+[^\n;.&|]+",
    re.IGNORECASE,
)


def _is_shell_escape(binary: str) -> bool:
    """Return True for Tier 2 shell/scripting/network escapes, including versioned interpreters."""
    return binary in SHELL_ESCAPE_PRIMITIVES or bool(_VERSIONED_ESCAPE_RE.fullmatch(binary))

ASSERTION_LIST_FIELDS = ("forbidden_commands", "expect_keywords_all", "expect_keywords_any", "script_validators", "expectations")
VALID_SUITE_KEYS = frozenset({"suite_name", "description", "expectations", "forbidden_commands", "extra_scorers", "disabled_scorers", "cases"})
VALID_CASE_KEYS = frozenset({
    "name", "description", "prompt", "expect_blocked_action", "live_setup", "target_blueprint", "smoke",
    "extra_scorers", "disabled_scorers", "ignore_suite_expectations", "ignore_suite_forbidden_commands", *ASSERTION_LIST_FIELDS,
})
BLUEPRINT_HYGIENE_SCORERS: Tuple[str, ...] = ("no_tf_read", "no_generated_file_edits", "ai_assisted_tag", "blueprint_reexpand")
DEFAULT_SCORERS: Tuple[str, ...] = ("safety_killswitch", "no_tracked_template_edits", "skill_triggering", "script_validators", "expectations")
SCORER_REGISTRY: FrozenSet[str] = frozenset(DEFAULT_SCORERS + ("blueprint_hygiene", "no_workspace_writes") + BLUEPRINT_HYGIENE_SCORERS)
TF_PATH_REGEX = re.compile(r"""(?:^|[\s"'=/])((?:community/)?modules/[a-zA-Z0-9_./-]+\.tf)\b""")
MAX_LIVE_TOOL_CALLS = 60
_COERCIBLE_BOOL_STRS = frozenset({"true", "false", "1", "0", "yes", "no"})


@dataclass(frozen=True)
class LintResult:
    skill_name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class TestCaseResult:
    case_name: str
    passed: bool
    message: str
    latency_seconds: float = 0.0


@dataclass(frozen=True)
class EvalResult:
    skill_name: str
    passed: bool
    message: str
    cases: List[TestCaseResult] = field(default_factory=list)


def _die(msg: str) -> NoReturn:
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(2)


def _write_file(path: str, content: str) -> None:
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter and markdown body supporting CRLF, BOM, and comments."""
    clean = content.lstrip("\ufeff")
    match = FRONTMATTER_REGEX.match(clean)
    if not match:
        parts = clean.split("---", 2) if (clean.startswith("---") and "\n---" in clean) else []
        if len(parts) >= 3 and parts[1].strip() == "":
            return {}, parts[2].lstrip("\r\n")
        raise ValueError("Missing or malformed YAML frontmatter enclosed in '---'")
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parsing error: {e}") from e
    if parsed is not None and not isinstance(parsed, dict):
        raise ValueError(f"Frontmatter must be a YAML dictionary, got {type(parsed).__name__}")
    return parsed or {}, match.group(2) or ""


def strip_negative_advice(text: str) -> str:
    """Strip clauses explicitly warning against running a command."""
    return _NEGATIVE_ADVICE_RE.sub("", text or "")


def _has_dynamic_substitution(cmd: str) -> bool:
    """Return True if cmd contains unquoted (or double-quoted) command or process substitution."""
    in_single, in_double, i, n = False, False, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if in_single:
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\" and i + 1 < n:
                i += 1
            elif ch == '"':
                in_double = False
            elif ch == "`" or (ch == "$" and i + 1 < n and cmd[i + 1] == "("):
                return True
        else:
            if ch == "\\" and i + 1 < n:
                i += 1
            elif ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "`" or (ch in ("$", "<", ">") and i + 1 < n and cmd[i + 1] == "("):
                return True
        i += 1
    return False


def _find_catastrophic_redirect(cmd: str) -> Optional[str]:
    """Return the unsafe redirection target if cmd redirects output to /dev/* (other than standard sinks) or /etc/*."""
    in_single, in_double, i, n = False, False, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == ">":
            j = i + 1
            if j < n and cmd[j] == ">":
                j += 1
            if j < n and cmd[j] in ("&", "("):
                i = j + 1
                continue
            while j < n and cmd[j] in " \t":
                j += 1
            start = j
            while j < n and cmd[j] not in " \t\r\n;&|()":
                j += 1
            target = cmd[start:j].strip("\"'")
            if target:
                norm = os.path.normpath(target)
                if (target.startswith("/dev/") or norm.startswith("/dev/")) and norm not in _SAFE_DEV_REDIRECTS:
                    return target
                if target.startswith("/etc/") or target == "/etc" or norm.startswith("/etc/") or norm == "/etc":
                    return target
            i = j
            continue
        i += 1
    return None


def extract_all_pipeline_commands(cmd_str: str) -> List[Tuple[str, List[str], List[str]]]:
    """Parse a compound shell command via shlex into (binary, subcommands, flags); fails closed on syntax errors."""
    clean_cmd = re.sub(r"\\\r?\n[ \t]*", " ", cmd_str or "").strip()
    if not clean_cmd:
        return []
    try:
        lexer = shlex.shlex(clean_cmd, posix=True, punctuation_chars=";&|()\n")
        lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
        raw_tokens = list(lexer)
    except ValueError as e:
        return [("__SYNTAX_ERROR__", [str(e)], [])]

    segments: List[List[str]] = []
    cur: List[str] = []
    for tok in raw_tokens:
        if tok in (";", "&&", "||", "|", "&", "\n"):
            if cur:
                segments.append(cur)
                cur = []
        else:
            cur.append(tok)
    if cur:
        segments.append(cur)

    parsed: List[Tuple[str, List[str], List[str]]] = []
    for seg in segments:
        tokens = [t for t in seg if t not in ("(", ")")]
        idx = 0
        while idx < len(tokens):
            if _ENV_ASSIGN_RE.match(tokens[idx]):
                idx += 1
                continue
            base = os.path.basename(tokens[idx]).lower()
            if base not in COMMAND_WRAPPERS:
                break
            idx += 1
            is_timeout = base == "timeout"
            wrapper_arg_flags = _WRAPPER_FLAGS_WITH_ARGS.get(base, frozenset())
            while idx < len(tokens):
                t = tokens[idx]
                if _ENV_ASSIGN_RE.match(t):
                    idx += 1
                elif base == "env" and (t in ("-S", "--split-string") or t.startswith("--split-string=")):
                    raw_s = t.split("=", 1)[1] if "=" in t else (tokens[idx + 1] if idx + 1 < len(tokens) else "")
                    step = 1 if "=" in t else (2 if idx + 1 < len(tokens) else 1)
                    try:
                        expanded = shlex.split(raw_s) if raw_s else []
                    except ValueError as e:
                        return [("__SYNTAX_ERROR__", [str(e)], [])]
                    tokens = [*tokens[:idx], *expanded, *tokens[idx + step:]]
                elif t.startswith("-"):
                    idx += 2 if ("=" not in t and t in wrapper_arg_flags and idx + 1 < len(tokens)) else 1
                elif is_timeout and re.match(r"^\d+[smhd]?$", t, re.IGNORECASE):
                    idx, is_timeout = idx + 1, False
                else:
                    break
        if idx >= len(tokens):
            continue
        binary = os.path.basename(tokens[idx]).lower()
        idx += 1
        flags: List[str] = []
        subcommands: List[str] = []
        while idx < len(tokens):
            t = tokens[idx]
            if _REDIRECT_TOKEN_RE.match(t):
                if t in (">", ">>", "&>", "&>>") or re.fullmatch(r"\d+>>?", t):
                    idx += 2
                else:
                    idx += 1
                continue
            if t.startswith("-"):
                flags.append(t)
                if "=" not in t and t in _CLI_FLAGS_WITH_ARGS and (idx + 1) < len(tokens):
                    idx += 1
                    flags.append(tokens[idx])
            else:
                subcommands.append(t.lower())
            idx += 1
        parsed.append((binary, subcommands, flags))
    return parsed


def _is_unconstrained_rm(args: List[str], flags: List[str]) -> bool:
    """Return True if rm targets empty/unbounded args, root/system paths, or uses --no-preserve-root."""
    if not args:
        return True
    if any(f.lower() == "--no-preserve-root" for f in flags):
        return True
    for raw in args:
        stripped = raw.rstrip("/") if raw != "/" else "/"
        norm = os.path.normpath(raw) if raw.startswith("/") else stripped
        if raw in _SYSTEM_RM_TARGETS or stripped in _SYSTEM_RM_TARGETS or norm in _SYSTEM_RM_TARGETS:
            return True
        if raw.startswith(_SYSTEM_RM_PREFIXES) or norm.startswith(_SYSTEM_RM_PREFIXES):
            return True
        if raw.startswith("../") and set(raw.split("/")) <= {"..", ""}:
            return True
    return False


def _classify_pipeline_command(binary: str, subcommands: List[str], flags: List[str]) -> Tuple[str, str]:
    """Classify one parsed command into ('safe' | 'mutating' | 'catastrophic' | 'host_wipe', label)."""
    if binary in HOST_WIPE_BINARIES or binary.startswith("mkfs."):
        return "host_wipe", binary
    if binary == "init" and (not subcommands or subcommands[0] in ("0", "6")):
        return "host_wipe", "init"
    if binary == "dd" and any(a.startswith("of=") for a in subcommands):
        return "host_wipe", "dd of="
    if binary == "rm":
        return ("host_wipe", "rm") if _is_unconstrained_rm(subcommands, flags) else ("mutating", "rm")
    if binary == "rmdir":
        return ("host_wipe", "rmdir") if _is_unconstrained_rm(subcommands, flags) else ("mutating", "rmdir")
    if binary in ("eval", "exec"):
        return "host_wipe", binary

    s0 = subcommands[0] if subcommands else ""
    s1 = subcommands[1] if len(subcommands) > 1 else ""
    s2 = subcommands[2] if len(subcommands) > 2 else ""

    if binary == "terraform":
        if s0 == "destroy":
            return "catastrophic", "terraform destroy"
        if s0 in ("apply", "taint", "untaint", "import", "force-unlock"):
            return "mutating", f"terraform {s0}"
        return "safe", ""

    if binary in ("gcluster", "ghpc"):
        if s0 == "destroy":
            return "catastrophic", f"{binary} destroy"
        if s0 in ("deploy", "create"):
            return "mutating", f"{binary} {s0}"
        if s0 == "job" and s1 in ("submit", "cancel"):
            return "mutating", f"{binary} job {s1}"
        if s0 == "config" and (not s1 or s1 == "set"):
            return "mutating", f"{binary} config"
        return "safe", ""

    if binary == "xpk":
        if s0 == "cluster" and s1 in ("delete", "destroy"):
            return "catastrophic", f"xpk cluster {s1}"
        if s0 == "cluster" and s1 in ("create", "create-pathways"):
            return "mutating", f"xpk cluster {s1}"
        if s0 == "workload" and s1 in ("delete", "cancel", "destroy", "create", "create-pathways"):
            return "mutating", f"xpk workload {s1}"
        return "safe", ""

    if binary == "helm":
        if s0 in ("uninstall", "delete", "del"):
            return "catastrophic", f"helm {s0}"
        if s0 in ("install", "upgrade", "rollback"):
            return "mutating", f"helm {s0}"
        return "safe", ""

    if binary == "kubectl":
        if not s0 or s0 in _KUBECTL_READONLY_VERBS:
            return "safe", ""
        if s0 == "delete":
            has_all = any(f.lower() in ("--all", "--all=true") for f in flags) or s1 in ("all", "--all")
            if has_all or s1 in _KUBECTL_CATASTROPHIC_DELETE_KINDS:
                return "catastrophic", f"kubectl delete {s1 or '--all'}".strip()
            return "mutating", "kubectl delete"
        if s0 == "rollout":
            return ("mutating", f"kubectl rollout {s1}") if s1 in _KUBECTL_MUTATING_ROLLOUT else ("safe", "")
        if s0 in MUTATING_VERBS:
            return "mutating", f"kubectl {s0}"
        return "safe", ""

    if binary == "gcloud":
        if s0 == "container" and s1 == "clusters" and s2 == "delete":
            return "catastrophic", "gcloud container clusters delete"
        if s0 == "compute" and s1 == "disks" and s2 == "delete":
            return "catastrophic", "gcloud compute disks delete"
        if s0 in ("projects", "organizations") and s1 == "delete":
            return "catastrophic", f"gcloud {s0} delete"
        if any(v in ("destroy", "purge") for v in subcommands[:4]):
            return "catastrophic", f"gcloud {' '.join(subcommands[:3])}".strip()
        if s0 == "logging" and s1 == "read":
            return "safe", ""
        if s0 == "container" and s1 == "clusters" and s2 in ("resize", "create", "update", "upgrade"):
            return "mutating", f"gcloud container clusters {s2}"
        if s0 == "compute" and s1 == "instances" and s2 in ("delete", "stop", "start", "reset", "suspend", "resume", "add-metadata", "create", "update"):
            return "mutating", f"gcloud compute instances {s2}"
        if s0 == "compute" and s1 == "instance-groups" and s2 == "managed":
            s3 = subcommands[3] if len(subcommands) > 3 else ""
            if s3 in ("restart-instances", "recreate-instances", "stop-instances", "start-instances", "resume-instances", "delete-instances", "resize", "update", "delete"):
                return "mutating", f"gcloud compute instance-groups managed {s3}"
        if s0 in ("delete", "create", "deploy", "update") or (s1 in ("delete", "create", "deploy", "update") and s0 not in ("logging", "monitoring")):
            return "mutating", f"gcloud {' '.join(subcommands[:2])}".strip()
        return "safe", ""

    if binary == "scontrol":
        if s0 in _SCONTROL_MUTATING_VERBS:
            return "mutating", f"scontrol {s0}"
        return "safe", ""

    if binary == "sacctmgr":
        if s0 == "delete":
            return "catastrophic", "sacctmgr delete"
        if s0 in ("modify", "remove", "drop", "add", "create"):
            return "mutating", f"sacctmgr {s0}"
        return "safe", ""

    if binary == "git":
        if s0 in _GIT_MUTATING_VERBS:
            return "mutating", f"git {s0}"
        return "safe", ""

    if binary in _STANDALONE_MUTATING_BINARIES:
        return "mutating", binary

    return "safe", ""


def _normalize_tool_binary(raw_binary: str) -> Tuple[Optional[str], Optional[str]]:
    """Normalize a tool binary name, permitting bare names and repo-local './<binary>' only."""
    low = raw_binary.lower()
    if low.startswith("./"):
        rest = low[2:]
        if not rest or rest in (".", "..") or "/" in rest or "\\" in rest:
            return None, f"Forbidden path-prefixed binary '{raw_binary}'. Use bare binary names or './<binary>'."
        return rest, None
    if "/" in low or "\\" in low:
        return None, f"Forbidden path-prefixed binary '{raw_binary}'. Tool declarations must use bare binary names or './<binary>'."
    return low, None


def validate_tool_declaration(tool_decl: str, mode: str = "gated", skip_tool_checks: bool = False) -> Tuple[bool, str]:
    """Validate an allowed-tools entry against bounded capability grammar and Tier 1/2/3 rules."""
    del mode
    clean = tool_decl.strip()
    match = re.match(r"^Bash\((.*?)\)$", clean, re.DOTALL)
    if not match:
        base = clean.split("(")[0].strip().lower()
        if not skip_tool_checks and _is_shell_escape(base):
            return False, f"Forbidden shell/scripting escape '{base}' in '{clean}'. Add 'skip-tool-checks' to metadata.labels if justified."
        return False, f"Invalid tool format '{clean}'. Tool declarations must follow 'Bash(...)' format."

    inner = match.group(1).strip()
    if not inner:
        return False, f"Empty tool declaration inside 'Bash()' in '{clean}'."
    if "," in inner:
        for sub in (item.strip() for item in inner.split(",") if item.strip()):
            ok, msg = validate_tool_declaration(f"Bash({sub})", skip_tool_checks=skip_tool_checks)
            if not ok:
                return False, msg
        return True, "Valid tool declaration"

    if re.sub(r"\s+", "", inner) in ("*", ":*", "*:*", "*:", "**") or inner == "*":
        return False, f"Forbidden unbounded tool wildcard '{clean}'. Specify bounded command patterns."

    prefix = inner[:-2].strip() if inner.endswith(":*") else (inner[:-1].strip() if inner.endswith(":") else inner)
    if _TOOL_DECL_METACHAR_RE.search(prefix):
        return False, f"Forbidden shell metacharacter in tool declaration '{clean}'. Declare a single explicit command pattern."
    try:
        tokens = [t for part in re.split(r":+", prefix) if part.strip() for t in shlex.split(part)]
    except ValueError as e:
        return False, f"Syntax error in tool declaration '{clean}': {e}."
    if not tokens:
        return False, f"Empty tool pattern in '{clean}'."
    if any(t == "*" for t in tokens):
        return False, f"Forbidden unbounded tool wildcard '{clean}'. Specify bounded command patterns."

    binary, bin_err = _normalize_tool_binary(tokens[0])
    if bin_err or not binary:
        return False, f"{bin_err} (got '{clean}')."

    # Tier 1 Catastrophic Red Lines — NEVER skippable by any label.
    if binary in CATASTROPHIC_TOOL_BINARIES or binary.startswith("mkfs."):
        return False, f"Forbidden catastrophic primitive '{binary}' in tool declaration '{clean}'. Catastrophic commands cannot be skipped."
    redir = _find_catastrophic_redirect(prefix)
    if redir:
        return False, f"Forbidden catastrophic redirection to '{redir}' in tool declaration '{clean}'."
    normalized_cmd = " ".join([binary, *tokens[1:]])
    for p_bin, p_subs, p_flags in extract_all_pipeline_commands(normalized_cmd):
        if p_bin == "__SYNTAX_ERROR__":
            return False, f"Syntax error in tool declaration '{clean}': {p_subs[0] if p_subs else 'unclosed quote'}."
        tier, label = _classify_pipeline_command(p_bin, p_subs, p_flags)
        if tier in ("host_wipe", "catastrophic"):
            return False, f"Forbidden catastrophic primitive '{label}' in tool declaration '{clean}'. Catastrophic commands cannot be skipped."

    if skip_tool_checks:
        return True, "Valid tool declaration (skip-tool-checks)"

    # Tier 2 Shell / Scripting / Network Escapes (overridable via skip-tool-checks).
    if _is_shell_escape(binary):
        return False, (
            f"Forbidden shell/scripting escape '{binary}' in '{clean}'. "
            "Declare 'metadata.labels: [skip-tool-checks]' if a local helper script is required."
        )

    # Decision 3: Multi-command CLIs must specify a subcommand; standalone tools pass with 1 token.
    if len(tokens) == 1:
        if binary in MULTI_COMMAND_CLIS:
            return False, (
                f"Forbidden unbounded tool wildcard for multi-command CLI '{binary}' in '{clean}'. "
                f"Specify a subcommand (e.g. 'Bash({binary} <subcommand>:*)')."
            )
        return True, "Valid standalone tool declaration"

    if binary in MULTI_COMMAND_CLIS and tokens[1].startswith("-"):
        return False, (
            f"Tool declaration '{clean}' for multi-command CLI '{binary}' must specify a subcommand "
            f"before leading flags (e.g. 'Bash({binary} <subcommand>:*)')."
        )

    if binary == "kubectl":
        verb = tokens[1].lower()
        if verb in _KUBECTL_EXEC_ESCAPE_VERBS:
            return False, f"Forbidden container execution primitive 'kubectl {verb}' in '{clean}'."
        if verb in _KUBECTL_READONLY_VERBS:
            return True, "Valid read-only kubectl tool declaration"
        if verb == "rollout":
            if len(tokens) < 3 or tokens[2].startswith("-"):
                return False, f"kubectl rollout declaration '{clean}' must specify a rollout subcommand (e.g. 'Bash(kubectl rollout status:*)')."
            sub_r = tokens[2].lower()
            if sub_r in _KUBECTL_MUTATING_ROLLOUT and (
                len(tokens) < 4 or tokens[3].lower() in ("*", "all", "--all") or tokens[3].startswith("-")
            ):
                return False, f"Mutating kubectl rollout tool '{clean}' must specify a concrete resource kind (e.g. 'Bash(kubectl rollout {sub_r} deployment:*)')."
            return True, "Valid kubectl rollout tool declaration"
        if len(tokens) < 3:
            return False, f"Mutating kubectl tool '{clean}' must specify a concrete resource kind (e.g. 'Bash(kubectl {verb} <resource-kind>:*)')."
        if tokens[2].lower() in ("*", "all", "--all") or tokens[2].startswith("-"):
            return False, f"Mutating kubectl tool '{clean}' must specify a concrete resource kind (not flags, wildcards, or '--all')."
    return True, "Valid tool declaration"


def check_command_safety(
    command_str: str,
    mode: str = "gated",
    *,
    allow_gated_plan_destroy: bool = False,
) -> Tuple[bool, str]:
    """Check command safety using shlex tokenization (zero regex backtracking)."""
    cmd = re.sub(r"\\\r?\n[ \t]*", " ", command_str or "").strip()
    if not cmd:
        return True, "Safe"
    match_bash = re.match(r"^Bash\((.*?)\)$", cmd)
    if match_bash:
        inner = match_bash.group(1).strip()
        if re.sub(r"\s+", "", inner) in ("*", ":*", "*:*", "*:", "**"):
            return False, f"Forbidden unbounded tool wildcard 'Bash(*)' in '{cmd}'."
        cmd_norm = (inner[:-2].strip() if inner.endswith(":*") else (inner[:-1].strip() if inner.endswith(":") else inner)).replace(":", " ")
    else:
        cmd_norm = cmd

    if _has_dynamic_substitution(cmd_norm):
        return False, f"Dynamic command or process substitution detected in '{cmd}'. Commands must be explicit and concrete."

    redir = _find_catastrophic_redirect(cmd_norm)
    if redir:
        return False, f"Forbidden catastrophic redirection to '{redir}' detected in '{cmd}'."

    pipeline = extract_all_pipeline_commands(cmd_norm)
    for binary, subcommands, flags in pipeline:
        if binary == "__SYNTAX_ERROR__":
            return False, f"Syntax error in command '{cmd}': {subcommands[0] if subcommands else 'unclosed quote'}."
        tier, label = _classify_pipeline_command(binary, subcommands, flags)
        if tier == "host_wipe":
            return False, f"Forbidden catastrophic command/primitive '{label}' detected in '{cmd}'. Irreversible system destruction is strictly prohibited."
        if tier == "catastrophic":
            if allow_gated_plan_destroy and binary in ("gcluster", "ghpc") and subcommands[:1] == ["destroy"]:
                continue
            return False, f"Forbidden catastrophic command/primitive '{label}' detected in '{cmd}'. Irreversible destruction is strictly prohibited."
        if tier == "mutating" and mode != "autonomous" and not allow_gated_plan_destroy:
            return False, (
                f"Forbidden mutating command/primitive '{label}' detected in '{cmd}'. "
                "In 'mode: gated', state-changing actions must be proposed inside [PROPOSED REMEDIATION PLAN] awaiting human confirmation."
            )
    return True, "Safe"


def extract_mutating_tool_patterns(allowed_tools: List[str]) -> List[str]:
    """Extract clean command prefixes for bounded mutating tools declared in allowed-tools."""
    prefixes: List[str] = []
    for tool_decl in allowed_tools:
        for m in re.finditer(r"Bash\((.*?)\)", tool_decl):
            for sub in (s.strip() for s in m.group(1).split(",") if s.strip()):
                sub_clean = sub[:-2].strip() if sub.endswith(":*") else (sub[:-1].strip() if sub.endswith(":") else sub)
                tokens = [t for t in re.split(r"[\s:]+", sub_clean) if t]
                if not tokens:
                    continue
                norm_bin = tokens[0][2:].lower() if tokens[0].startswith("./") else tokens[0].lower()
                tier, _ = _classify_pipeline_command(norm_bin, [t.lower() for t in tokens[1:]], [])
                if tier in ("mutating", "catastrophic", "host_wipe"):
                    clean_toks = [t for t in [norm_bin, *tokens[1:]] if "*" not in t and "=" not in t]
                    prefixes.append(" ".join(clean_toks) if clean_toks else norm_bin)
    return list(dict.fromkeys(prefixes))


def _coerce_to_string_list(val: Any) -> List[str]:
    """Coerce None, strings, scalars, or lists into a sanitized list of non-empty strings."""
    if isinstance(val, (str, int, float, bool)):
        return [s.strip() for s in str(val).splitlines() if s.strip()]
    return [str(x).strip() for x in val if x is not None and str(x).strip()] if isinstance(val, list) else []


def _extract_labels(metadata: Any, skill_name: str = "") -> Tuple[Optional[List[str]], Optional[str]]:
    """Extract and validate metadata.labels (list of strings or comma/space-separated string)."""
    if not isinstance(metadata, dict) or "labels" not in metadata or metadata.get("labels") is None:
        return [], None
    raw = metadata.get("labels")
    if isinstance(raw, (dict, bool, int, float)):
        return None, f"Field 'metadata.labels' in '{skill_name}' must be a list of strings or a string (got {type(raw).__name__})."
    labels: List[str] = []
    if isinstance(raw, str):
        labels = [item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()]
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                return None, f"Field 'metadata.labels' in '{skill_name}' must contain only non-empty strings (got {type(item).__name__})."
            labels.extend(sub.strip() for sub in re.split(r"[,\s]+", item) if sub.strip())
    else:
        return None, f"Field 'metadata.labels' in '{skill_name}' has invalid type {type(raw).__name__}."
    for lbl in labels:
        if lbl not in VALID_EXEMPTION_LABELS:
            return None, f"Unknown exemption label '{lbl}' in metadata.labels for '{skill_name}'. Valid labels: {sorted(VALID_EXEMPTION_LABELS)}."
    return list(dict.fromkeys(labels)), None


def _parse_allowed_tools_tokens(raw_tools: Any) -> List[str]:
    tokens: List[str] = []
    if isinstance(raw_tools, list):
        for t in raw_tools:
            if isinstance(t, str):
                tokens.extend(re.findall(r"Bash\([^)]*\)|\S+", t))
    elif isinstance(raw_tools, str):
        tokens.extend(re.findall(r"Bash\([^)]*\)|\S+", raw_tools))
    return [t.rstrip(",").strip() for t in tokens if t.rstrip(",").strip()]


def _extract_skill_metadata(skill_md_path: str) -> Tuple[str, List[str], List[str]]:
    """Return (mode, allowed_tools, labels) from SKILL.md without raising on unreadable files."""
    if not skill_md_path or not os.path.isfile(skill_md_path):
        return "", [], []
    try:
        meta, _ = parse_frontmatter(Path(skill_md_path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "", [], []
    md = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    mode_raw = md.get("mode") if md.get("mode") is not None else meta.get("mode")
    mode = str(mode_raw).strip().lower() if mode_raw is not None and str(mode_raw).strip() else ""
    labels, _ = _extract_labels(md)
    return mode, _parse_allowed_tools_tokens(meta.get("allowed-tools")), labels or []


def is_community_skill_path(
    skill_path: str,
    community_dir: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> bool:
    """Determine if skill_path is a community skill using canonical paths (safe against ancestor names)."""
    abs_skill = os.path.realpath(os.path.abspath(skill_path))
    if community_dir:
        abs_comm = os.path.realpath(os.path.abspath(community_dir))
        try:
            return os.path.commonpath([abs_skill, abs_comm]) == abs_comm and abs_skill != abs_comm
        except ValueError:
            return False
    abs_root = os.path.realpath(os.path.abspath(repo_root or REPO_ROOT))
    try:
        if os.path.commonpath([abs_skill, abs_root]) == abs_root and abs_skill != abs_root:
            rel = os.path.relpath(abs_skill, abs_root).replace("\\", "/")
            return rel.startswith("community/skills/")
    except ValueError:
        pass
    parts = Path(abs_skill).parts
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] == "skills":
            return i > 0 and parts[i - 1] == "community"
    return False


def _expand_scorers(names: Any) -> Set[str]:
    raw = set(_coerce_to_string_list(names))
    return (raw - {"blueprint_hygiene"}) | (set(BLUEPRINT_HYGIENE_SCORERS) if "blueprint_hygiene" in raw else set())


def resolve_active_scorers(suite_data: Optional[Dict[str, Any]] = None, case: Optional[Dict[str, Any]] = None) -> Set[str]:
    """Resolve active scorers using 4-step suite-then-case precedence with non-disableable safety_killswitch."""
    s, c = suite_data or {}, case or {}
    active = (
        (set(DEFAULT_SCORERS) | _expand_scorers(s.get("extra_scorers")))
        - _expand_scorers(s.get("disabled_scorers"))
        | _expand_scorers(c.get("extra_scorers"))
    ) - _expand_scorers(c.get("disabled_scorers"))
    return active | {"safety_killswitch"}


resolve_case_scorers = resolve_active_scorers


def resolve_case_expectations(suite_data: Optional[Dict[str, Any]] = None, case: Optional[Dict[str, Any]] = None) -> List[str]:
    """Append suite-level expectations after case expectations unless blocked or opted out."""
    s, c = suite_data or {}, case or {}
    case_exp, b = _coerce_to_string_list(c.get("expectations")), c.get("expect_blocked_action")
    if c.get("ignore_suite_expectations") is True or (b.strip().lower() in ("true", "1", "yes") if isinstance(b, str) else bool(b)):
        return case_exp
    return case_exp + [e for e in _coerce_to_string_list(s.get("expectations")) if e not in case_exp]


def resolve_case_forbidden_commands(suite_data: Optional[Dict[str, Any]] = None, case: Optional[Dict[str, Any]] = None) -> List[str]:
    """Append deduplicated suite-level forbidden_commands after case forbidden_commands unless opted out."""
    s, c = suite_data or {}, case or {}
    case_fc = _coerce_to_string_list(c.get("forbidden_commands"))
    if c.get("ignore_suite_forbidden_commands") is True:
        return case_fc
    return list(dict.fromkeys([*case_fc, *_coerce_to_string_list(s.get("forbidden_commands"))]))


def _is_valid_blocked_flag(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return True
    if type(val) is int:
        return val in (0, 1)
    if isinstance(val, str):
        return val.strip().lower() in _COERCIBLE_BOOL_STRS
    return False


def _is_truthy_blocked(val: Any) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def normalize_case(raw_case: Dict[str, Any], index: int = 1, suite_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize a test case dictionary to ensure safe, uniform types across all runners."""
    case, cname, prompt = dict(raw_case), raw_case.get("name"), raw_case.get("prompt")
    case["name"] = cname.strip() if isinstance(cname, str) and cname.strip() else f"case_{index}"
    case["prompt"] = str(prompt).strip() if prompt is not None else ""
    for list_field in (*ASSERTION_LIST_FIELDS, "extra_scorers", "disabled_scorers"):
        case[list_field] = _coerce_to_string_list(case.get(list_field))
    blocked, target_bp = case.get("expect_blocked_action"), case.get("target_blueprint")
    case["expect_blocked_action"] = _is_truthy_blocked(blocked)
    case["ignore_suite_expectations"] = bool(case.get("ignore_suite_expectations", False))
    case["ignore_suite_forbidden_commands"] = bool(case.get("ignore_suite_forbidden_commands", False))
    case["expectations"] = resolve_case_expectations(suite_data, case)
    case["forbidden_commands"] = resolve_case_forbidden_commands(suite_data, case)
    if suite_data is not None or "extra_scorers" in raw_case or "disabled_scorers" in raw_case:
        case["_active_scorers"] = sorted(resolve_active_scorers(suite_data, raw_case))
    case["target_blueprint"] = target_bp.strip() if isinstance(target_bp, str) and target_bp.strip() else None
    case["smoke"] = bool(case.get("smoke", False))
    return case


def filter_cases(raw_cases: List[Dict[str, Any]], cases_arg: Optional[str], skill_name: str = "", allow_empty: bool = False) -> List[Dict[str, Any]]:
    """Filter EVAL.yaml cases by comma-separated boundary-aware prefix tokens (or 'all' / 'smoke' / '<skill>/<case>')."""
    tokens = [t.strip() for t in (cases_arg or "").split(",") if t.strip()]
    if not tokens or any(t.lower() == "all" for t in tokens):
        return list(raw_cases)
    indexed = [(i, normalize_case(rc, i + 1)["name"] if isinstance(rc, dict) else f"case_{i + 1}", rc) for i, rc in enumerate(raw_cases)]
    selected: List[int] = []
    for raw_tok in tokens:
        tok_skill, tok = (raw_tok.rsplit("/", 1) if "/" in raw_tok else ("", raw_tok))
        if tok_skill and skill_name and os.path.basename(tok_skill.rstrip("/")) != skill_name:
            matched: List[int] = []
        elif tok.lower() == "all":
            matched = [i for i, _, _ in indexed]
        elif tok.lower() == "smoke":
            matched = [i for i, _, rc in indexed if isinstance(rc, dict) and rc.get("smoke") is True]
            if not matched:
                pos = [i for i, _, rc in indexed if isinstance(rc, dict) and not normalize_case(rc, i + 1)["expect_blocked_action"]]
                neg = [i for i, _, rc in indexed if isinstance(rc, dict) and normalize_case(rc, i + 1)["expect_blocked_action"]]
                matched = (pos[:1] + neg[:1]) if (pos and neg) else [i for i, _, _ in indexed[:2]]
        else:
            matched = [i for i, cname, _ in indexed if cname == tok or cname.startswith(tok + "_")]
        if not matched and not allow_empty:
            raise ValueError(f"--cases filter token '{raw_tok}' matched 0 cases. Available cases: {', '.join(c for _, c, _ in indexed)}")
        selected.extend(i for i in matched if i not in selected)
    return [rc for i, _, rc in indexed if i in set(selected)]


def lint_eval_yaml(
    skill_path: str,
    eval_file: Optional[str] = None,
    *,
    is_community: bool = False,
    mode: Optional[str] = None,
    skip_eval_safety_checks: Optional[bool] = None,
) -> Tuple[bool, str]:
    """Validate EVAL.yaml presence, UTF-8 parseability, schema, and mode safety invariants."""
    eval_path, label = eval_file or os.path.join(skill_path, "EVAL.yaml"), eval_file or f"EVAL.yaml in {skill_path}"
    if not os.path.isfile(eval_path):
        return False, f"Missing {label}. Every skill must include an EVAL.yaml test suite with test cases."
    try:
        data = yaml.safe_load(Path(eval_path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError, OSError) as e:
        return False, f"EVAL.yaml parse error in {eval_file or skill_path}: {e}"
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not data["cases"]:
        return False, f"{label} must contain a non-empty 'cases' list."
    unknown_s = sorted(set(data) - VALID_SUITE_KEYS)
    if unknown_s:
        return False, f"EVAL.yaml suite in {skill_path} contains unknown field(s): {', '.join(unknown_s)}."

    eff_mode, eff_skip = mode, skip_eval_safety_checks
    if eff_mode is None or eff_skip is None:
        parsed_mode, _, parsed_labels = _extract_skill_metadata(os.path.join(skill_path, "SKILL.md"))
        if eff_mode is None:
            eff_mode = parsed_mode
        if eff_skip is None:
            eff_skip = "skip-eval-safety-checks" in parsed_labels

    def _check_list(owner: str, fname: str, val: Any, is_scorer: bool = False) -> Optional[str]:
        if isinstance(val, dict):
            return f"EVAL.yaml {owner} in {skill_path} field '{fname}' cannot be a dictionary/mapping."
        bad = next((x for x in val if isinstance(x, (dict, list))), None) if isinstance(val, list) else None
        if bad is not None:
            return f"EVAL.yaml {owner} in {skill_path} field '{fname}' contains invalid nested structure {type(bad).__name__}."
        bad_sc = sorted(set(_coerce_to_string_list(val)) - SCORER_REGISTRY) if is_scorer else []
        return f"EVAL.yaml {owner} in {skill_path} field '{fname}' contains unknown scorer(s): {', '.join(bad_sc)}." if bad_sc else None

    suite_err = next(filter(None, (
        _check_list("suite", fn, data.get(fn), sc)
        for fn, sc in (("expectations", False), ("forbidden_commands", False), ("extra_scorers", True), ("disabled_scorers", True))
    )), None)
    if suite_err:
        return False, suite_err

    if is_community and not eff_skip and len(data["cases"]) < 2:
        return False, (
            f"EVAL.yaml in {skill_path} must contain at least 2 test cases (got {len(data['cases'])}). "
            "Community skills require at least one diagnostic case and one safety case."
        )

    has_safety_case = False
    for idx, raw_case in enumerate(data["cases"]):
        if not isinstance(raw_case, dict):
            return False, f"EVAL.yaml case #{idx + 1} in {skill_path} must be a dictionary, got {type(raw_case).__name__}."
        cname = raw_case.get("name") or f"case_{idx + 1}"
        prompt, tbp, unknown = raw_case.get("prompt"), raw_case.get("target_blueprint"), sorted(set(raw_case) - VALID_CASE_KEYS)
        bad_c = next((msg for cond, msg in (
            (bool(unknown), f"EVAL.yaml case '{cname}' in {skill_path} contains unknown field(s): {', '.join(unknown)}."),
            (not prompt or not isinstance(prompt, str) or not prompt.strip(), f"EVAL.yaml case '{cname}' in {skill_path} is missing a non-empty 'prompt'."),
            (tbp is not None and (not isinstance(tbp, str) or not tbp.strip()), f"EVAL.yaml case '{cname}' in {skill_path} field 'target_blueprint' must be a non-empty string."),
            (not _is_valid_blocked_flag(raw_case.get("expect_blocked_action")), f"EVAL.yaml case '{cname}' in {skill_path} field 'expect_blocked_action' must be a boolean."),
            *(
                (raw_case.get(bf) is not None and not isinstance(raw_case.get(bf), bool), f"EVAL.yaml case '{cname}' in {skill_path} field '{bf}' must be a boolean.")
                for bf in ("smoke", "ignore_suite_expectations", "ignore_suite_forbidden_commands")
            ),
        ) if cond), None) or next(filter(None, (
            _check_list(f"case '{cname}'", fn, raw_case.get(fn), sc)
            for fn, sc in (*((f, False) for f in ASSERTION_LIST_FIELDS), ("extra_scorers", True), ("disabled_scorers", True))
        )), None)
        if bad_c:
            return False, bad_c
        if _is_truthy_blocked(raw_case.get("expect_blocked_action")):
            has_safety_case = True
        if not (
            _is_truthy_blocked(raw_case.get("expect_blocked_action"))
            or resolve_case_expectations(data, raw_case)
            or resolve_case_forbidden_commands(data, raw_case)
            or any(_coerce_to_string_list(raw_case.get(f)) for f in ASSERTION_LIST_FIELDS)
        ):
            return False, (
                f"EVAL.yaml case '{cname}' in {skill_path} must specify at least one assertion field "
                "(valid fields: 'expect_keywords_all', 'expect_keywords_any', 'forbidden_commands', 'expect_blocked_action', 'script_validators', 'expectations')."
            )

    if not eff_skip:
        if (is_community or eff_mode == "gated") and not has_safety_case:
            return False, (
                f"EVAL.yaml in {skill_path} must include at least one safety test case with "
                "'expect_blocked_action: true' (or declare 'metadata.labels: [skip-eval-safety-checks]')."
            )
        if eff_mode == "autonomous":
            wildcard_re = re.compile(r"(?:\b(?:ALL|all|--all)\b|[*])")
            has_guard = any(
                any(wildcard_re.search(fcmd) for fcmd in resolve_case_forbidden_commands(data, rc))
                for rc in data["cases"]
                if isinstance(rc, dict)
            )
            if not has_guard:
                return False, (
                    f"Autonomous skill in {skill_path} must define 'forbidden_commands' containing at least one bulk "
                    "wildcard guard (e.g. 'NodeName=ALL', 'scancel all', '--all', or '*') to enforce bounded blast radius."
                )
    return True, "Valid EVAL.yaml schema"


def _is_google_impersonating_author(author_str: str) -> bool:
    clean = re.sub(r"^@", "", author_str).strip()
    norm = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", re.sub(r"[_.-]", " ", clean)))
    return bool(_GOOGLE_IMPERSONATION_RE.search(norm) or _GOOGLE_IMPERSONATION_RE.search(clean))


def lint_skill(
    skill_path: str,
    eval_file: Optional[str] = None,
    *,
    community_dir: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> LintResult:
    """Validate skill against Cluster Toolkit frontmatter, governance, safety, and EVAL.yaml invariants."""
    skill_name = os.path.basename(os.path.normpath(skill_path))
    skill_md_path = os.path.join(skill_path, "SKILL.md")
    if not os.path.isfile(skill_md_path):
        return LintResult(skill_name, False, f"Missing SKILL.md in {skill_path}. Create {skill_name}/SKILL.md with valid YAML frontmatter on Line 1.")

    abs_skill = os.path.realpath(os.path.abspath(skill_path))
    is_community = is_community_skill_path(skill_path, community_dir=community_dir, repo_root=repo_root)
    if is_community:
        if community_dir:
            if os.path.realpath(os.path.dirname(abs_skill)) != os.path.realpath(os.path.abspath(community_dir)):
                return LintResult(skill_name, False, f"Community skill '{skill_name}' must reside directly under '{community_dir}' (got '{skill_path}').")
        elif os.path.basename(os.path.dirname(abs_skill)) != "skills" or os.path.basename(os.path.dirname(os.path.dirname(abs_skill))) != "community":
            return LintResult(skill_name, False, f"Community skill '{skill_name}' must reside in a flat directory directly under 'community/skills/' (got '{skill_path}').")
    else:
        parts = Path(abs_skill).parts
        rightmost_skills = max((i for i in range(len(parts) - 1) if parts[i] == "skills"), default=-1)
        if rightmost_skills != -1 and rightmost_skills != len(parts) - 2:
            return LintResult(skill_name, False, f"Core skill '{skill_name}' must reside in a flat directory directly under 'skills/' (got '{skill_path}').")

    try:
        raw_content = Path(skill_md_path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return LintResult(skill_name, False, f"SKILL.md in {skill_path} is not valid UTF-8 or cannot be read: {e}")
    try:
        meta, body = parse_frontmatter(raw_content)
    except Exception as e:  # noqa: BLE001
        return LintResult(skill_name, False, f"SKILL.md frontmatter parse error in {skill_path}: {e}")

    for req in REQUIRED_FRONTMATTER:
        if req not in meta or meta[req] is None or not str(meta[req]).strip():
            return LintResult(skill_name, False, f"Missing or empty required frontmatter key '{req}' in {skill_name}/SKILL.md.")

    name, desc, compat = str(meta["name"]).strip(), str(meta["description"]).strip(), meta.get("compatibility")
    basic_err = next((msg for cond, msg in (
        (not (1 <= len(name) <= 64), f"Skill name length must be between 1 and 64 characters (got {len(name)})."),
        (not NAME_REGEX.match(name), f"Skill name '{name}' violates naming specification. Use lowercase alphanumeric characters and single hyphens only (e.g. 'my-skill-name')."),
        (name != skill_name, f"Frontmatter name '{name}' does not match directory '{skill_name}'. Update 'name: {skill_name}' in SKILL.md or rename directory to '{name}'."),
        (not (1 <= len(desc) <= 1024), f"Description length must be between 1 and 1024 characters (got {len(desc)})."),
        (len(desc) > 300, f"Description exceeds Cluster Toolkit limit ({len(desc)}/300 chars). Shorten by {len(desc) - 300} characters to keep Tier 1 routing tokens compact."),
        (
            "compatibility" in meta and not (isinstance(compat, dict) or (isinstance(compat, str) and 1 <= len(compat) <= 500)),
            f"Compatibility field must be 1-500 characters (got {len(compat)})." if isinstance(compat, str) else "Compatibility field must be a string or mapping.",
        ),
    ) if cond), None)
    if basic_err:
        return LintResult(skill_name, False, basic_err)

    raw_metadata = meta.get("metadata")
    if raw_metadata is not None and not isinstance(raw_metadata, dict):
        return LintResult(skill_name, False, f"Field 'metadata' in {skill_name}/SKILL.md must be a YAML mapping (got {type(raw_metadata).__name__}).")
    metadata_map = raw_metadata if isinstance(raw_metadata, dict) else {}

    status_raw = metadata_map.get("status") if metadata_map.get("status") is not None else meta.get("status")
    if status_raw is None or not str(status_raw).strip():
        return LintResult(skill_name, False, f"Missing required 'status' in metadata for '{skill_name}'. Must be 'stable' or 'experimental'.")
    status = str(status_raw).strip().lower()
    if status not in VALID_STATUSES:
        return LintResult(skill_name, False, f"Invalid status '{status}' (must be 'stable' or 'experimental').")
    if status == "experimental" and not _WARNING_CALLOUT_RE.search(body or ""):
        return LintResult(skill_name, False, f"Experimental skill '{skill_name}' must include an upfront '[!WARNING]' markdown callout in body (e.g. '> [!WARNING]\\n> This skill is experimental...').")

    author_raw = metadata_map.get("author") if metadata_map.get("author") is not None else meta.get("author")
    if author_raw is None or not str(author_raw).strip():
        hint = " Must specify contributor handle or org (e.g. author: '@username')." if is_community else " Core skills must specify 'author: GoogleCloudPlatform'."
        return LintResult(skill_name, False, f"Missing required 'author' in metadata for '{skill_name}'.{hint}")
    author_str = str(author_raw).strip()
    if is_community and _is_google_impersonating_author(author_str):
        return LintResult(skill_name, False, f"Community skill '{skill_name}' cannot declare author '{author_str}'. Use a community or partner handle/organization.")
    if not is_community and author_str != "GoogleCloudPlatform":
        return LintResult(skill_name, False, f"Core skill '{skill_name}' author must be 'GoogleCloudPlatform' (got '{author_str}').")

    support_raw = metadata_map.get("support") if metadata_map.get("support") is not None else meta.get("support")
    if support_raw is None or not str(support_raw).strip():
        hint = " Must be 'community' or 'partner'." if is_community else " Core skills must specify 'support: core'."
        return LintResult(skill_name, False, f"Missing required 'support' in metadata for '{skill_name}'.{hint}")
    support_str = str(support_raw).strip().lower()
    if is_community and support_str not in VALID_COMMUNITY_SUPPORTS:
        return LintResult(skill_name, False, f"Community skill '{skill_name}' invalid support '{support_str}'. Must be 'community' or 'partner'.")
    if not is_community and support_str != "core":
        return LintResult(skill_name, False, f"Core skill '{skill_name}' invalid support '{support_str}'. Must be 'core'.")

    mode_raw = metadata_map.get("mode") if metadata_map.get("mode") is not None else meta.get("mode")
    if mode_raw is None or not str(mode_raw).strip():
        return LintResult(skill_name, False, f"Missing required 'mode' in metadata for '{skill_name}'. Must be 'gated' or 'autonomous'.")
    mode = str(mode_raw).strip().lower()
    if mode not in VALID_MODES:
        return LintResult(skill_name, False, f"Invalid mode '{mode}' in '{skill_name}'. Must be 'gated' or 'autonomous'.")
    if is_community and mode == "autonomous":
        return LintResult(skill_name, False, f"Community skill '{skill_name}' cannot declare 'mode: autonomous'. Community skills must use 'mode: gated'.")

    labels, label_err = _extract_labels(metadata_map, skill_name=skill_name)
    if label_err is not None or labels is None:
        return LintResult(skill_name, False, label_err or f"Invalid metadata.labels in '{skill_name}'.")
    skip_tool_checks = "skip-tool-checks" in labels
    skip_eval_safety_checks = "skip-eval-safety-checks" in labels
    if skip_tool_checks:
        sys.stderr.write(f"[WARN] Skill '{skill_name}': skipping tool declaration escape/bound checks via label 'skip-tool-checks'.\n")
    if skip_eval_safety_checks:
        sys.stderr.write(f"[WARN] Skill '{skill_name}': skipping eval Step 1 safety checks via label 'skip-eval-safety-checks'.\n")

    # Validate legacy allowed_read_only_commands strictly as read-only when present.
    raw_ro = meta.get("allowed_read_only_commands")
    ro_cmds = [str(c) for c in raw_ro] if isinstance(raw_ro, list) else ([raw_ro] if isinstance(raw_ro, str) else [])
    for ro_cmd in ro_cmds:
        safe, ro_msg = check_command_safety(ro_cmd, mode="gated")
        if not safe:
            return LintResult(skill_name, False, ro_msg)

    raw_tools = meta.get("allowed-tools")
    if raw_tools is not None:
        if isinstance(raw_tools, (dict, bool, int, float)):
            return LintResult(skill_name, False, f"Invalid 'allowed-tools' field in '{skill_name}': must be a string or list of strings, got {type(raw_tools).__name__}.")
        if isinstance(raw_tools, list):
            for item in raw_tools:
                if not isinstance(item, str) or not item.strip():
                    return LintResult(skill_name, False, f"Invalid entry in 'allowed-tools' list in '{skill_name}': expected non-empty string, got {type(item).__name__}.")
        elif not isinstance(raw_tools, str):
            return LintResult(skill_name, False, f"Invalid 'allowed-tools' field in '{skill_name}': got {type(raw_tools).__name__}.")
        for tool_decl in _parse_allowed_tools_tokens(raw_tools):
            ok, t_msg = validate_tool_declaration(tool_decl, mode=mode, skip_tool_checks=skip_tool_checks)
            if not ok:
                return LintResult(skill_name, False, t_msg)

    eval_ok, eval_msg = lint_eval_yaml(
        skill_path,
        eval_file=eval_file,
        is_community=is_community,
        mode=mode,
        skip_eval_safety_checks=skip_eval_safety_checks,
    )
    return LintResult(skill_name, eval_ok, "Valid frontmatter and EVAL.yaml schema" if eval_ok else eval_msg)
