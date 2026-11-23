# -*- coding: utf-8 -*-
"""从运行中的 MCP server 生成 docs/tools.md（工具清单，以 server 实际注册为准）。"""
import asyncio
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


def esc(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def first_sentence(text: str) -> str:
    text = (text or "").strip()
    for sep in ("。", "\n", "；"):
        if sep in text:
            text = text.split(sep)[0]
    return esc(text)


async def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env.pop("MCC_TRANSPORT", None)
    transport = StdioTransport(command=str(os.environ["PY"]), args=["-m", "mc_agent.server"],
                              env=env, cwd=str(ROOT))
    async with Client(transport) as client:
        tools = sorted(await client.list_tools(), key=lambda t: t.name)

    lines = ["# 工具清单", "",
             f"本文件由 `scripts/gen_tools_doc.py` 从运行中的 server 自动生成，共 **{len(tools)} 个工具**。",
             "",
             "## 总览", "",
             "| 工具 | 说明 | 必填参数 |", "| --- | --- | --- |"]
    for t in tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
        req = schema.get("required") or []
        lines.append(f"| `{t.name}` | {first_sentence(t.description)} | {', '.join(req) or '—'} |")

    lines += ["", "## 逐个工具", ""]
    for t in tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
        props = schema.get("properties") or {}
        reqset = set(schema.get("required") or [])
        lines += [f"### `{t.name}`", "", (t.description or "").strip() or "（无说明）", "", "| 参数 | 类型 | 必填 | 默认 | 说明 |",
                  "| --- | --- | --- | --- | --- |"]
        for pname, pspec in props.items():
            ptype = pspec.get("type") or pspec.get("anyOf") and " / ".join(
                x.get("type", "?") for x in pspec.get("anyOf", [])) or "—"
            default = pspec.get("default", "")
            lines.append(f"| `{pname}` | {esc(str(ptype))} | {'是' if pname in reqset else '否'} | {esc(str(default)) or '—'} | {esc(pspec.get('description','')) or '—'} |")
        lines.append("")

    out = ROOT / "docs" / "tools.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", "utf-8")
    print("wrote", out, len(tools), "tools")


if __name__ == "__main__":
    os.environ["PY"] = os.environ.get("PY", "python")
    asyncio.run(main())
