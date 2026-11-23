"""Project scaffolding for Minecraft Java mods (Fabric / NeoForge).

Templates are generated here, not copied from any third-party product. Version
numbers that matter (loader, Fabric API, Loom, NeoForge) are resolved live or
fail loudly; nothing is guessed silently.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config, resolve

MOD_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

PACK_FORMATS = {
    "1.20": 15, "1.20.1": 15, "1.20.2": 18, "1.20.3": 22, "1.20.4": 22,
    "1.20.5": 41, "1.20.6": 41,
    "1.21": 34, "1.21.1": 34, "1.21.2": 42, "1.21.3": 42, "1.21.4": 46,
    "1.21.5": 55, "1.21.6": 63, "1.21.7": 64, "1.21.8": 64,
}
PACK_FORMAT_DEFAULT = 34


class ScaffoldError(RuntimeError):
    pass


def java_version_for(mc_version: str) -> int:
    parts = [int(p) for p in re.findall(r"\d+", mc_version)[:2]] or [1, 20]
    major, minor = parts[0], parts[1]
    if major != 1:
        return 8
    if minor >= 20.5 or minor >= 21:
        return 21
    if minor >= 17:
        return 17
    if minor >= 16:
        return 11
    return 8


def pack_format_for(mc_version: str) -> int:
    if mc_version in PACK_FORMATS:
        return PACK_FORMATS[mc_version]
    prefix = ".".join(mc_version.split(".")[:2])
    return PACK_FORMATS.get(prefix, PACK_FORMAT_DEFAULT)


def _class_name(mod_id: str) -> str:
    return "".join(part.capitalize() for part in mod_id.split("_")) + "Mod"


def _write(root: Path, files: dict[str, str]) -> list[str]:
    written = []
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(rel)
    return written


def attach_wrapper(root: Path, gradle_version: str = "8.10") -> str | None:
    """Generate gradle wrapper files in a scratch project and copy them in.

    Gradle 9 cannot configure Fabric Loom, so the wrapper pins an 8.x
    distribution while the installed CLI only produces the four wrapper files.
    """
    gradle = shutil.which("gradle")
    if not gradle:
        return None

    local_zip = os.environ.get("MCC_GRADLE_ZIP", "").strip()
    if not local_zip:
        bundled = Path(__file__).resolve().parents[2] / "tools" / f"gradle-{gradle_version}-bin.zip"
        if bundled.exists():
            local_zip = str(bundled)

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "build.gradle").write_text("", encoding="utf-8")
        (Path(tmp) / "settings.gradle").write_text('rootProject.name = "wrapper-seed"\n',
                                                   encoding="utf-8")
        if local_zip and Path(local_zip).exists():
            url = "file:///" + Path(local_zip).resolve().as_posix()
            args = [gradle, "wrapper", "--gradle-distribution-url", url,
                    "--no-validate-url", "--no-daemon", "-q"]
        else:
            args = [gradle, "wrapper", "--gradle-version", gradle_version,
                    "--no-validate-url", "--no-daemon", "-q"]
        proc = subprocess.run(args, cwd=tmp, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return None
        for name in ("gradlew", "gradlew.bat"):
            src = Path(tmp) / name
            if src.exists():
                shutil.copy2(src, root / name)
        for rel in ("gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties"):
            src = Path(tmp) / rel
            if src.exists():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, root / rel)

        mirror = os.environ.get("MCC_GRADLE_MIRROR", "").strip().rstrip("/")
        props = root / "gradle" / "wrapper" / "gradle-wrapper.properties"
        if props.exists() and local_zip and Path(local_zip).exists():
            as_uri = Path(local_zip).resolve().as_posix()
            text = props.read_text(encoding="utf-8")
            text = re.sub(r"distributionUrl=.*", f"distributionUrl=file:///{as_uri}", text)
            props.write_text(text, encoding="utf-8")
        elif mirror and props.exists():
            text = props.read_text(encoding="utf-8")
            text = re.sub(r"distributionUrl=https\\:/+[^/]+/distributions/",
                          f"distributionUrl={mirror}/distributions/", text)
            props.write_text(text, encoding="utf-8")
    return gradle_version


def _fabric_files(mc: str, mod_id: str, name: str, pkg: str, java: int,
                  loader: str, fabric_api: str | None, loom: str, desc: str) -> dict[str, str]:
    cls = _class_name(mod_id)
    pkg_path = pkg.replace(".", "/")
    api_dep = f',\n    "fabric-api": "*"' if fabric_api else ""
    api_line = (f'    modImplementation "net.fabricmc.fabric-api:fabric-api:{fabric_api}"\n'
                if fabric_api else "")
    return {
        "settings.gradle": (
            "pluginManagement {\n"
            "    repositories {\n"
            "        maven { name = 'Fabric'; url = 'https://maven.fabricmc.net/' }\n"
            "        mavenCentral()\n"
            "        gradlePluginPortal()\n"
            "    }\n"
            "}\n\n"
            f'rootProject.name = "{mod_id}"\n'
        ),
        "build.gradle": (
            "plugins {\n"
            f"    id 'fabric-loom' version '{loom}'\n"
            "    id 'maven-publish'\n"
            "}\n\n"
            "version = project.mod_version\n"
            "group = project.maven_group\n\n"
            "base {\n"
            "    archivesName = project.archives_base_name\n"
            "}\n\n"
            "repositories {\n"
            "    mavenCentral()\n"
            "}\n\n"
            "dependencies {\n"
            '    minecraft "com.mojang:minecraft:${project.minecraft_version}"\n'
            "    mappings loom.officialMojangMappings()\n"
            '    modImplementation "net.fabricmc:fabric-loader:${project.loader_version}"\n'
            f"{api_line}"
            "}\n\n"
            "processResources {\n"
            '    inputs.property "version", project.version\n'
            '    filesMatching("fabric.mod.json") {\n'
            '        expand "version": project.version\n'
            "    }\n"
            "}\n\n"
            "tasks.withType(JavaCompile).configureEach {\n"
            "    it.options.release = %d\n"
            "}\n\n"
            "java {\n"
            "    withSourcesJar()\n"
            "    toolchain {\n"
            "        languageVersion = JavaLanguageVersion.of(%d)\n"
            "    }\n"
            "}\n" % (java, java)
        ),
        "gradle.properties": (
            "org.gradle.jvmargs=-Xmx2G\n"
            "org.gradle.parallel=true\n\n"
            f"minecraft_version={mc}\n"
            f"loader_version={loader}\n"
            f"fabric_version={fabric_api or ''}\n"
            "mod_version=1.0.0\n"
            f"maven_group={pkg.rsplit('.', 1)[0] if '.' in pkg else pkg}\n"
            f"archives_base_name={mod_id}\n"
        ),
        "src/main/resources/fabric.mod.json": (
            "{\n"
            '  "schemaVersion": 1,\n'
            f'  "id": "{mod_id}",\n'
            '  "version": "${version}",\n'
            f'  "name": {json.dumps(name, ensure_ascii=False)},\n'
            f'  "description": {json.dumps(desc, ensure_ascii=False)},\n'
            '  "authors": [],\n'
            '  "license": "MIT",\n'
            '  "environment": "*",\n'
            '  "entrypoints": {\n'
            f'    "main": ["{pkg}.{cls}"]\n'
            "  },\n"
            '  "depends": {\n'
            f'    "fabricloader": ">={loader}",\n'
            f'    "minecraft": "~{mc}",\n'
            f'    "java": ">={java}"{api_dep}\n'
            "  }\n"
            "}\n"
        ),
        f"src/main/java/{pkg_path}/{cls}.java": (
            f"package {pkg};\n\n"
            "import net.fabricmc.api.ModInitializer;\n"
            "import org.slf4j.Logger;\n"
            "import org.slf4j.LoggerFactory;\n\n"
            f"public class {cls} implements ModInitializer {{\n"
            f'    public static final String MOD_ID = "{mod_id}";\n'
            f'    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);\n\n'
            "    @Override\n"
            "    public void onInitialize() {\n"
            '        LOGGER.info("[{}] initialized", MOD_ID);\n'
            "    }\n"
            "}\n"
        ),
        "LICENSE": "MIT License\n\nCopyright (c) the project authors.\n",
        ".gitignore": "build/\n.gradle/\nrun/\n.idea/\n*.iml\n",
        "README.md": f"# {name}\n\nMinecraft {mc} · Fabric · generated by mc-craft.\n\n"
                     "```\n./gradlew build\n```\n\n产物在 `build/libs/`。\n",
        "run/.gitkeep": "",
    }


def _neoforge_files(mc: str, mod_id: str, name: str, pkg: str, java: int,
                    loader: str, desc: str) -> dict[str, str]:
    cls = _class_name(mod_id)
    pkg_path = pkg.replace(".", "/")
    return {
        "settings.gradle": (
            "pluginManagement {\n"
            "    repositories {\n"
            "        maven { name = 'NeoForged'; url = 'https://maven.neoforged.net/releases' }\n"
            "        mavenCentral()\n"
            "        gradlePluginPortal()\n"
            "    }\n"
            "}\n\n"
            f'rootProject.name = "{mod_id}"\n'
        ),
        "build.gradle": (
            "plugins {\n"
            "    id 'java'\n"
            "    id 'net.neoforged.moddev' version '2.0.+'\n"
            "}\n\n"
            "version = '1.0.0'\n"
            f"group = '{pkg}'\n\n"
            "neoForge {\n"
            f"    version = '{loader}'\n"
            "    runs {\n"
            "        client { client() }\n"
            "        server { server() }\n"
            "    }\n"
            "}\n\n"
            "java {\n"
            "    toolchain { languageVersion = JavaLanguageVersion.of(%d) }\n"
            "}\n" % java
        ),
        "gradle.properties": (
            "org.gradle.jvmargs=-Xmx3G\n"
            "org.gradle.parallel=true\n"
        ),
        "src/main/resources/META-INF/neoforge.mods.toml": (
            'modLoader = "javafml"\n'
            f'loaderVersion = "[{loader.split(".")[0]},)"\n'
            'license = "MIT"\n\n'
            "[[mods]]\n"
            f'modId = "{mod_id}"\n'
            'version = "1.0.0"\n'
            f'displayName = {json.dumps(name, ensure_ascii=False)}\n'
            f'description = {json.dumps(desc, ensure_ascii=False)}\n\n'
            "[[dependencies.%s]]\n"
            'modId = "neoforge"\n'
            'type = "required"\n'
            f'versionRange = "[{loader},)"\n'
            "ordering = \"NONE\"\n"
            "side = \"BOTH\"\n\n"
            "[[dependencies.%s]]\n"
            'modId = "minecraft"\n'
            'type = "required"\n'
            f'versionRange = "[{mc},)"\n'
            "ordering = \"NONE\"\n"
            "side = \"BOTH\"\n" % (mod_id, mod_id)
        ),
        "src/main/resources/pack.mcmeta": (
            "{\n"
            '  "pack": {\n'
            f'    "pack_format": {pack_format_for(mc)},\n'
            f'    "description": {json.dumps(name, ensure_ascii=False)}\n'
            "  }\n"
            "}\n"
        ),
        f"src/main/java/{pkg_path}/{cls}.java": (
            f"package {pkg};\n\n"
            "import net.neoforged.bus.api.IEventBus;\n"
            "import net.neoforged.fml.common.Mod;\n"
            "import org.slf4j.Logger;\n"
            "import org.slf4j.LoggerFactory;\n\n"
            f"@Mod({cls}.MOD_ID)\n"
            f"public class {cls} {{\n"
            f'    public static final String MOD_ID = "{mod_id}";\n'
            f'    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);\n\n'
            "    public %s(IEventBus modBus) {\n"
            '        LOGGER.info("[{}] initialized", MOD_ID);\n'
            "    }\n"
            "}\n" % cls
        ),
        "LICENSE": "MIT License\n\nCopyright (c) the project authors.\n",
        ".gitignore": "build/\n.gradle/\nrun/\n.idea/\n*.iml\n",
        "README.md": f"# {name}\n\nMinecraft {mc} · NeoForge · generated by mc-craft.\n\n"
                     "```\n./gradlew build\n```\n\n产物在 `build/libs/`。\n",
    }


def scaffold_mod(
    loader: str,
    mc_version: str,
    mod_id: str,
    dest: str = "",
    name: str = "",
    package: str = "",
    description: str = "",
    include_fabric_api: bool = True,
    with_wrapper: bool = True,
) -> dict:
    loader = loader.lower().strip()
    if not MOD_ID_RE.match(mod_id):
        raise ScaffoldError("mod_id 必须是全小写字母/数字/下划线，以字母开头，2-41 字符")
    if loader not in ("fabric", "neoforge"):
        raise ScaffoldError(f"暂只支持 fabric / neoforge（收到 {loader}）；"
                            "Forge 的 MDK 版本矩阵未做验证，不做猜测性 scaffold")

    root = Path(dest).expanduser().resolve() if dest else config.projects_dir() / f"{mod_id}-{loader}"
    if root.exists() and any(root.iterdir()):
        raise ScaffoldError(f"目标目录非空: {root}")

    pkg = package or f"com.example.{mod_id}"
    display = name or mod_id
    desc = description or f"{display} for Minecraft {mc_version}"
    java = java_version_for(mc_version)
    resolved = {}

    if loader == "fabric":
        loader_v = resolve.fabric_loader_version(mc_version)
        api_v = resolve.fabric_api_version(mc_version) if include_fabric_api else None
        loom = resolve.loom_version(mc_version)
        resolved = {"loader_version": loader_v, "fabric_api": api_v, "loom": loom,
                    "java": java}
        files = _fabric_files(mc_version, mod_id, display, pkg, java, loader_v, api_v,
                              loom, desc)
    else:
        loader_v = resolve.neoforge_version(mc_version)
        resolved = {"loader_version": loader_v, "java": java}
        files = _neoforge_files(mc_version, mod_id, display, pkg, java, loader_v, desc)

    root.mkdir(parents=True, exist_ok=True)
    written = _write(root, files)
    (root / ".mc-craft.json").write_text(json.dumps({
        "loader": loader, "mc_version": mc_version, "mod_id": mod_id,
        "package": pkg, "java": java, "resolved": resolved,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    wrapper = attach_wrapper(root) if with_wrapper else None
    return {
        "project_dir": str(root),
        "loader": loader,
        "mc_version": mc_version,
        "java": java,
        "resolved": resolved,
        "files": written,
        "gradle_wrapper": wrapper,
        "next": "在项目里执行 gradle_build(project_dir=...) 验证能编译",
    }
