"""mc-craft MCP: shared Minecraft toolchain library behind mc-agent-mcp.

Layout:
    src/mc_craft_mcp/
        config.py       paths & env
        resolve.py      live version resolution (Fabric / Modrinth / NeoForge)
        instances.py    instance registry + portablemc launcher
        install.py      artifact installation into instances
        scaffold.py     mod project scaffolding (Fabric / NeoForge)
        build.py        gradle builds with JDK selection
        pack.py         resource pack + .mrpack packaging
        textures.py     deterministic pixel post-processing
        model.py        .bbmodel writer / validator
        server.py       MCP surface
"""

__version__ = "0.1.0"
