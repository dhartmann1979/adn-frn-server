"""Dashboard update: fast-forward install in a throw-away git checkout (no network, no fastapi)."""
import subprocess

import pytest

from frnadn import updater


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "frnadn").mkdir()
    (origin / "frnadn" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    (origin / "requirements.txt").write_text("")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "one")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    monkeypatch.setattr(updater, "ROOT", work)
    updater._cache.clear()
    return origin, work


def push_commit(origin, text="2"):
    (origin / "frnadn" / "__init__.py").write_text(f'__version__ = "1.0.{text}"\n')
    git(origin, "commit", "-qam", f"commit {text}")
    return git(origin, "rev-parse", "HEAD")


def test_local_version_and_writable(repos):
    _, work = repos
    info = updater.local_version()
    assert info["version"] == "1.0.0" and len(info["commit"]) == 40 and info["branch"] == "main" and not info["error"]
    assert updater.writable()


def test_install_fast_forwards_to_expected_commit(repos):
    origin, work = repos
    new = push_commit(origin)
    result = updater.install("main", new)
    assert result["changed"] and result["new"] == new and "frnadn/__init__.py" in result["files"]
    assert updater.package_version() == "1.0.2"
    assert updater.install("main", new)["changed"] is False          # already current


def test_install_refuses_unexpected_commit(repos):
    origin, _ = repos
    push_commit(origin)
    with pytest.raises(updater.UpdateError, match="different version"):
        updater.install("main", "0" * 40)


def test_install_refuses_local_changes(repos):
    origin, work = repos
    new = push_commit(origin)
    (work / "frnadn" / "__init__.py").write_text("# edited by hand\n")
    with pytest.raises(updater.UpdateError, match="changed by hand"):
        updater.install("main", new)


def test_install_refuses_diverged_checkout(repos):
    origin, work = repos
    new = push_commit(origin)
    (work / "own.txt").write_text("x")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "own commit")
    with pytest.raises(updater.UpdateError, match="own commits"):
        updater.install("main", new)


def test_install_rejects_bad_input(repos):
    with pytest.raises(updater.UpdateError):
        updater.install("--upload-pack=x", "")
    with pytest.raises(updater.UpdateError):
        updater.install("main", "not-a-sha")


def test_safe_directory_is_passed_so_foreign_owned_checkouts_work(repos):
    _, work = repos
    assert f"safe.directory={work}" in updater._git_args("status")


def test_no_git_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    info = updater.local_version()
    assert info["commit"] == "" and "git" in info["error"].lower()
    with pytest.raises(updater.UpdateError):
        updater.install("main", "")
