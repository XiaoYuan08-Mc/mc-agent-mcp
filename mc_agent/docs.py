"""Minecraft API 离线知识库 + 检索。

`mc_api_docs` / `mc_api_search` 查的是仓库内置索引。这里给一份
手工维护的等价语料：符号、物理侧、适用版本、可粘贴片段。宁可少而准，不编版本号。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORPUS: list[dict] = [
    {
        "symbol": "Item", "side": "common", "since": "1.20",
        "tags": ["item", "registry", "物品"],
        "summary": "物品基类。构造时传入 Item.Settings。1.20.5+ 起组件（食物、附魔）改由 DataComponents 承载。",
        "snippet": "public static final Item RUBY = Registry.register(\n"
                   "        Registries.ITEM, Identifier.of(MOD_ID, \"ruby\"),\n"
                   "        new Item(new Item.Settings().maxCount(64)));",
    },
    {
        "symbol": "Item.Settings", "side": "common", "since": "1.20",
        "tags": ["item", "settings", "属性"],
        "summary": "物品属性链式配置：maxCount / rarity / fireproof / component。stack_size 上限 99。",
        "snippet": "new Item.Settings().maxCount(16).rarity(Rarity.RARE).fireproof()",
    },
    {
        "symbol": "DataComponents", "side": "common", "since": "1.20.5",
        "tags": ["component", "data", "组件", "食物"],
        "summary": "1.20.5 起物品数据走组件。食物用 DataComponents.FOOD；自定义组件用 DataComponentType.<T>builder() 注册后 attach。",
        "snippet": "new Item.Settings().component(DataComponents.FOOD,\n"
                   "        new FoodComponent.Builder().nutrition(4).saturationModifier(0.3f).build())",
    },
    {
        "symbol": "Registry.register", "side": "common", "since": "1.19",
        "tags": ["registry", "注册"],
        "summary": "Fabric 的注册入口。物品进 Registries.ITEM，方块进 Registries.BLOCK，两者要成对注册。",
        "snippet": "Registry.register(Registries.BLOCK, id, new Block(Block.Settings.create()));\n"
                   "Registry.register(Registries.ITEM, id, new BlockItem(block, new Item.Settings()));",
    },
    {
        "symbol": "Block", "side": "common", "since": "1.20",
        "tags": ["block", "方块"],
        "summary": "方块基类。1.20.5+ 的构造参数从 AbstractBlock.Settings 改为 Block.Settings。碰撞/硬度/掉落都在 Settings。",
        "snippet": "public static final Block RUBY_BLOCK = new Block(\n"
                   "        Block.Settings.create().strength(3.0f, 6.0f).requiresTool());",
    },
    {
        "symbol": "BlockEntity", "side": "common", "since": "1.20",
        "tags": ["block", "blockentity", "方块实体", "容器"],
        "summary": "带状态的方块。必须同时注册 BlockEntityType 并实现 toNbt/fromNbt（1.20.5+ 是 writeNbt/readNbt + NbtCompound）。",
        "snippet": "public class CrateEntity extends BlockEntity implements ImplementedInventory {\n"
                   "    private final DefaultedList<ItemStack> items = DefaultedList.ofSize(27, ItemStack.EMPTY);\n"
                   "    public CrateEntity(BlockPos pos, BlockState state) { super(TYPE, pos, state); }\n"
                   "}",
    },
    {
        "symbol": "FabricBlockEntityTypeBuilder", "side": "common", "since": "1.20",
        "tags": ["blockentity", "注册", "fabric"],
        "summary": "Fabric 的 BlockEntityType 构造器，避免手写 Builder.create 的泛型坑。",
        "snippet": "public static final BlockEntityType<CrateEntity> TYPE =\n"
                   "        FabricBlockEntityTypeBuilder.create(CrateEntity::new, CRATE).build();",
    },
    {
        "symbol": "ItemGroupEvents", "side": "common", "since": "1.20",
        "tags": ["itemgroup", "创造模式", "fabric"],
        "summary": "把物品塞进原版创造标签页，或注册自定义 ItemGroup。",
        "snippet": "ItemGroupEvents.modifyEntriesEvent(ItemGroups.INGREDIENTS)\n"
                   "        .register(entries -> entries.add(RUBY));",
    },
    {
        "symbol": "ServerTickEvents", "side": "server", "since": "1.20",
        "tags": ["event", "tick", "事件", "fabric"],
        "summary": "服务端 tick 回调，别在 END_SERVER_TICK 里做重活；世界级逻辑用 END_WORLD_TICK。",
        "snippet": "ServerTickEvents.END_SERVER_TICK.register(server -> {\n"
                   "    // 每 tick 一次\n"
                   "});",
    },
    {
        "symbol": "PlayerBlockBreakEvents", "side": "server", "since": "1.20",
        "tags": ["event", "block", "事件"],
        "summary": "方块破坏前后回调；AFTER 里拿得到 BlockEntity，适合做掉落/统计。",
        "snippet": "PlayerBlockBreakEvents.AFTER.register((world, player, pos, state, entity) -> {\n"
                   "    if (state.isOf(Blocks.STONE)) { /* ... */ }\n"
                   "});",
    },
    {
        "symbol": "PayloadTypeRegistry", "side": "common", "since": "1.20.5",
        "tags": ["network", "payload", "网络", "封包"],
        "summary": "1.20.5 起自定义封包改为 CustomPayload + PayloadTypeRegistry，不再用 PacketByteBuf 裸写通道。",
        "snippet": "public record C2SRequest(int id) implements CustomPayload {\n"
                   "    public static final CustomPayload.Id<C2SRequest> ID = new CustomPayload.Id<>(Identifier.of(MOD_ID, \"req\"));\n"
                   "    public static final PacketCodec<RegistryByteBuf, C2SRequest> CODEC =\n"
                   "            PacketCodec.tuple(PacketCodecs.VAR_INT, C2SRequest::id, C2SRequest::new);\n"
                   "    @Override public CustomPayload.Id<? extends CustomPayload> getId() { return ID; }\n"
                   "}",
    },
    {
        "symbol": "ServerPlayNetworking", "side": "server", "since": "1.20.5",
        "tags": ["network", "封包", "fabric"],
        "summary": "服务端收发。注册必须在 PayloadTypeRegistry.playC2S().register 之后，且在 common 初始化阶段完成。",
        "snippet": "PayloadTypeRegistry.playC2S().register(C2SRequest.ID, C2SRequest.CODEC);\n"
                   "ServerPlayNetworking.registerGlobalReceiver(C2SRequest.ID, (payload, ctx) -> {\n"
                   "    ctx.server().execute(() -> { /* 回主线程再碰世界状态 */ });\n"
                   "});",
    },
    {
        "symbol": "Screen", "side": "client", "since": "1.20",
        "tags": ["ui", "screen", "界面"],
        "summary": "客户端界面基类。init() 里加控件；render() 里画背景；关闭时不要留静态引用。",
        "snippet": "public class CrateScreen extends Screen {\n"
                   "    protected CrateScreen() { super(Text.literal(\"Crate\")); }\n"
                   "    @Override protected void init() {\n"
                   "        addDrawableChild(ButtonWidget.builder(Text.literal(\"OK\"), b -> close())\n"
                   "                .dimensions(width / 2 - 30, height / 2, 60, 20).build());\n"
                   "    }\n"
                   "}",
    },
    {
        "symbol": "HandledScreen", "side": "client", "since": "1.20",
        "tags": ["ui", "container", "容器", "槽位"],
        "summary": "带槽位的容器界面。必须同时有 ScreenHandler（服务端权威）与 HandledScreen（客户端绘制），槽位坐标两边要一致。",
        "snippet": "public class CrateScreen extends HandledScreen<CrateScreenHandler> {\n"
                   "    public CrateScreen(CrateScreenHandler handler, PlayerInventory inv, Text title) {\n"
                   "        super(handler, inv, title);\n"
                   "        this.backgroundWidth = 176;\n"
                   "        this.backgroundHeight = 166;\n"
                   "    }\n"
                   "}",
    },
    {
        "symbol": "ScreenHandler", "side": "common", "since": "1.20",
        "tags": ["ui", "container", "槽位", "同步"],
        "summary": "容器逻辑的唯一权威。addSlot 的顺序决定 quickMove 的区间划分；shift 点击要靠 transferSlot 自己写区间。",
        "snippet": "public class CrateScreenHandler extends ScreenHandler {\n"
                   "    public CrateScreenHandler(int syncId, PlayerInventory playerInv) {\n"
                   "        super(TYPE, syncId);\n"
                   "        for (int i = 0; i < 27; i++)\n"
                   "            addSlot(new Slot(inventory, i, 8 + (i % 9) * 18, 18 + (i / 9) * 18));\n"
                   "    }\n"
                   "}",
    },
    {
        "symbol": "SimpleInventory", "side": "common", "since": "1.20",
        "tags": ["inventory", "容器", "背包"],
        "summary": "轻量背包实现，配合 ScreenHandler 使用；要持久化就自己接 NBT 或在 BlockEntity 里持有。",
        "snippet": "SimpleInventory inv = new SimpleInventory(27);\n"
                   "inv.addListener(inventory -> markDirty());",
    },
    {
        "symbol": "EntityRenderer", "side": "client", "since": "1.20",
        "tags": ["render", "entity", "渲染", "实体"],
        "summary": "实体渲染器。1.20.5+ 的 render 签名带 RenderState；模型部件用 EntityModel + ModelPart。",
        "snippet": "public class RubyGolemRenderer extends MobEntityRenderer<RubyGolem, RubyGolemModel> {\n"
                   "    public RubyGolemRenderer(EntityRendererFactory.Context ctx) {\n"
                   "        super(ctx, new RubyGolemModel(ctx.getPart(RubyGolemModel.LAYER)), 0.5f);\n"
                   "    }\n"
                   "}",
    },
    {
        "symbol": "EntityModelLayer", "side": "client", "since": "1.20",
        "tags": ["render", "model", "模型层"],
        "summary": "1.20.5+ 用 EntityModelLayer 注册模型层，不再是 EntityModelLayerRegistry 的旧签名。",
        "snippet": "public static final ModelLayerLocation LAYER =\n"
                   "        new ModelLayerLocation(Identifier.of(MOD_ID, \"ruby_golem\"), \"main\");\n"
                   "EntityModelLayerRegistry.registerModelLayer(LAYER, RubyGolemModel::getTexturedModelData);",
    },
    {
        "symbol": "blockstates", "side": "common", "since": "1.13",
        "tags": ["resourcepack", "资源包", "模型", "方块"],
        "summary": "assets/<ns>/blockstates/<block>.json 把方块状态映射到模型；variants 的键必须覆盖全部属性组合。",
        "snippet": "{\n  \"variants\": {\n    \"facing=north\": { \"model\": \"mymod:block/ruby_block\" },\n    \"facing=south\": { \"model\": \"mymod:block/ruby_block\", \"y\": 180 }\n  }\n}",
    },
    {
        "symbol": "item model", "side": "common", "since": "1.21.4",
        "tags": ["resourcepack", "模型", "物品", "版本差异"],
        "summary": "1.21.4 起物品模型改用 assets/<ns>/items/<item>.json（ItemModelDefinition），旧的 models/item 仍作 fallback。跨版本时先确认目标版本再生成。",
        "snippet": "{\n  \"model\": {\n    \"type\": \"minecraft:model\",\n    \"model\": \"mymod:item/ruby\"\n  }\n}",
    },
    {
        "symbol": "pack.mcmeta", "side": "common", "since": "1.13",
        "tags": ["resourcepack", "资源包", "pack_format"],
        "summary": "资源包描述文件。pack_format 与版本强绑定（1.21.4=46，1.21.5=55，需按目标版本核对），写错会直接不加载。",
        "snippet": "{\n  \"pack\": { \"pack_format\": 46, \"description\": \"My Pack\" }\n}",
    },
    {
        "symbol": "fabric.mod.json", "side": "common", "since": "1.20",
        "tags": ["fabric", "元数据", "入口"],
        "summary": "Fabric 模组元数据。entrypoints.main 的类实现 ModInitializer；client 的类实现 ClientModInitializer，二者不要混。",
        "snippet": "{\n  \"schemaVersion\": 1,\n  \"id\": \"mymod\",\n  \"version\": \"1.0.0\",\n  \"entrypoints\": { \"main\": [\"com.example.mymod.MyMod\"] },\n  \"depends\": { \"fabricloader\": \">=0.15.0\", \"minecraft\": \"~1.21.1\" }\n}",
    },
    {
        "symbol": "neoforge.mods.toml", "side": "common", "since": "1.20.5",
        "tags": ["neoforge", "元数据"],
        "summary": "NeoForge 元数据文件名是 META-INF/neoforge.mods.toml（Forge 是 mods.toml）。modLoader 填 javafml。",
        "snippet": "modLoader=\"javafml\"\nloaderVersion=\"[4,)\"\nlicense=\"MIT\"\n[[mods]]\nmodId=\"mymod\"\nversion=\"1.0.0\"",
    },
    {
        "symbol": "DeferredRegister.Items", "side": "common", "since": "1.20.5",
        "tags": ["neoforge", "registry", "注册"],
        "summary": "NeoForge 的延迟注册。registerSimpleItem 是最短路径；要在主类构造器里把 register 挂到 mod event bus。",
        "snippet": "public static final DeferredRegister.Items ITEMS = DeferredRegister.createItems(MOD_ID);\n"
                   "public static final DeferredItem<Item> RUBY = ITEMS.registerSimpleItem(\"ruby\", new Item.Properties());",
    },
    {
        "symbol": "@SubscribeEvent", "side": "common", "since": "1.20",
        "tags": ["neoforge", "event", "事件"],
        "summary": "NeoForge 事件用注解订阅，方法必须是 public 且只收一个事件参数；实例事件要注册监听器对象。",
        "snippet": "@SubscribeEvent\npublic void onServerTick(ServerTickEvent.Post event) {\n    // ...\n}",
    },
    {
        "symbol": "mixin", "side": "common", "since": "1.16",
        "tags": ["mixin", "注入", "hook"],
        "summary": "改原版行为的标准手段。mymod.mixins.json 里声明 package 与 mixins；@Inject 用 at = @At(\"HEAD\")，改返回值用 @ModifyReturnValue。",
        "snippet": "@Mixin(PlayerEntity.class)\npublic abstract class PlayerMixin {\n"
                   "    @Inject(method = \"tick\", at = @At(\"HEAD\"))\n"
                   "    private void mymod$tick(CallbackInfo ci) { }\n"
                   "}",
    },
    {
        "symbol": "GeckoLib GeoItem", "side": "common", "since": "1.20",
        "tags": ["geckolib", "animation", "动画", "物品"],
        "summary": "GeckoLib 4 的物品动画入口：实现 GeoItem，提供 AnimatableInstanceCache，模型/动画放 assets/<ns>/geo 与 animations。",
        "snippet": "public class RubySword extends Item implements GeoItem {\n"
                   "    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);\n"
                   "    public void registerControllers(AnimatableManager.ControllerRegistrar c) {\n"
                   "        c.add(new AnimationController<>(this, \"controller\", 0, state -> PlayState.CONTINUE));\n"
                   "    }\n"
                   "}",
    },
    {
        "symbol": "geo model json", "side": "common", "since": "1.20",
        "tags": ["geckolib", "geo", "模型", "bedrock"],
        "summary": "GeckoLib 直接吃 Bedrock 几何格式：format_version 1.12.0，minecraft:geometry 里是 bones + cubes + uv。",
        "snippet": "{\n  \"format_version\": \"1.12.0\",\n  \"minecraft:geometry\": [{\n    \"description\": { \"identifier\": \"geometry.ruby\", \"texture_width\": 16, \"texture_height\": 16 },\n    \"bones\": [{ \"name\": \"body\", \"pivot\": [0, 0, 0], \"cubes\": [] }]\n  }]\n}",
    },
    {
        "symbol": "bedrock manifest.json", "side": "common", "since": "1.20",
        "tags": ["bedrock", "基岩", "manifest", "addon"],
        "summary": "基岩附加包入口。header/modules 的 uuid 必须唯一，version 三段数字，min_engine_version 影响可用组件。",
        "snippet": "{\n  \"format_version\": 2,\n  \"header\": { \"name\": \"My Addon\", \"uuid\": \"<uuid>\", \"version\": [1,0,0], \"min_engine_version\": [1,20,0] },\n  \"modules\": [{ \"type\": \"data\", \"uuid\": \"<uuid2>\", \"version\": [1,0,0] }]\n}",
    },
    {
        "symbol": "bedrock entity json", "side": "common", "since": "1.20",
        "tags": ["bedrock", "entity", "实体", "行为包"],
        "summary": "行为包 entities/*.json 定义组件组；资源包 entity/*.entity.json 绑定几何、贴图、动画与刷怪蛋。",
        "snippet": "{\n  \"format_version\": \"1.20.0\",\n  \"minecraft:entity\": {\n    \"description\": { \"identifier\": \"mymod:ruby_golem\", \"is_spawnable\": true, \"is_summonable\": true },\n    \"components\": { \"minecraft:health\": { \"value\": 40 } }\n  }\n}",
    },
    {
        "symbol": "JSON-UI", "side": "client", "since": "1.20",
        "tags": ["bedrock", "ui", "json-ui"],
        "summary": "基岩 UI 用 ui/<name>.json + namespace。控件树里 size/offset 是数组，绑定数据走 bindings。",
        "snippet": "{\n  \"namespace\": \"mymod_ui\",\n  \"panel\": {\n    \"main\": { \"type\": \"panel\", \"size\": [320, 180], \"controls\": [] }\n  }\n}",
    },
    {
        "symbol": "LootTable", "side": "server", "since": "1.20",
        "tags": ["loot", "掉落", "数据包"],
        "summary": "掉落表在 data/<ns>/loot_table/blocks/<block>.json（1.21 起路径从 loot_tables 改为 loot_table）。方块要指到这张表才有掉落。",
        "snippet": "Block.Settings.create().dropsLike(Blocks.STONE)",
    },
    {
        "symbol": "TagKey", "side": "common", "since": "1.20",
        "tags": ["tag", "标签", "数据包"],
        "summary": "标签在 data/<ns>/tags/block|item/<name>.json。工具等级靠 mineable/* 标签决定，别在代码里硬判。",
        "snippet": "{\n  \"replace\": false,\n  \"values\": [\"mymod:ruby_block\"]\n}",
    },
    {
        "symbol": "Recipe", "side": "server", "since": "1.20",
        "tags": ["recipe", "合成", "数据包"],
        "summary": "1.21 起合成表字段改为 type + category + key + result（result 只写 id，count 移到 count 字段）。放 data/<ns>/recipe/。",
        "snippet": "{\n  \"type\": \"minecraft:crafting_shaped\",\n  \"category\": \"misc\",\n  \"pattern\": [\"RRR\", \"R R\", \"RRR\"],\n  \"key\": { \"R\": \"mymod:ruby\" },\n  \"result\": { \"id\": \"mymod:ruby_block\", \"count\": 1 }\n}",
    },
    {
        "symbol": "gradle loom", "side": "common", "since": "1.20",
        "tags": ["gradle", "构建", "loom"],
        "summary": "Fabric 用 fabric-loom 插件；Gradle 9 不被 Loom 支持，wrapper 固定 8.10。Java 版本：1.20.x→17，1.20.5+/1.21.x→21。",
        "snippet": "plugins { id 'fabric-loom' version '1.7-SNAPSHOT' }\njava { toolchain { languageVersion = JavaLanguageVersion.of(21) } }",
    },
    {
        "symbol": "portablemc", "side": "common", "since": "1.20",
        "tags": ["runtime", "启动", "实例"],
        "summary": "离线启动实例：portablemc start <version> --main-dir <dir> --username <name>。fabric 版本写成 fabric:<mc>。",
        "snippet": "portablemc start fabric:1.21.1 --main-dir .\\runtime --username Player",
    },
]


class DocsError(RuntimeError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def docs(topic: str = "", symbols: list | None = None, project_dir: str = "") -> dict:
    picked = []
    if symbols:
        want = [_norm(s) for s in symbols]
        for row in CORPUS:
            if any(w and (w in _norm(row["symbol"]) or w in _norm(row["summary"])) for w in want):
                picked.append(row)
    if topic:
        t = _norm(topic)
        for row in CORPUS:
            if row in picked:
                continue
            hay = _norm(row["symbol"] + row["summary"] + " ".join(row["tags"]))
            if t and t in hay:
                picked.append(row)
    if not picked and not topic and not symbols:
        picked = CORPUS[:6]

    project_hint = {}
    root = Path(project_dir).expanduser().resolve() if project_dir else None
    if root and root.exists():
        project_hint = {
            "root": str(root),
            "has_fabric_json": (root / "src/main/resources/fabric.mod.json").exists(),
            "has_neoforge_toml": (root / "src/main/resources/META-INF/neoforge.mods.toml").exists(),
            "java_files": len(list(root.rglob("*.java"))) if root.exists() else 0,
        }

    return {
        "topic": topic,
        "matched": len(picked),
        "entries": picked,
        "project": project_hint,
        "note": "语料是手工维护的离线索引，标注了 since 版本；与目标版本不符时以官方文档为准",
    }


def search(query: str, physical_side: str = "both", symbols: list | None = None,
           max_results: int = 8) -> dict:
    if not query and not symbols:
        raise DocsError("query 与 symbols 至少给一个")
    terms = [t for t in re.split(r"\s+", (query or "").strip()) if t]
    scored = []
    for row in CORPUS:
        if physical_side in ("client", "server") and row["side"] not in (physical_side, "common"):
            continue
        hay = _norm(row["symbol"] + row["summary"] + " ".join(row["tags"]) + row["snippet"])
        score = 0
        for term in terms:
            n = _norm(term)
            if not n:
                continue
            if n in _norm(row["symbol"]):
                score += 5
            if n in hay:
                score += 2
        if symbols:
            for s in symbols:
                if _norm(s) and _norm(s) in _norm(row["symbol"]):
                    score += 6
        if score:
            scored.append((score, row))
    scored.sort(key=lambda t: -t[0])
    picked = [dict(r, score=s) for s, r in scored[:max(1, min(20, int(max_results)))]]
    return {
        "query": query,
        "physical_side": physical_side,
        "hits": len(picked),
        "results": picked,
        "corpus_size": len(CORPUS),
    }
