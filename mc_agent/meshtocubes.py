"""三角网格 → 立方体：GLB / OBJ 解析 → 体素化 → 贪心合并 → bbmodel。

外部服务的做法是 Per-mesh-part OBB 拟合；本模块用
经典的体素化 + greedy meshing：先把三角面撒进体素格，再把相邻同层格合并成盒子。
输出是 Blockbench 能直接打开的 cube 树，Java 版模型也能吃（全轴对齐）。

代价说清楚：曲面会变"台阶"，这是 Minecraft 的造型语言，不是精度损失。
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

from mc_craft_mcp import config
from . import state


class MeshError(RuntimeError):
    pass


# --------------------------------------------------------------- 读网格
def _mat_mul(a, b):
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def _mat_apply(m, p):
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


def _node_matrix(node: dict):
    if "matrix" in node:
        return [float(v) for v in node["matrix"]]
    t = node.get("translation") or [0, 0, 0]
    r = node.get("rotation") or [0, 0, 0, 1]  # x,y,z,w
    s = node.get("scale") or [1, 1, 1]
    x, y, z, w = [float(v) for v in r]
    rot = [
        1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
        2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
        2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0,
        0, 0, 0, 1,
    ]
    scale = [s[0], 0, 0, 0, 0, s[1], 0, 0, 0, 0, s[2], 0, 0, 0, 0, 1]
    trans = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1]
    return _mat_mul(trans, _mat_mul(rot, scale))


_CTYPE = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
          5125: ("I", 4), 5126: ("f", 4)}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read_accessor(gltf: dict, blob: bytes, index: int):
    acc = gltf["accessors"][index]
    bv = gltf["bufferViews"][acc["bufferView"]]
    fmt, size = _CTYPE[acc["componentType"]]
    ncomp = _NCOMP[acc["type"]]
    stride = bv.get("byteStride") or size * ncomp
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    count = acc["count"]
    out = []
    for i in range(count):
        off = base + i * stride
        vals = struct.unpack_from("<" + fmt * ncomp, blob, off)
        out.append(vals if ncomp > 1 else vals[0])
    return out


def read_glb(path: str) -> tuple[list, list]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise MeshError(f"文件不存在: {p}")
    raw = p.read_bytes()
    if raw[:4] != b"glTF":
        raise MeshError("不是 GLB")
    total = struct.unpack_from("<I", raw, 8)[0]
    off, gltf, blob = 12, None, b""
    while off < min(total, len(raw)):
        clen, ctype = struct.unpack_from("<I4s", raw, off)
        chunk = raw[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            text = chunk.decode("utf-8", "replace").strip("\x00 \t\r\n")
            gltf = json.JSONDecoder().raw_decode(text.lstrip("﻿"))[0]
        elif ctype.strip(b"\x00") == b"BIN":
            blob = chunk
        off += 8 + clen + ((4 - clen % 4) % 4)
    if not gltf:
        raise MeshError("GLB 里没有 JSON 块")

    verts: list[tuple] = []
    tris: list[tuple] = []

    def walk(node_index: int, parent):
        node = gltf["nodes"][node_index]
        world = _mat_mul(parent, _node_matrix(node))
        if "mesh" in node:
            mesh = gltf["meshes"][node["mesh"]]
            for prim in mesh.get("primitives") or []:
                attrs = prim.get("attributes") or {}
                if "POSITION" not in attrs:
                    continue
                pos = _read_accessor(gltf, blob, attrs["POSITION"])
                base = len(verts)
                verts.extend(_mat_apply(world, v) for v in pos)
                if "indices" in prim:
                    idx = _read_accessor(gltf, blob, prim["indices"])
                    for i in range(0, len(idx) - 2, 3):
                        tris.append((base + idx[i], base + idx[i + 1], base + idx[i + 2]))
                else:
                    for i in range(0, len(pos) - 2, 3):
                        tris.append((base + i, base + i + 1, base + i + 2))
        for child in node.get("children") or []:
            walk(child, world)

    scene = gltf.get("scenes") or [{"nodes": list(range(len(gltf.get("nodes") or [])))}]
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for root in scene[gltf.get("scene", 0)].get("nodes") or []:
        walk(root, identity)
    if not tris:
        raise MeshError("GLB 里没有可用的三角面")
    return verts, tris


def read_obj(path: str) -> tuple[list, list]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise MeshError(f"文件不存在: {p}")
    verts, tris = [], []
    for line in p.read_text("utf-8", errors="ignore").splitlines():
        if line.startswith("v "):
            _, x, y, z = line.split()[:4]
            verts.append((float(x), float(y), float(z)))
        elif line.startswith("f "):
            parts = line.split()[1:]
            idx = []
            for token in parts:
                i = int(token.split("/")[0])
                idx.append(i - 1 if i > 0 else len(verts) + i)
            for k in range(1, len(idx) - 1):
                tris.append((idx[0], idx[k], idx[k + 1]))
    if not tris:
        raise MeshError("OBJ 里没有可用的面")
    return verts, tris


# --------------------------------------------------------------- 体素化
def _aabb(verts, tris):
    lo = [1e18] * 3
    hi = [-1e18] * 3
    for i in {i for t in tris for i in t}:
        v = verts[i]
        for a in range(3):
            lo[a] = min(lo[a], v[a])
            hi[a] = max(hi[a], v[a])
    return lo, hi


def voxelize(verts, tris, resolution: int = 32, surface_only: bool = True,
             thickness: float = 0.75) -> dict:
    """把三角面撒进体素格。thickness 是命中半径（体素边长的倍数）。"""
    lo, hi = _aabb(verts, tris)
    size = [(hi[i] - lo[i]) or 1e-6 for i in range(3)]
    longest = max(size)
    vs = longest / max(4, int(resolution))
    nx = max(1, math.ceil(size[0] / vs))
    ny = max(1, math.ceil(size[1] / vs))
    nz = max(1, math.ceil(size[2] / vs))
    if nx * ny * nz > 4_000_000:
        raise MeshError(f"体素网格太大（{nx}x{ny}x{nz}），把 resolution 降到 16–48")

    hit = set()
    reach = vs * thickness
    reach2 = reach * reach

    for tri in tris:
        a, b, c = (verts[tri[0]], verts[tri[1]], verts[tri[2]])
        tlo = [min(a[i], b[i], c[i]) for i in range(3)]
        thi = [max(a[i], b[i], c[i]) for i in range(3)]
        i0 = [max(0, int((tlo[i] - lo[i] - reach) / vs)) for i in range(3)]
        i1 = [min([nx, ny, nz][i] - 1, int((thi[i] - lo[i] + reach) / vs)) for i in range(3)]
        if any(i1[i] < i0[i] for i in range(3)):
            continue
        # 三角形平面法线，用于点到面距离
        ab = [b[i] - a[i] for i in range(3)]
        ac = [c[i] - a[i] for i in range(3)]
        n = [ab[1] * ac[2] - ab[2] * ac[1],
             ab[2] * ac[0] - ab[0] * ac[2],
             ab[0] * ac[1] - ab[1] * ac[0]]
        nl = math.sqrt(sum(v * v for v in n)) or 1e-9
        n = [v / nl for v in n]
        for ix in range(i0[0], i1[0] + 1):
            for iy in range(i0[1], i1[1] + 1):
                for iz in range(i0[2], i1[2] + 1):
                    p = (lo[0] + (ix + 0.5) * vs,
                         lo[1] + (iy + 0.5) * vs,
                         lo[2] + (iz + 0.5) * vs)
                    if abs((p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1] + (p[2] - a[2]) * n[2]) > reach:
                        continue
                    # 重心坐标判定投影是否落在三角形内（放宽 0.15 兼容边缘）
                    ap = [p[i] - a[i] for i in range(3)]
                    d00 = sum(ab[i] * ab[i] for i in range(3))
                    d01 = sum(ab[i] * ac[i] for i in range(3))
                    d11 = sum(ac[i] * ac[i] for i in range(3))
                    d20 = sum(ap[i] * ab[i] for i in range(3))
                    d21 = sum(ap[i] * ac[i] for i in range(3))
                    den = d00 * d11 - d01 * d01
                    if abs(den) < 1e-12:
                        continue
                    u = (d11 * d20 - d01 * d21) / den
                    v = (d00 * d21 - d01 * d20) / den
                    if u < -0.15 or v < -0.15 or u + v > 1.15:
                        continue
                    # 平面距离已在上面卡过，重心坐标保证落在三角形内；
                    # 不要再拿"到顶点 a 的距离"过滤——大三角形会被整片丢掉。
                    hit.add((ix, iy, iz))

    if not surface_only:
        hit = _fill_solid(hit, nx, ny, nz)

    return {"voxels": hit, "vs": vs, "origin": lo, "dims": [nx, ny, nz], "grid": [[nx, ny, nz]]}


def _fill_solid(voxels, nx, ny, nz):
    """表面体素 → 实心（逐列扫描线填充）。"""
    filled = set()
    for ix in range(nx):
        for iy in range(ny):
            col = [iz for (x, y, iz) in voxels if x == ix and y == iy]
            if len(col) < 2:
                continue
            for iz in range(min(col), max(col) + 1):
                filled.add((ix, iy, iz))
    return filled or voxels


def greedy_boxes(voxels, dims) -> list[tuple]:
    """三维贪心：沿 x 扩 → 沿 z 扩 → 沿 y 扩，出一个尽量大的盒子。

    逐轴扩展比"逐 z 层做 2D 矩形"少一个量级的盒子数——顶面会合成一整块，
    而不是被切成 19×11 个小格。
    """
    remaining = set(voxels)
    boxes = []
    for seed in sorted(remaining):
        if seed not in remaining:
            continue
        x0, y0, z0 = seed
        x1 = x0
        while (x1 + 1, y0, z0) in remaining:
            x1 += 1
        z1 = z0
        while all((x, y0, z1 + 1) in remaining for x in range(x0, x1 + 1)):
            z1 += 1
        y1 = y0
        while all((x, y1 + 1, z) in remaining
                  for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)):
            y1 += 1
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    remaining.discard((x, y, z))
        boxes.append((x0, y0, z0, x1, y1, z1))
    return boxes


def to_bbmodel_spec(boxes, voxel: dict, target_pixels: float = 16.0,
                    name: str = "mesh") -> dict:
    """体素盒 → Blockbench cube spec（单位像素，最长边 = target_pixels）。"""
    lo, vs = voxel["origin"], voxel["vs"]
    nx, ny, nz = voxel["dims"]
    span = max(nx, ny, nz) * vs
    scale = target_pixels / span if span else 1.0

    def conv(v):
        return round(v * scale, 3)

    cubes = []
    for (x0, y0, z0, x1, y1, z1) in boxes:
        frm = [conv(lo[0] + x0 * vs - lo[0]), conv(lo[1] + y0 * vs - lo[1]), conv(lo[2] + z0 * vs - lo[2])]
        to = [conv(lo[0] + (x1 + 1) * vs - lo[0]), conv(lo[1] + (y1 + 1) * vs - lo[1]),
              conv(lo[2] + (z1 + 1) * vs - lo[2])]
        if any(t - f <= 0 for f, t in zip(frm, to)):
            continue
        cubes.append({"name": f"cube_{len(cubes)}", "from": frm, "to": to,
                      "origin": [0, 0, 0], "rotation": [0, 0, 0]})

    groups = [{"name": "mesh", "origin": [0, 0, 0], "cubes": cubes}]
    return {
        "name": name,
        "resolution": 16,
        "groups": groups,
        "_mcagent": {
            "source": "mesh_to_cubes",
            "voxel_size": round(vs, 4),
            "grid": [nx, ny, nz],
            "boxes": len(cubes),
            "scale_to_pixels": round(scale, 4),
        },
    }


def convert(path: str, resolution: int = 32, target_pixels: float = 16.0,
            solid: bool = False, name: str = "", out_path: str = "") -> dict:
    """一步到位：读 GLB/OBJ → 体素 → 盒子 → .bbmodel。"""
    suffix = Path(path).suffix.lower()
    if suffix == ".glb":
        verts, tris = read_glb(path)
    elif suffix == ".obj":
        verts, tris = read_obj(path)
    else:
        raise MeshError(f"只支持 .glb / .obj（收到 {suffix}）")

    vox = voxelize(verts, tris, resolution, surface_only=not solid)
    if not vox["voxels"]:
        raise MeshError("体素化结果为空：模型可能太小或 resolution 太低")

    boxes = greedy_boxes(vox["voxels"], vox["dims"])
    spec = to_bbmodel_spec(boxes, vox, target_pixels, name or Path(path).stem)

    from mc_craft_mcp.model import build_model
    model = build_model({k: v for k, v in spec.items() if not k.startswith("_")})
    model["_mcagent"] = spec["_mcagent"]

    out = Path(out_path).expanduser().resolve() if out_path else \
        config.exports_dir() / f"{(name or Path(path).stem)}_cubes.bbmodel"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({k: v for k, v in model.items() if not k.startswith("_")},
                              ensure_ascii=False, indent=2), "utf-8")

    from mc_craft_mcp.model import validate_model
    report = validate_model(str(out))
    rec = state.register_asset(str(out), model.get("name") or out.stem, "bbmodel",
                               meta={"source": str(Path(path).resolve()), "cubes": len(boxes)})
    return {
        "asset_id": rec["id"],
        "output": str(out),
        "triangles": len(tris),
        "voxels": len(vox["voxels"]),
        "boxes": len(boxes),
        "grid": vox["dims"],
        "voxel_size": round(vox["vs"], 4),
        "validation": report,
    }
