#!/usr/bin/env python3
"""Build a wheel, install it in a venv and test it inside an offline namespace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

EXCLUDED = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache"}


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(n for n in names if n not in EXCLUDED and not n.endswith(".egg-info"))
        for name in names + files:
            if (Path(directory) / name).is_symlink():
                raise RuntimeError("Check inputs must not contain symlinks")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = Path(directory) / name
            if not path.is_file():
                raise RuntimeError("Check inputs must be regular files")
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


TEST_RUNNER = r'''
import json, sys, unittest
suite = unittest.defaultTestLoader.discover(sys.argv[1], pattern='test*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('LIGA_TEST_RESULT=' + json.dumps({'suite':sys.argv[1], 'run':result.testsRun,
    'failures':len(result.failures), 'errors':len(result.errors), 'skipped':len(result.skipped)}), flush=True)
if result.testsRun == 0 or result.skipped or not result.wasSuccessful():
    raise SystemExit(1)
'''

INNER = r'''
import hashlib, json, os, pathlib, shutil, socket, subprocess, sys, zipfile
status = pathlib.Path('/proc/self/status').read_text()
assert int(next(x.split()[1] for x in status.splitlines() if x.startswith('CapEff:')),16)==0
assert next(x.split()[1] for x in status.splitlines() if x.startswith('NoNewPrivs:'))=='1'
assert not pathlib.Path('/home/martin').exists()
try:
    with socket.create_connection(('1.1.1.1',443),timeout=0.1):
        raise AssertionError('Network unexpectedly available')
except OSError:
    pass
for path in ['/source', *(['/acceptance'] if pathlib.Path('/acceptance').exists() else [])]:
    try:
        pathlib.Path(path,'write-probe').write_text('must fail')
    except OSError:
        pass
    else:
        raise AssertionError('Test inputs are writable')
shutil.copytree('/source','/tmp/build-source')
os.chdir('/tmp/build-source')
from setuptools.build_meta import build_wheel
wheel_name=build_wheel('/tmp/wheels')
wheel_path=pathlib.Path('/tmp/wheels',wheel_name)
with zipfile.ZipFile(wheel_path) as package:
    names=package.namelist()
    assert any(n.endswith('/licenses/LICENSE') or n.endswith('.dist-info/LICENSE') for n in names)
    entry=next(n for n in names if n.endswith('.dist-info/entry_points.txt'))
    assert 'liga-local = liga_local.cli:main' in package.read(entry).decode()
    metadata=package.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
    assert not any(line.startswith('Requires-Dist:') for line in metadata.splitlines())
os.chdir('/tmp')
subprocess.run([sys.executable,'-B','-s','-m','venv','--without-pip','/tmp/venv'],check=True)
python='/tmp/venv/bin/python'
subprocess.run([sys.executable,'-B','-s','-m','pip','--python',python,'install','--no-index',
    '--no-deps','--disable-pip-version-check',str(wheel_path)],check=True)
env=dict(os.environ,LIGA_LOCAL_CLI='/tmp/venv/bin/liga-local')
subprocess.run([python,'-I','-B','/source/scripts/check.py','--inner-tests','/source/tests'],env=env,check=True)
if pathlib.Path('/acceptance').exists():
    subprocess.run([python,'-I','-B','/source/scripts/check.py','--inner-tests','/acceptance'],env=env,check=True)
subprocess.run(['/tmp/venv/bin/liga-local','--help'],env=env,check=True,stdout=subprocess.DEVNULL)
subprocess.run([python,'-I','-B','-m','liga_local','--help'],env=env,check=True,stdout=subprocess.DEVNULL)
print('LIGA_BUILD_RESULT='+json.dumps({'wheel':wheel_name,'wheel_sha256':hashlib.sha256(wheel_path.read_bytes()).hexdigest(),
    'venv_installed':True,'source_read_only':True,'offline':True,'cap_eff':0,'no_new_privs':True,'python':sys.version.split()[0]}),flush=True)
'''


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--inner-tests":
        sys.argv = [sys.argv[0], sys.argv[2]]
        exec(compile(TEST_RUNNER, "<fixed-test-runner>", "exec"), {"__name__": "__main__"})
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    before = inventory(root)
    acceptance = args.acceptance.resolve() if args.acceptance else None
    frozen = inventory(acceptance) if acceptance else None
    if not shutil.which("bwrap") or not shutil.which("setpriv"):
        parser.error("Linux, bubblewrap and util-linux/setpriv are required")
    with tempfile.TemporaryDirectory(prefix="liga-local-check-") as temporary:
        stage = Path(temporary) / "source"
        stage.mkdir()
        for name in before:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        assert inventory(stage) == before
        command = ["bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv"]
        for directory in ("/usr", "/bin", "/lib", "/lib64", "/opt"):
            if Path(directory).exists():
                command += ["--ro-bind", directory, directory]
        # Distro pip may import requests against the public system CA bundle
        # even with --no-index. Mount only that public file, never all of /etc.
        ca_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
        if ca_bundle.is_file():
            command += ["--dir", "/etc/ssl/certs", "--ro-bind", str(ca_bundle), str(ca_bundle)]
        command += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/home", "--dir", "/empty-home"]
        command += ["--ro-bind", str(stage), "/source", "--chdir", "/tmp"]
        if acceptance:
            command += ["--ro-bind", str(acceptance), "/acceptance"]
        for key, value in {"HOME":"/empty-home", "PATH":"/usr/bin:/bin", "LC_ALL":"C.UTF-8", "PYTHONDONTWRITEBYTECODE":"1", "PIP_NO_INDEX":"1", "PIP_DISABLE_PIP_VERSION_CHECK":"1"}.items():
            command += ["--setenv", key, value]
        command += ["/usr/bin/setpriv", "--no-new-privs", sys.executable, "-B", "-s", "-c", INNER]
        completed = subprocess.run(command, check=False, timeout=180)
        assert inventory(stage) == before, "Staged source changed"
    assert inventory(root) == before, "Original source changed"
    if acceptance:
        assert inventory(acceptance) == frozen, "Independent tests changed"
    proof = {"returncode":completed.returncode,
             "source_sha256":hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
             "acceptance_sha256":hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest() if frozen else None}
    if args.receipt:
        args.receipt.write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps(proof))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
