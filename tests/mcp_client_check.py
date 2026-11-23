"""通过真实 MCP 协议连 server：list_tools + 调两个工具，验证「agent 能调」。

运行：在仓库根执行 python tests/mcp_client_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)

from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402


async def main():
    env = {
        "PYTHONPATH": str(ROOT),
        "MCC_HOME": str(Path(tempfile.gettempdir()) / "mc-agent-test"),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PATH": os.environ.get("PATH", ""),
    }
    transport = StdioTransport(
        command=str(PY),
        args=["-m", "mc_agent.server"],
        env=env,
        cwd=str(ROOT),
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        print(f"server 工具数: {len(tools)}")
        names = sorted(t.name for t in tools)
        print("列表:", ", ".join(names[:12]), "...")

        r1 = await client.call_tool("mc_api_search", {"query": "blockentity", "physical_side": "common"})
        data = r1.data if hasattr(r1, "data") else r1
        print("mc_api_search ->", json.dumps(data, ensure_ascii=False)[:180])

        r2 = await client.call_tool("design_model_concepts", {"prompt": "石头小怪", "kind": "model"})
        d2 = r2.data if hasattr(r2, "data") else r2
        print("design_model_concepts ->", len(d2.get("concepts", [])), "concepts")

        r3 = await client.call_tool("web_search", {"query": "fabric api"})
        d3 = r3.data if hasattr(r3, "data") else r3
        print("web_search ->", d3.get("error"), "|", (d3.get("alternatives") or [""])[0][:60])

    print("MCP 客户端链路 OK")


if __name__ == "__main__":
    asyncio.run(main())
