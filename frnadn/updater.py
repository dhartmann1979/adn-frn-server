"""Dashboard updates from GitHub: check, fast-forward install, dependencies, restart.

The check asks the GitHub API (no login, a few requests per hour) whether the configured
branch has commits the local checkout does not have. "Upgrade" is deliberately narrow:
it only fast-forwards the checkout to the branch of the git remote ``origin`` that is
configured on disk, only to the exact commit the administrator saw, never over local
changes, with git hooks and the ext transport switched off and no shell involved.

The checkout is usually owned by root while the dashboard runs as its own service user.
Every git call therefore passes ``safe.directory`` for this checkout on the command line;
without it git refuses to work ("dubious ownership") and no update is ever reported.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "dhartmann1979/adn-frn-server"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,100}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIREMENT_FILES = ("requirements.txt",)
HELP_PERMISSIONS = "Run once as root: cd {root} && sudo ./scripts/update.sh (sets the file permissions that updates from the admin portal need)."


class UpdateError(Exception):
    pass


# ------------------------------------------------------------------ git
def _git_args(*args: str) -> List[str]:
    return ["git", "-C", str(ROOT), "-c", f"safe.directory={ROOT}", "-c", "core.hooksPath=/dev/null",
            "-c", "protocol.ext.allow=never", "-c", "credential.helper=", *args]


def _env() -> Dict[str, str]:
    home = os.environ.get("HOME") or str(ROOT)
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/true", "SSH_ASKPASS": "/bin/true", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def _run(*args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(_git_args(*args), capture_output=True, text=True, timeout=timeout, env=_env())
    except FileNotFoundError:
        raise UpdateError("git is not installed (apt install git).")
    except (OSError, subprocess.SubprocessError) as e:
        raise UpdateError(f"git could not be run: {e}")


def _git(*args: str, timeout: float = 120) -> str:
    r = _run(*args, timeout=timeout)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        raise UpdateError(f"git {args[0]} failed: {msg[-1] if msg else r.returncode}")
    return r.stdout.strip()


def package_version() -> str:
    try:
        text = (ROOT / "frnadn" / "__init__.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
        return m.group(1) if m else ""
    except OSError:
        return ""


def local_version() -> Dict[str, Any]:
    """{'version', 'commit', 'short', 'date', 'branch', 'error'} – commit is empty without a usable git checkout."""
    info: Dict[str, Any] = {"version": package_version(), "commit": "", "short": "", "date": "", "branch": "", "error": ""}
    if not (ROOT / ".git").exists():
        info["error"] = "No git checkout: the dashboard was installed without .git."
        return info
    try:
        line = _git("log", "-1", "--format=%H|%cI", timeout=10)
        commit, _, date = line.partition("|")
        info.update(commit=commit, short=commit[:7], date=date, branch=_git("rev-parse", "--abbrev-ref", "HEAD", timeout=10))
    except UpdateError as e:
        info["error"] = str(e)
    return info


def writable() -> bool:
    """Can the running user change the checkout? (needed for the upgrade button)"""
    git_dir = ROOT / ".git"
    return git_dir.exists() and os.access(git_dir, os.W_OK) and os.access(ROOT, os.W_OK)


# ------------------------------------------------------------------ GitHub check
def _fetch(url: str, timeout: float = 12, raw: bool = False) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "frn-adn-update", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise UpdateError("GitHub rate limit reached – check again later.")
        if e.code == 404:
            raise UpdateError("Repository or branch not found on GitHub.")
        raise UpdateError(f"GitHub answered with HTTP {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"GitHub not reachable: {getattr(e, 'reason', e)}")
    return data if raw else json.loads(data)


def _remote_version(repo: str, ref: str) -> str:
    try:
        text = _fetch(f"https://raw.githubusercontent.com/{repo}/{ref}/frnadn/__init__.py", raw=True)
        m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
        return m.group(1) if m and VERSION_RE.match(m.group(1)) else ""
    except UpdateError:
        return ""


_cache: Dict[str, Any] = {}


def check(repo: str = DEFAULT_REPO, branch: str = "main", force: bool = False, max_age: float = 600) -> Dict[str, Any]:
    """Compare the local commit with the newest commit of repo/branch on GitHub. Never raises."""
    repo, branch = (repo or DEFAULT_REPO).strip(), (branch or "main").strip()
    key = f"{repo}@{branch}"
    hit = _cache.get(key)
    if hit and not force and time.time() - hit["checked_at"] < max_age:
        return hit
    loc = local_version()
    res: Dict[str, Any] = {"ok": False, "repo": repo, "branch": branch, "local": loc, "latest": None, "update": False,
                           "behind": 0, "commits": [], "remote_version": "", "error": "", "checked_at": time.time(),
                           "can_upgrade": False, "hint": "", "url": f"https://github.com/{repo}"}
    if not REPO_RE.match(repo) or not BRANCH_RE.match(branch):
        res["error"] = "Invalid repository or branch name."
    else:
        try:
            head = _fetch(f"https://api.github.com/repos/{repo}/commits/{branch}")
            sha = head.get("sha", "")
            c = head.get("commit") or {}
            res["latest"] = {"commit": sha, "short": sha[:7], "date": (c.get("committer") or {}).get("date", ""),
                             "message": (c.get("message") or "").split("\n")[0][:140]}
            res["ok"] = True
            if not loc["commit"]:
                res["error"] = loc["error"] or "The local version is unknown."
                res["hint"] = HELP_PERMISSIONS.format(root=ROOT)
            elif sha and sha != loc["commit"]:
                cmp_ = _fetch(f"https://api.github.com/repos/{repo}/compare/{loc['commit']}...{sha}")
                res["behind"] = int(cmp_.get("ahead_by") or 0)
                res["update"] = cmp_.get("status") in ("ahead", "diverged") and res["behind"] > 0
                res["commits"] = [{"short": (x.get("sha") or "")[:7],
                                   "message": ((x.get("commit") or {}).get("message") or "").split("\n")[0][:140],
                                   "date": ((x.get("commit") or {}).get("committer") or {}).get("date", "")}
                                  for x in reversed(cmp_.get("commits") or [])][:10]
                res["url"] = f"https://github.com/{repo}/compare/{loc['short']}...{sha[:7]}"
                if cmp_.get("status") == "diverged":
                    res["hint"] = "This dashboard has its own commits – it cannot simply be moved forward."
                res["remote_version"] = _remote_version(repo, sha)
            res["can_upgrade"] = bool(res["update"] and writable() and _fast_forwardable(res))
            if res["update"] and not writable():
                res["hint"] = HELP_PERMISSIONS.format(root=ROOT)
        except UpdateError as e:
            res["error"] = str(e)
        except (ValueError, KeyError, TypeError) as e:
            res["error"] = f"Unexpected answer from GitHub: {e}"
    _cache[key] = res
    return res


def _fast_forwardable(res: Dict[str, Any]) -> bool:
    """A diverged checkout cannot be fast-forwarded."""
    return not res.get("hint", "").startswith("This dashboard has its own commits")


# ------------------------------------------------------------------ installing
def install(branch: str = "main", expected: str = "") -> Dict[str, Any]:
    """Fast-forward to origin/<branch> if that is exactly ``expected``. Returns what changed."""
    branch = (branch or "main").strip()
    expected = (expected or "").strip().lower()
    if not BRANCH_RE.match(branch) or branch.startswith("-") or ".." in branch:
        raise UpdateError("Invalid branch name.")
    if expected and not SHA_RE.match(expected):
        raise UpdateError("Please check for updates first.")
    if not (ROOT / ".git").exists():
        raise UpdateError("This is not a git checkout – update by hand (scripts/update.sh).")
    if not writable():
        raise UpdateError("The dashboard user may not write to the program directory. " + HELP_PERMISSIONS.format(root=ROOT))
    current = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=10)
    if current != branch:
        raise UpdateError(f"The checkout is on branch '{current}', not '{branch}'.")
    dirty = _git("status", "--porcelain", "--untracked-files=no", timeout=20)
    if dirty:
        files = ", ".join(line.split(maxsplit=1)[-1] for line in dirty.splitlines()[:5])
        raise UpdateError(f"Files were changed by hand ({files}). Update on the console, or undo the changes first (git stash).")
    old = _git("rev-parse", "HEAD", timeout=10)
    _git("fetch", "--no-tags", "--quiet", "origin", f"refs/heads/{branch}", timeout=180)
    new = _git("rev-parse", "FETCH_HEAD", timeout=10)
    if expected and new != expected:
        raise UpdateError(f"GitHub has a different version now ({new[:7]} instead of {expected[:7]}). Please check again.")
    if new == old:
        return {"ok": True, "changed": False, "old": old, "new": new, "files": [], "requirements_changed": False}
    if _run("merge-base", "--is-ancestor", old, new, timeout=20).returncode != 0:
        raise UpdateError("This dashboard has its own commits – it cannot simply be moved forward. Update by hand.")
    files = [f for f in _git("diff", "--name-only", old, new, timeout=30).splitlines() if f]
    _git("merge", "--ff-only", "--quiet", new, timeout=60)
    _cache.clear()
    req_changed = any(f in REQUIREMENT_FILES for f in files)
    pip_out = ""
    if req_changed:
        pip_out = install_requirements()
    return {"ok": True, "changed": True, "old": old, "new": new, "files": files[:200], "requirements_changed": req_changed,
            "pip": pip_out, "version": package_version()}


def install_requirements() -> str:
    """pip install -r requirements.txt with the interpreter that runs the dashboard (its venv)."""
    req = ROOT / "requirements.txt"
    if not req.exists():
        return ""
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], capture_output=True,
                           text=True, timeout=600, env={**_env(), "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    except (OSError, subprocess.SubprocessError) as e:
        raise UpdateError(f"Python packages could not be installed: {e}")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [str(r.returncode)]
        raise UpdateError(f"The code is updated, but the Python packages are not ({tail[0]}). Please run sudo ./scripts/update.sh.")
    return (r.stdout or "")[-500:]


def under_systemd() -> bool:
    """True if a service manager will start the dashboard again after it exits."""
    return bool(os.environ.get("INVOCATION_ID"))
