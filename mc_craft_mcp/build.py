"""Gradle builds with explicit JDK selection (no silent wrong-JDK builds)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config
from .scaffold import java_version_for


class BuildError(RuntimeError):
    pass


def _major_of(java_exe: Path) -> int | None:
    try:
        out = subprocess.run([str(java_exe), "-version"], capture_output=True, text=True,
                             timeout=30).stderr
        m = re.search(r'version "(\d+)', out) or re.search(r'version "1\.(\d+)', out)
        if m:
            return int(m.group(1))
    except Exception:
        return None


def pick_java(mc_version: str) -> tuple[Path | None, int]:
    want = java_version_for(mc_version)
    best: tuple[Path | None, int] = (None, 0)
    for base in config.java_home_candidates():
        exe = base / "bin" / "java.exe"
        if not exe.exists():
            continue
        major = _major_of(exe) or 0
        if major == want:
            return base, major
        if major > want and (best[0] is None or major < best[1]):
            best = (base, major)
    if best[0] is not None:
        return best
    which = shutil.which("java")
    if which:
        return Path(which).parent.parent, _major_of(Path(which)) or 0
    return None, 0


def gradle_build(project_dir: str, task: str = "build", timeout: int = 900,
                 extra_args: str = "") -> dict:
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        raise BuildError(f"项目目录不存在: {root}")
    meta_path = root / ".mc-craft.json"
    if not meta_path.exists():
        raise BuildError("不是 mc-craft scaffold 出来的项目（缺少 .mc-craft.json）")
    import json
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    java_home, java_major = pick_java(meta.get("mc_version", "1.21.1"))
    if java_home is None:
        raise BuildError("没有找到可用 JDK，请设置 MCC_JAVA_HOME")
    want = java_version_for(meta.get("mc_version", "1.21.1"))
    if java_major < want:
        raise BuildError(f"JDK 版本过低：需要 {want}，找到 {java_major}（{java_home}）")

    if os.name == "nt" and (root / "gradlew.bat").exists():
        cmd = [str(root / "gradlew.bat")]
    elif (root / "gradlew").exists():
        cmd = ["sh", str(root / "gradlew")]
    else:
        gradle = shutil.which("gradle")
        if not gradle:
            raise BuildError("既没有 gradlew 也没有全局 gradle")
        cmd = [gradle]

    cmd += [task, "--no-daemon", "--console=plain"] + ([extra_args] if extra_args else [])

    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")

    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout,
                          env=env, shell=False)
    logs = root / "build" / "mc-craft-build.log"
    logs.parent.mkdir(parents=True, exist_ok=True)
    logs.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")

    artifacts = []
    libs = root / "build" / "libs"
    if libs.exists():
        artifacts = [str(p) for p in sorted(libs.glob("*.jar"))]

    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-40:]
    blob = (proc.stdout or "") + (proc.stderr or "")
    hint = ""
    if proc.returncode != 0 and ("insufficient memory" in blob.lower()
                                 or "outofmemoryerror" in blob.lower()):
        hint = ("构建 JVM 内存不足：NeoForge 26.x 首次构建会用 -Xmx4096m 反编译 Minecraft，"
                "需要至少 6~8GB 可用提交内存。可调大系统虚拟内存/页面文件，"
                "或设置 MCC_JAVA_HOME 指向 64 位 JDK 25 后重试。")
    return {
        "project_dir": str(root),
        "task": task,
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "java_home": str(java_home),
        "java_major": java_major,
        "artifacts": artifacts,
        "log": str(logs),
        "output_tail": "\n".join(tail),
        "hint": hint,
    }
