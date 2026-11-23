"""Java 物品注册：源码 + 模型 + 语言文件一次落盘。

生成的是编译得过的骨架：Fabric 走 `Registry.register`，NeoForge 走 `DeferredRegister`。
贴图从当前 3D 资产的渲染图或已有 icon 拷进 `assets/<ns>/textures/item/`。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mc_craft_mcp import config
from . import assets, state

RARITIES = ("common", "uncommon", "rare", "epic")


class JavaItemError(RuntimeError):
    pass


def _class_name(raw: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", raw)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Item"


def _detect_loader(root: Path) -> str:
    if (root / "src" / "main" / "resources" / "fabric.mod.json").exists():
        return "fabric"
    if (root / "src" / "main" / "resources" / "META-INF" / "neoforge.mods.toml").exists():
        return "neoforge"
    if (root / "build.gradle").exists():
        text = (root / "build.gradle").read_text("utf-8", errors="ignore")
        if "net.neoforged" in text:
            return "neoforge"
        return "fabric"
    return "fabric"


def _detect_package(root: Path, mod_id: str) -> str:
    for base in (root / "src" / "main" / "java",):
        if not base.exists():
            continue
        for p in base.rglob("*.java"):
            text = p.read_text("utf-8", errors="ignore")
            m = re.search(r"^package\s+([\w.]+);", text, re.M)
            if m:
                return m.group(1)
    return f"com.example.{mod_id}"


def register_items(
    dest_path: str = "",
    namespace: str = "",
    asset_id: str = "",
    items: list | None = None,
    action: str = "write",
    dry_run: bool = False,
) -> dict:
    if not items:
        raise JavaItemError("items 为空：每个物品至少要有 id")
    root = Path(dest_path).expanduser().resolve() if dest_path else config.projects_dir()
    loader = _detect_loader(root)
    if not namespace and loader == "fabric":
        try:
            meta = json.loads((root / "src/main/resources/fabric.mod.json").read_text("utf-8"))
            namespace = meta.get("id") or ""
        except Exception:
            namespace = ""
    namespace = namespace or "mcagent"
    pkg = _detect_package(root, namespace)
    cls = _class_name(namespace) + "Items"

    src_dir = root / "src" / "main" / "java" / Path(*pkg.split("."))
    res_dir = root / "src" / "main" / "resources" / "assets" / namespace
    tex_dir = res_dir / "textures" / "item"
    model_dir = res_dir / "models" / "item"
    lang_dir = res_dir / "lang"

    # 贴图来源：当前资产渲染图
    tex_src = None
    rec = state.get_asset(asset_id) if asset_id else state.current_asset()
    if rec:
        try:
            tmp = config.exports_dir() / f"{rec['id']}_itemtex.png"
            assets.render_model(assets.read_model(rec["path"]), str(tmp), size=64, margin=8)
            tex_src = tmp
        except Exception:
            tex_src = None

    written = []
    for it in items:
        item_id = (it.get("id") or "").strip()
        if not item_id or not re.fullmatch(r"[a-z0-9_]+", item_id):
            raise JavaItemError(f"物品 id 不合法: {item_id!r}（小写字母/数字/下划线）")
        stack = int(it.get("stack_size", 64))
        if not 1 <= stack <= 99:
            raise JavaItemError(f"{item_id}: stack_size 必须在 1..99")

        model = {"parent": "minecraft:item/generated",
                 "textures": {"layer0": f"{namespace}:item/{item_id}"}}
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / f"{item_id}.json").write_text(json.dumps(model, indent=2), "utf-8")
        written.append(str(model_dir / f"{item_id}.json"))

        tex_dir.mkdir(parents=True, exist_ok=True)
        if tex_src and tex_src.exists():
            import shutil
            shutil.copyfile(tex_src, tex_dir / f"{item_id}.png")
            written.append(str(tex_dir / f"{item_id}.png"))

        for lang, label in (("en_us", it.get("name_en") or it.get("name") or item_id),
                            ("zh_cn", it.get("name") or item_id)):
            lang_dir.mkdir(parents=True, exist_ok=True)
            lp = lang_dir / f"{lang}.json"
            data = json.loads(lp.read_text("utf-8")) if lp.exists() else {}
            data[f"item.{namespace}.{item_id}"] = label
            lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            written.append(str(lp))

    if loader == "fabric":
        code = _fabric_source(pkg, namespace, cls, items)
    else:
        code = _neoforge_source(pkg, namespace, cls, items)
    src_dir.mkdir(parents=True, exist_ok=True)
    src_file = src_dir / f"{cls}.java"

    if action == "preview" or dry_run:
        return {
            "loader": loader,
            "package": pkg,
            "namespace": namespace,
            "class": cls,
            "source_preview": code,
            "files_planned": written,
            "dry_run": True,
        }

    src_file.write_text(code, "utf-8")
    return {
        "loader": loader,
        "package": pkg,
        "namespace": namespace,
        "class": cls,
        "source": str(src_file),
        "files": written + [str(src_file)],
        "items": [i.get("id") for i in items],
    }


def _fabric_source(pkg: str, ns: str, cls: str, items: list) -> str:
    rows = []
    for it in items:
        item_id = it["id"]
        stack = int(it.get("stack_size", 64))
        const = item_id.upper()
        settings = f"new Item.Settings().maxCount({stack})"
        rows.append(
            f'    public static final Item {const} = register("{item_id}", {settings});'
        )
    body = "\n".join(rows)
    return f"""package {pkg};

import net.minecraft.item.Item;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

/** 由 mc-agent 生成的物品注册表。手改后请自行维护。 */
public final class {cls} {{

{body}

    private static Item register(String id, Item.Settings settings) {{
        return Registry.register(Registries.ITEM, Identifier.of("{ns}", id), new Item(settings));
    }}

    public static void init() {{
        // 静态字段在类加载时完成注册；显式调用一次保证顺序。
    }}

    private {cls}() {{
    }}
}}
"""


def _neoforge_source(pkg: str, ns: str, cls: str, items: list) -> str:
    rows = []
    for it in items:
        item_id = it["id"]
        stack = int(it.get("stack_size", 64))
        const = item_id.upper()
        rows.append(
            f'    public static final DeferredItem<Item> {const} = ITEMS.registerSimpleItem(\n'
            f'            "{item_id}", new Item.Properties().stacksTo({stack}));'
        )
    body = "\n\n".join(rows)
    return f"""package {pkg};

import net.minecraft.world.item.Item;
import net.neoforged.neoforge.registries.DeferredItem;
import net.neoforged.neoforge.registries.DeferredRegister;

/** 由 mc-agent 生成的物品注册表。记得在主类构造器里 ITEMS.register(modBus)。 */
public final class {cls} {{

    public static final DeferredRegister.Items ITEMS = DeferredRegister.createItems("{ns}");

{body}

    private {cls}() {{
    }}
}}
"""
