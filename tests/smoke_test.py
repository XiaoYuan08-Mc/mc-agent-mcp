"""Smoke test for mc-craft MCP.

    python tests/smoke_test.py           # fast, offline-ish checks
    python tests/smoke_test.py --full    # also scaffolds + really builds a Fabric mod
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MCC_HOME", str(Path(tempfile.gettempdir()) / "mc-agent-test"))

from fastmcp import Client  # noqa: E402
from PIL import Image  # noqa: E402

from mc_craft_mcp.server import mcp  # noqa: E402


def make_source_image(path: Path, size: int = 128) -> None:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            if (x // 16 + y // 16) % 2 == 0:
                px[x, y] = (180, 90, 40, 255)
            else:
                px[x, y] = (120, 60, 20, 255)
            if 40 < x < 90 and 40 < y < 60:
                px[x, y] = (255, 210, 120, 255)
    img.save(path)


async def run(full: bool) -> int:
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="mcc-smoke-"))
    src = tmp / "lamp.png"
    make_source_image(src)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools)
        print(f"tools ({len(names)}): {', '.join(names)}")

        async def call(tool_name: str, /, **args):
            res = await client.call_tool(tool_name, args)
            data = res.data if getattr(res, "data", None) is not None else res.content
            return data

        # 1. instance registry
        try:
            import uuid
            inst_name = "smoke-" + uuid.uuid4().hex[:6]
            r = await call("mc_instance", action="create", name=inst_name, mc_version="1.21.1",
                           loader="vanilla")
            print("create:", json.dumps(r, ensure_ascii=False)[:160])
            assert Path(r["created"]["dir"]).is_dir()
            r2 = await call("mc_instance", action="list")
            assert any(i["name"] == inst_name for i in r2["instances"])
            r3 = await call("mc_instance", action="inspect", name=inst_name)
            assert r3["status"]["running"] is False
            print("instance: ok")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"instance: {exc}")

        # 2. textures
        try:
            bt = await call("block_texture", source=str(src), size=16, colors=8)
            print("block_texture:", json.dumps(bt["seam"], ensure_ascii=False), bt["colors_used"], "colors")
            assert Path(bt["output"]).exists()
            em = await call("emissive_mask", base=bt["output"], threshold=150)
            assert Path(em["mask"]).exists() and Path(em["lit"]).exists()
            print("emissive:", em["emissive_pixels"], "px")
            pr = await call("palette_report", path=bt["output"])
            print("palette:", pr["distinct_colors"], "colors")
            ic = await call("item_icon", source=str(src), size=32)
            assert Path(ic["output"]).exists()
            print("item_icon: ok")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"textures: {exc}")

        # 3. model
        try:
            spec = {
                "name": "smoke_crate",
                "resolution": 16,
                "groups": [
                    {"name": "body", "cubes": [
                        {"name": "base", "from": [0, 0, 0], "to": [16, 16, 16]},
                        {"name": "lid", "from": [0, 16, 0], "to": [16, 18, 16],
                         "origin": [8, 16, 8], "rotation": [0, -10, 0]},
                    ]},
                ],
            }
            r = await call("bbmodel_write", spec=spec, output=str(tmp / "crate.bbmodel"))
            print("bbmodel:", r["cubes"], "cubes,", r["groups"], "groups")
            v = await call("bbmodel_validate", path=r["output"])
            assert v["ok"], v["issues"]
        except Exception as exc:  # noqa: BLE001
            failures.append(f"model: {exc}")

        # 4. resource pack
        try:
            pack_dir = tmp / "rp"
            (pack_dir / "assets" / "minecraft" / "textures" / "block").mkdir(parents=True)
            (pack_dir / "pack.mcmeta").write_text(
                json.dumps({"pack": {"pack_format": 34, "description": "smoke"}}), encoding="utf-8")
            (pack_dir / "assets" / "minecraft" / "textures" / "block" / "lamp.png").write_bytes(
                src.read_bytes())
            rp = await call("resourcepack_build", pack_dir=str(pack_dir))
            assert Path(rp["output"]).exists()
            print("resourcepack:", rp["files"], "files")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"resourcepack: {exc}")

        # 5. mrpack write (no downloads)
        try:
            mp = await call("modpack_build", name="smoke-pack", mc_version="1.21.1", mods=[])
            assert Path(mp["output"]).exists()
            print("mrpack: ok")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"mrpack: {exc}")

        if full:
            # 6. scaffold + real build
            try:
                sc = await call("scaffold_mod", loader="fabric", mc_version="1.21.1",
                                mod_id="smoke_mod", name="Smoke Mod",
                                dest=str(tmp / "smoke_mod"))
                print("scaffold:", sc["resolved"], "wrapper:", sc["gradle_wrapper"])
                b = await call("gradle_build", project_dir=sc["project_dir"], timeout=1800)
                print("build exit:", b["exit_code"], "artifacts:", b["artifacts"])
                if not b["ok"]:
                    failures.append(f"gradle_build failed: {b['output_tail'][-600:]}")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"scaffold/build: {exc}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nALL CHECKS PASSED")
    print("tmp:", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run("--full" in sys.argv)))
