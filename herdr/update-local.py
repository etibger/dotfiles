#!/usr/bin/env python3
"""Build upstream Herdr with PR 4281 and atomically select the validated binary."""

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse


FIX_COMMIT = "3b045ba3b4de422a665f70f6dce718c7a2cb5a63"
UPSTREAM_URL = "https://github.com/herdrdev/herdr.git"
REGRESSION = "copy_mode_repeat_during_projection_gap_stays_active"


def say(message):
    print(message, flush=True)


def run(args, cwd, env, check=True):
    result = subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(map(str, args))}\n{result.stdout}")
    return result


def git(repo, env, *args, check=True):
    return run(["git", "-c", "core.fsmonitor=false", "-C", repo, *args],
               repo, env, check=check)


def check_tools(env):
    say("Checking build prerequisites...")
    problems = []
    tools = [
        ("Git", "git", "git", ["--version"]),
        ("just", "just", "just", ["--version"]),
        ("curl", "curl", "curl", ["--version"]),
        ("Zig", env.get("ZIG", "zig"), "zig", ["version"]),
        # --version can inspect the active compiler; --help avoids toolchain downloads.
        ("rustup", "rustup", "rustup", ["--help"]),
        # Do not invoke the Cargo proxy yet: it can download a missing toolchain.
        ("Cargo (rustup proxy)", "cargo", "rustup", []),
        ("cargo-nextest", "cargo-nextest", "cargo-nextest", ["--version"]),
    ]
    if sys.platform == "darwin":
        # These also match upstream's macOS build-tool setup.
        tools.extend((
            ("CMake", "cmake", "cmake", ["--version"]),
            ("Ninja", "ninja", "ninja", ["--version"]),
        ))
    for label, executable, formula, version_args in tools:
        available = shutil.which(executable, path=env.get("PATH"))
        problem = None
        if not available:
            problem = f"{label}: {executable} is missing from PATH."
        elif version_args:
            try:
                probe = run([executable, *version_args], Path.cwd(), env, check=False)
                if probe.returncode:
                    problem = f"{label}: {executable} cannot run (exit {probe.returncode})."
            except OSError as error:
                problem = f"{label}: {executable} cannot run ({error})."
        if problem:
            action = "reinstall" if available else "install"
            problem += f"\n    Run: brew {action} {formula}"
            if formula == "rustup":
                problem += '\n    Then: export PATH="$(brew --prefix rustup)/bin:$PATH"'
            if label == "Zig" and "ZIG" in env:
                problem += "\n    Also correct or unset your ZIG executable override."
            problems.append(problem)
    if sys.platform == "darwin":
        sdk_ok = True
        for command in (["xcode-select", "-p"], ["xcrun", "--find", "clang"],
                        ["xcrun", "--find", "clang++"], ["xcrun", "--find", "ld"],
                        ["xcrun", "--show-sdk-path"]):
            try:
                probe = run(command, Path.cwd(), env, check=False)
                if probe.returncode or not probe.stdout.strip() or not Path(probe.stdout.strip()).exists():
                    sdk_ok = False
                    break
            except OSError:
                sdk_ok = False
                break
        if not sdk_ok:
            problems.append("Apple Command Line Tools / macOS SDK are unavailable."
                            "\n    Run: xcode-select --install"
                            "\n    Complete the installer, then rerun this script.")
    if problems:
        message = "Missing or unusable build prerequisites:\n\n" + "\n\n".join(
            "- " + problem for problem in problems
        )
        if not shutil.which("brew", path=env.get("PATH")):
            message += ("\n\nHomebrew is not on PATH. Install it from https://brew.sh "
                        "to use the brew commands above, or install the tools manually.")
        raise RuntimeError(message + "\n\nInstall the missing prerequisites and rerun this script.")
    say("Build tools and native compiler/SDK checks passed.")


def check_checkout_tools(source, env):
    problems = []
    manifest = source / "vendor/libghostty-vt/build.zig.zon"
    required = re.search(r'\.minimum_zig_version\s*=\s*"([^"]+)"', manifest.read_text())
    actual = run([env.get("ZIG", "zig"), "version"], source, env).stdout.strip()
    if required and actual != required.group(1):
        problems.append(f"Zig {required.group(1)} is required; found {actual}."
                        "\n    Download the matching build from https://ziglang.org/download/"
                        "\n    Then: export ZIG=/absolute/path/to/the/matching/zig")
    toolchain = (source / "rust-toolchain.toml").read_text()
    channel = re.search(r'^\s*channel\s*=\s*"([^"]+)"', toolchain, re.MULTILINE)
    if not channel:
        raise RuntimeError("Cannot determine the Rust version from rust-toolchain.toml.")
    channel = channel.group(1)
    components_match = re.search(r'^\s*components\s*=\s*\[([^]]*)\]', toolchain, re.MULTILINE)
    components = re.findall(r'"([^"]+)"', components_match.group(1)) if components_match else []
    # An explicit rustup run (without --install) checks without downloading anything.
    probe_env = dict(env, RUSTUP_TOOLCHAIN=channel)
    rust_ok = all(run(["rustup", "run", channel, tool, "--version"], source,
                      probe_env, check=False).returncode == 0 for tool in ("rustc", "cargo"))
    missing_components = []
    if rust_ok and components:
        installed = run(["rustup", "component", "list", "--toolchain", channel, "--installed"],
                        source, probe_env, check=False)
        names = installed.stdout.splitlines() if installed.returncode == 0 else []
        missing_components = [component for component in components if not any(
            name == component or name.startswith(component + "-") for name in names
        )]
    if not rust_ok or missing_components:
        detail = "is missing or unusable" if not rust_ok else "is missing components: " + ", ".join(missing_components)
        command = ["rustup", "toolchain", "install", channel, "--profile", "minimal"]
        for component in components:
            command.extend(["--component", component])
        settings = " ".join(f"{key}={shlex.quote(env[key])}" for key in
                            ("RUSTUP_HOME", "CARGO_HOME", "TMPDIR") if key in env)
        problems.append(f"Rust {channel} {detail} in the updater's isolated toolchain directory."
                        f"\n    Run: {settings} {shlex.join(command)}")
    if problems:
        raise RuntimeError("Checkout toolchain requirements are not satisfied:\n\n" +
                           "\n\n".join("- " + problem for problem in problems) +
                           "\n\nInstall the required versions and rerun this script.")
    env["RUSTUP_TOOLCHAIN"] = channel
    # Confirm that Cargo can invoke the test runner with the selected toolchain.
    result = run(["cargo", "nextest", "--version"], source, env, check=False)
    if result.returncode:
        raise RuntimeError("Cargo cannot run cargo-nextest.\n"
                           "    Run: brew install cargo-nextest\n"
                           "    Ensure its bin directory is on PATH.\n" + result.stdout)
    say(f"Checkout toolchains ready: Rust {channel}, Zig {actual}, cargo-nextest.")


def apply_fix(source, env, fix):
    if git(source, env, "merge-base", "--is-ancestor", fix, "HEAD",
           check=False).returncode == 0:
        say("The fix is already in upstream history.")
        return
    result = git(source, env, "cherry-pick", "--no-commit", fix, check=False)
    if result.returncode:
        # Git can report an empty cherry-pick after an upstream squash/rebase.
        clean = all(git(source, env, *args, check=False).returncode == 0 for args in (
            ("diff", "--quiet"), ("diff", "--cached", "--quiet"),
        ))
        unmerged = git(source, env, "ls-files", "--unmerged").stdout.strip()
        if not clean or unmerged:
            raise RuntimeError("The copy-mode patch needs manual rebasing.\n" + result.stdout)
        # Only accept the empty-patch case, not arbitrary Git failures.
        reverse = git(source, env, "show", "--format=", "--binary", fix).stdout
        probe = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "apply", "--reverse", "--check"],
            cwd=source, env=env, input=reverse, text=True, capture_output=True,
        )
        if probe.returncode:
            raise RuntimeError(result.stdout)
        git(source, env, "cherry-pick", "--quit")
        say("The patch is already present in upstream.")
    else:
        say("Applied the copy-mode patch in the build worktree.")


def cache_tls_downloads(output, source, run_dir, env, attempted):
    if "TlsInitializationFailed" not in output:
        return False
    urls = set(re.findall(r'\.url\s*=\s*"(https://[^"\s]+)"', output))
    urls -= attempted
    if not urls:
        return False
    vendor = source / "vendor/libghostty-vt"
    # Read the expected Zig package hashes from the actual checked-out manifests.
    packages = {}
    for manifest in vendor.rglob("build.zig.zon"):
        content = manifest.read_text()
        for url, package_hash in re.findall(
            r'\.url\s*=\s*"([^"]+)"[^{}]*?\.hash\s*=\s*"([^"]+)"', content
        ):
            if url in packages and packages[url] != package_hash:
                raise RuntimeError(f"Conflicting pinned hashes for {url}")
            packages[url] = package_hash
    for url in sorted(urls):
        expected = packages.get(url)
        if not expected:
            raise RuntimeError(f"Cannot find a pinned Zig package hash for {url}")
        filename = Path(urlparse(url).path).name
        archive = run_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + "-" + filename)
        say(f"Retrying Zig download with curl: {url}")
        run(["curl", "--fail", "--location", "--retry", "3",
             "--connect-timeout", "30", "--max-time", "600",
             "--proto", "=https", "--proto-redir", "=https",
             "--output", archive, url], source, env)
        actual = run([env.get("ZIG", "zig"), "fetch", archive], vendor, env).stdout.strip()
        if actual != expected:
            raise RuntimeError(f"Zig hash mismatch for {url}: expected {expected}, got {actual}")
        attempted.add(url)
        say(f"Verified Zig package hash: {actual}")
    return True


def build_step(args, source, run_dir, env, attempted, log):
    for _ in range(20):
        say("Running: " + " ".join(args))
        output = []
        with subprocess.Popen(args, cwd=source, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
                output.append(line)
            code = process.wait()
        if code == 0:
            return
        if not cache_tls_downloads("".join(output), source, run_dir, env, attempted):
            raise RuntimeError(f"{' '.join(args)} failed (exit {code}).")
    raise RuntimeError("Stopped after 20 dependency-download retries.")


def install_binary(binary, install_dir, run_dir, tree, env):
    selected = install_dir / "herdr-pr4281"
    if os.path.lexists(selected) and not selected.is_symlink():
        raise RuntimeError(f"Refusing to replace a non-symlink: {selected}")
    install_dir.mkdir(parents=True, exist_ok=True)
    if install_dir.stat().st_dev != run_dir.stat().st_dev:
        raise RuntimeError("Install directory and checkout must be on the same filesystem "
                           "for atomic installation.")
    staged = run_dir / "herdr-new"
    shutil.copyfile(binary, staged)
    staged.chmod(0o755)
    say(run([staged, "--version"], run_dir, env).stdout.strip())
    digest = hashlib.sha256(staged.read_bytes()).hexdigest()[:12]
    versioned = install_dir / f"herdr-pr4281-{tree[:12]}-{digest}"
    if os.path.lexists(versioned):
        if versioned.is_symlink() or not versioned.is_file() or versioned.read_bytes() != staged.read_bytes():
            raise RuntimeError(f"Refusing to overwrite a different build: {versioned}")
        staged.unlink()
    else:
        os.replace(staged, versioned)
    previous = os.readlink(selected) if selected.is_symlink() else None
    next_link = run_dir / "next-herdr"
    next_link.symlink_to(versioned.name)
    os.replace(next_link, selected)
    say(f"Installed: {selected} -> {versioned.name}")
    if previous:
        say(f"Previous build retained: {previous}")


def update(args, repo, state, env):
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=state))
    env["TMPDIR"] = str(run_dir)
    source = run_dir / "source"
    say(f"Build files and logs: {run_dir}")
    try:
        say("Fetching origin/master...")
        git(repo, env, "fetch", "--no-tags", "origin",
            "+refs/heads/master:refs/remotes/origin/master")
        upstream = git(repo, env, "rev-parse", "refs/remotes/origin/master").stdout.strip()
        if git(repo, env, "cat-file", "-e", args.fix_commit + "^{commit}",
               check=False).returncode:
            git(repo, env, "fetch", "--no-tags", "origin", args.fix_commit)
        fix = git(repo, env, "rev-parse", args.fix_commit + "^{commit}").stdout.strip()
        say(f"Upstream: {upstream}\nCopy-mode fix: {fix}")
        git(repo, env, "worktree", "add", "--detach", source, upstream)
        apply_fix(source, env, fix)
        tree = git(source, env, "write-tree").stdout.strip()
        check_checkout_tools(source, env)
        attempted = set()
        with (run_dir / "build.log").open("w") as log:
            build_step(["just", "test-one", REGRESSION], source, run_dir, env, attempted, log)
            build_step(["just", "build"], source, run_dir, env, attempted, log)
        binary = Path(env["CARGO_TARGET_DIR"]) / "release/herdr"
        say(run([binary, "--version"], source, env).stdout.strip())
        if args.build_only:
            say(f"Validated build: {binary}\nInstallation skipped (--build-only).")
        else:
            install_binary(binary, args.install_dir.expanduser().absolute(), run_dir, tree, env)
        result = git(repo, env, "worktree", "remove", "--force", source, check=False)
        if result.returncode:
            say(f"Build succeeded; worktree cleanup needs attention:\n{result.stdout}")
        say("Running sessions are unchanged. Restart them when ready to use the new build.")
    except BaseException:
        say(f"Update did not complete. Diagnostic files retained at: {run_dir}")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "Checks build prerequisites and prints installation instructions for missing tools. "
        "Clones herdrdev/herdr if the checkout directory is missing. "
        "Fetches origin/master into a separate worktree; your checkout is preserved. "
        "Reuses private/tmp/to_persist/herdr-pr4281 build caches. "
        "Keeps logs and failed worktrees under private/tmp/to_persist/herdr-update. "
        "Does not stop sessions or modify Homebrew."
    ))
    parser.add_argument("--repo", type=Path, default=Path.home() / "Projects/herdr-local")
    parser.add_argument("--install-dir", type=Path, default=Path.home() / ".local/bin")
    parser.add_argument("--fix-commit", default=FIX_COMMIT, help="copy-mode commit (default: PR 4281)")
    parser.add_argument("--build-only", action="store_true", help="test and build without installing")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.fix_commit):
        parser.error("--fix-commit must be a full 40-character commit SHA")
    env = os.environ.copy()
    rustup_bin = Path("/opt/homebrew/opt/rustup/bin")
    if rustup_bin.is_dir():
        env["PATH"] = str(rustup_bin) + os.pathsep + env.get("PATH", "")
    check_tools(env)
    repo = args.repo.expanduser().absolute()
    if not os.path.lexists(repo):
        repo.parent.mkdir(parents=True, exist_ok=True)
        say(f"Checkout not found; cloning {UPSTREAM_URL} into {repo}...")
        run(["git", "-c", "core.fsmonitor=false", "clone", "--", UPSTREAM_URL, repo],
            repo.parent, env)
    repo = repo.resolve(strict=True)
    root = Path(git(repo, env, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != repo:
        parser.error("--repo must name the root of the Herdr checkout")
    cache = repo / "private/tmp/to_persist/herdr-pr4281"
    state = repo / "private/tmp/to_persist/herdr-update"
    state.mkdir(parents=True, exist_ok=True)
    for key, name in (("CARGO_HOME", "cargo"), ("RUSTUP_HOME", "rustup"),
                      ("CARGO_TARGET_DIR", "target"), ("ZIG_GLOBAL_CACHE_DIR", "zig-global"),
                      ("ZIG_LOCAL_CACHE_DIR", "zig-local")):
        env[key] = str(cache / name)
    env.pop("RUSTUP_TOOLCHAIN", None)
    env.pop("CARGO_BUILD_TARGET", None)
    # The lock is deliberately retained; unlinking it can let concurrent runs overlap.
    with (state / "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another local Herdr update is already running")
        update(args, repo, state, env)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
