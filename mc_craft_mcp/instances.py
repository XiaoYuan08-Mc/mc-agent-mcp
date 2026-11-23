"""Instance registry and PortableMC runtime control."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from . import config, resolve

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
LOADERS = ("vanilla", "fabric", "quilt", "forge", "neoforge")


class InstanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Instance:
    name: str
    mc_version: str
    loader: str = "vanilla"
    loader_version: str = ""
    created: str = field(default_factory=_now)
    notes: str = ""
    last_launch: dict = field(default_factory=dict)

    # --- paths ---------------------------------------------------------
    @property
    def dir(self) -> Path:
        return config.instances_dir() / self.name

    @property
    def meta_path(self) -> Path:
        return self.dir / "instance.json"

    @property
    def logs_dir(self) -> Path:
        p = self.dir / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # --- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mc_version": self.mc_version,
            "loader": self.loader,
            "loader_version": self.loader_version,
            "created": self.created,
            "notes": self.notes,
            "last_launch": self.last_launch,
            "dir": str(self.dir),
        }

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, name: str) -> "Instance":
        meta = config.instances_dir() / name / "instance.json"
        if not meta.exists():
            raise InstanceError(f"实例不存在: {name}")
        data = json.loads(meta.read_text(encoding="utf-8"))
        inst = cls(
            name=data["name"],
            mc_version=data["mc_version"],
            loader=data.get("loader", "vanilla"),
            loader_version=data.get("loader_version", ""),
            created=data.get("created", _now()),
            notes=data.get("notes", ""),
            last_launch=data.get("last_launch") or {},
        )
        return inst

    # --- portablemc ----------------------------------------------------
    def version_spec(self) -> str:
        loader = self.loader.lower()
        if loader == "vanilla":
            return self.mc_version
        if loader in ("fabric", "quilt"):
            return f"{loader}:{self.mc_version}:{self.loader_version}"
        if loader in ("forge", "neoforge"):
            if not self.loader_version:
                raise InstanceError(f"{loader} 需要显式 loader_version，不允许猜")
            return f"{loader}::{self.loader_version}"
        raise InstanceError(f"未知 loader: {loader}")


def list_instances() -> list[dict]:
    out = []
    base = config.instances_dir()
    for meta in sorted(base.glob("*/instance.json")):
        try:
            out.append(json.loads(meta.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def create_instance(
    name: str,
    mc_version: str,
    loader: str = "vanilla",
    loader_version: str = "",
    notes: str = "",
) -> Instance:
    if not NAME_RE.match(name):
        raise InstanceError("实例名只能包含字母数字 . _ -，且不超过 40 字符")
    loader = loader.lower().strip()
    if loader not in LOADERS:
        raise InstanceError(f"loader 必须是 {', '.join(LOADERS)}")
    if (config.instances_dir() / name / "instance.json").exists():
        raise InstanceError(f"实例已存在: {name}")

    if loader in ("fabric", "quilt") and not loader_version:
        loader_version = resolve.fabric_loader_version(mc_version)
    if loader in ("forge", "neoforge") and not loader_version:
        raise InstanceError(f"{loader} 必须给出准确 loader_version（不要猜版本号）")

    inst = Instance(name=name, mc_version=mc_version, loader=loader,
                    loader_version=loader_version, notes=notes)
    for sub in ("mods", "resourcepacks", "shaderpacks", "saves", "config", "logs"):
        (inst.dir / sub).mkdir(parents=True, exist_ok=True)
    inst.save()
    return inst


def _portablemc(args: list[str], *, timeout: float = 900.0, log_path: Path | None = None):
    cmd = [sys.executable, "-m", "portablemc", *args]
    kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== {_now()} {cmd} ===\n")
            fh.flush()
            kwargs["stdout"] = fh
            kwargs["stderr"] = subprocess.STDOUT
            proc = subprocess.run(cmd, **kwargs)
            return proc.returncode, ""
    proc = subprocess.run(cmd, **kwargs)
    return proc.returncode, proc.stdout or ""


def ensure_runtime(inst: Instance, username: str = "Player") -> dict:
    """Install / verify the version + loader without launching (portablemc --dry)."""
    log = inst.logs_dir / "install.log"
    rc, output = _portablemc(
        [
            "start",
            "--main-dir", str(config.runtime_dir()),
            "--mc-dir", str(inst.dir),
            "--dry",
            "-u", username,
            inst.version_spec(),
        ],
        timeout=1800.0,
        log_path=log,
    )
    return {
        "instance": inst.name,
        "spec": inst.version_spec(),
        "exit_code": rc,
        "ok": rc == 0,
        "log": str(log),
        "output_tail": output[-4000:] if output else "",
    }


def launch(inst: Instance, username: str = "Player", extra_args: list[str] | None = None) -> dict:
    """Start the game detached; the process keeps writing to its launch log."""
    spec = inst.version_spec()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = inst.logs_dir / f"launch-{stamp}.log"
    cmd = [
        sys.executable, "-m", "portablemc",
        "start",
        "--main-dir", str(config.runtime_dir()),
        "--mc-dir", str(inst.dir),
        "-u", username,
        *(extra_args or []),
        spec,
    ]
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = log_path.open("a", encoding="utf-8")
    fh.write(f"\n=== {_now()} {cmd} ===\n")
    fh.flush()
    proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    inst.last_launch = {
        "pid": proc.pid,
        "log": str(log_path),
        "started": _now(),
        "spec": spec,
    }
    inst.save()
    return {**inst.last_launch, "instance": inst.name}


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    if psutil is not None:
        try:
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except Exception:
            return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True)
        return "java" in out.stdout.lower() or str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def status(inst: Instance) -> dict:
    pid = (inst.last_launch or {}).get("pid")
    alive = _alive(pid)
    java_pids = []
    if alive and psutil is not None:
        try:
            java_pids = [c.pid for c in psutil.Process(pid).children()
                         if "java" in c.name().lower()]
        except Exception:
            pass
    return {
        "instance": inst.name,
        "pid": pid,
        "running": alive,
        "java_pids": java_pids,
        "log": (inst.last_launch or {}).get("log"),
        "started": (inst.last_launch or {}).get("started"),
    }


def stop(inst: Instance, grace: float = 8.0) -> dict:
    pid = (inst.last_launch or {}).get("pid")
    if not pid or not _alive(pid):
        return {"instance": inst.name, "stopped": False, "reason": "没有在运行的进程"}
    if psutil is None:
        raise InstanceError("缺少 psutil，无法安全停止进程树")
    proc = psutil.Process(pid)
    children = proc.children(recursive=True)
    for child in children:
        try:
            child.terminate()
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass
    gone, alive = psutil.wait_procs([proc, *children], timeout=grace)
    for leftover in alive:
        try:
            leftover.kill()
        except Exception:
            pass
    return {
        "instance": inst.name,
        "stopped": not _alive(pid),
        "pid": pid,
        "terminated": len(gone),
        "killed": len(alive),
    }


def tail_log(inst: Instance, lines: int = 80, which: str = "latest") -> dict:
    logs = sorted(inst.logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return {"instance": inst.name, "log": None, "lines": []}
    if which == "install":
        target = inst.logs_dir / "install.log"
        if not target.exists():
            return {"instance": inst.name, "log": None, "lines": []}
    else:
        target = logs[0]
    text = target.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"instance": inst.name, "log": str(target), "lines": text[-max(1, lines):]}
