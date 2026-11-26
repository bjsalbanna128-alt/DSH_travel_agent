# 内容层与检索合流：景点/酒店内容、向量化与可售性标注

任务开始日期 2026-11-26。

## 一、原因与目标

现状：agent 的景点与酒店知识全部来自两处**静态种子**——`scripts/seed_knowledge.py` 里写死的 30 个景点（成都/北京/三亚各 10），`backend/scripts/seed_hotels.py` 导入的 72 家酒店。这些数据和我们的「商品目录」没有任何关系：检索到的酒店景点，绝大多数**我们并不卖**。

目标：建立**内容层**（景点/酒店的介绍、评分、标签、坐标等），让 agent 检索的是内容层；内容层条目可以绑定商品（票种/房型），从而在检索结果上直接标出「这个能不能卖、卖多少钱」。

最终达到：

- 运营录入一条内容 → 向量化 → agent 就能推荐它。
- 内容条目绑定了在售商品 → 检索结果标「可代订」；没绑定或已售罄 → 标「参考 · 不可预订」。
- 种子字典退役，数据迁进内容层，由运营长期维护。

## 二、范围和边界

### 本次交付

1. 两张表：`place_contents`（内容层）与 `place_content_products`（内容 ↔ 商品绑定）。
2. 内容 → 向量文档生成与同步服务，配套脚本（全量重建 + 增量更新）。
3. 种子数据导入：本期只导入**北京**（10 个景点 + 18 家酒店）到内容层；其他城市的种子不进内容层。
4. **北京试点库存**：用北京种子数据生成供应商、商品、逐日报价与库存，并绑定内容，使北京成为第一个「检索到的就是能卖的」城市。
5. 检索改造：内容层向量 + 高德两源合并，新增**可售性标注**与**排序规则**；旧种子集合不再被读取。
6. 规划节点改造：景点与酒店的检索结果带 `offer`，`Attraction`/`Hotel` 结构扩展。
7. B 端「内容管理」页面：景点与酒店内容的增删改、发布、绑定商品。
8. 检索链路一次性切换：北京走「内容层 + 高德」，其他城市只走高德；不保留灰度开关。

### 不在本次范围

- C 端的标记展示、两道确认与加购（见「C端售卖与加购」规格）。
- 订单与支付（已有订单规格，C 端入口属下一份规格）。
- 内容的多语言、富文本、图片相册（首版纯文本 + 单图 URL 字段预留）。
- 内容与高德 POI 的自动匹配（首版由运营手工填写坐标，或用后台的 POI 搜索选择器）。
- 内容层向量的实时同步（首版用脚本触发）。

### 依赖

- 库存口径（总投放 / 预占 / 确认占用与占用明细）来自「2026-11-26-履约模块前置修改」第 2 节。本规格只做**读取**：展示「剩余 = 总投放 − 预占 − 确认占用」并据此标注可售，不写占用、不建占用明细。因此前置规格必须先落地。

### 可能受影响的现有行为

- 景点/酒店检索结果多出 `sellable`、`price_cny`、`remaining` 等字段，规划提示词与编译产物需要兼容（新增字段可选，缺省不影响旧流程）。
- 规划结果中的景点/酒店可能带 `product_id`，行程详情页可据此展示「可代订」。
- ChromaDB 新增两个集合，旧集合保留不删（回滚用）。

## 三、数据模型

### 3.1 `place_contents` — 内容层

一张表存景点与酒店，用 `kind` 区分；公共字段共用，类型专属字段可空。

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `id` | String(36) PK | |
| `kind` | String(16) 非空，`ck_pc_kind`：`attraction` / `hotel` | 内容类型 |
| `city` | String(100) 非空，索引 | 所在城市 |
| `name` | String(160) 非空 | 名称，同 city 内唯一（`uq_pc_city_name`） |
| `category` | String(32) 默认 `""` | 景点分类：natural / cultural / entertainment / shopping；酒店留空 |
| `rating` | Float 可空，0–5 | 评分 |
| `visit_duration_hours` | Float 可空，>0 | 景点建议游玩时长 |
| `opening_hours` | String(64) 默认 `""` | 开放时间文本，如 `08:00-17:00`、`全天` |
| `ticket_price_hint_cny` | Float 可空，≥0 | 参考票价（非售价），用于「参考价」展示 |
| `star_rating` | Integer 可空，1–5 | 酒店星级 |
| `landmark_hint` | String(160) 默认 `""` | 酒店位置提示，如「近春熙路」 |
| `lat` / `lng` | Float 可空 | 坐标；用于距离排序与地图 |
| `tags` | JSON 默认 `[]` | 标签，如 `["拍照","美食"]` |
| `suitable_for` | JSON 默认 `[]` | 适合人群，如 `["家庭","情侣"]` |
| `description` | Text 默认 `""` | 介绍正文（纯文本） |
| `highlights` | JSON 默认 `[]` | 亮点短句列表 |
| `cover_image_url` | String(500) 默认 `""` | 封面（预留） |
| `source` | String(16) 非空，默认 `manual` | `manual` / `seed` / `amap`，用于追溯 |
| `status` | String(16) 非空，默认 `draft` | `draft` / `published` / `unpublished` |
| `created_by` / `updated_by` | String(36) 可空 | |
| `created_at` / `updated_at` | DateTime 非空 | |

索引：`ix_pc_kind_city_status(kind, city, status)`、`ix_pc_name(name)`。

**为什么内容与商品分开**：免费景点（宽窄巷子、锦里、春熙路）永远没有门票商品，但它们是行程合理性的必需品。若强绑商品，规划将只会推荐能卖票的地方，用户会觉得 AI 在推销。

### 3.2 `place_content_products` — 内容 ↔ 商品绑定

| 字段 | 类型与约束 | 含义 |
|---|---|---|
| `content_id` | FK `place_contents.id` ON DELETE CASCADE | 内容 |
| `product_id` | FK `products.id` ON DELETE CASCADE | 商品（票种/房型/车型） |
| 主键 | `(content_id, product_id)` | 多对多 |

约束：一条内容可绑多个商品（成人票/儿童票/联票，或多种房型），一个商品只应属于一条内容（应用层校验，冲突时提示但不阻止，允许同一商品被多家内容引用以应对极端情况）。

索引：`ix_pcp_content(content_id)`、`ix_pcp_product(product_id)`。

### 3.3 与商品表的关系

不改 `products` 表结构。内容层通过关联表指向商品；商品侧仍由「资源管理」维护（供应商、报价、上架状态）。

**可售性判断**（对某内容、某服务日期）：

```
剩余 = 总投放 - 预占 - 确认占用          （口径见《履约模块前置修改》第 2 节）

存在至少一个绑定商品 p 满足：
  p.status = 'on_shelf'
  且 p.supplier.status = 'active'
  且 price_offers(p, date).status = 'available'
  且 库存数已核实（该报价已设置总投放）
  且 剩余 >= 1
```

未设置总投放的旧报价视为「库存未核实」，**不计为可售**（与前置规格一致：未设库存只供查看，游客不能下单）。

满足则 `sellable = true`，展示价取满足条件商品中 `sale_fen` 的最小值，并返回该 `product_id` 与剩余数量（多个商品时剩余取所选商品的剩余）。

## 四、向量化与同步

### 4.1 文档生成

复用现有 `chroma_store` 的写入接口，新增内容层文档生成函数 `content_to_document(content: dict) -> tuple[str, dict]`，返回（文本，metadata）。

景点文档模板：

```
{name}是{city}的{category}类景点。{description}
评分{rating}/5，建议游玩{visit_duration_hours}小时，开放时间{opening_hours}。
适合：{suitable_for 逗号连接}。标签：{tags 逗号连接}。
亮点：{highlights 逗号连接}。
```

酒店文档模板：

```
{name}是{city}的{star_rating}星级酒店，{landmark_hint}。{description}
评分{rating}/5。适合：{suitable_for}。标签：{tags}。亮点：{highlights}。
```

metadata（用于过滤与展示，**不写入可售性**）：

```
content_id, kind, city, name, category, rating, visit_duration, tier_price_hint,
lat, lng, opening_hours, tags(json), suitable_for(json), star_rating
```

### 4.2 集合与开关

新增两个集合：`contents_attractions`、`contents_hotels`。旧的 `attractions`、`hotels` 保留数据但**不再被检索读取**。

**不设灰度开关**：检索链路一次性切换到新链路。

| 城市 | 检索来源 |
|---|---|
| 北京（内容层有数据） | 内容层向量 + 高德实时，两者合并去重 |
| 其他城市（内容层为空） | **只走高德实时** |

实现上不判断城市名，而是「按城市查内容层集合」：查到就用，查不到就只用高德。城市名不进配置，将来给成都录了内容，成都自动变成「内容层 + 高德」，无需改配置或发版。

旧集合与 `scripts/seed_knowledge.py` 的字典保留在仓库里作为数据备份与回滚依据，代码不再引用它们；确认新链路稳定后再在后续迭代中清理。

### 4.3 同步服务

新增 `app/services/content_vectors.py`：

```python
async def sync_contents(sessions, *, kinds=("attraction", "hotel"), rebuild=False) -> dict
```

行为：

1. `rebuild=True`：删除两个内容集合并重建；否则增量。
2. 读取 `status == 'published'` 的内容行（草稿与下架不进向量库）。
3. 逐条生成文档与 metadata，按 `content_id` 幂等 upsert（先 `delete(ids=[...])` 再 `add`）。
4. 计算应存在 ID 集合与库内 ID 集合的差集，删除多余项（内容被删/下架）。
5. 返回 `{"added": n, "updated": n, "removed": n}`。

脚本 `backend/scripts/sync_content_vectors.py`：

```
python -m scripts.sync_content_vectors --rebuild
python -m scripts.sync_content_vectors            # 增量
```

### 4.4 触发时机

- **发布与下架自动同步**：`publish` / `unpublish` 接口在写入状态后直接调用同步服务，运营无需再点一次「同步向量」；同步失败不回滚发布，记录告警，运营仍可手动重试。
- 后台保留「同步向量（增量）」「重建向量」两个按钮，用于批量补录与排障。
- 第二期改为事件驱动（内容保存后异步触发），本期不做。

## 五、种子导入与北京试点库存

一次性完成两件事：把种子数据搬进内容层，并把**北京**这批种子同时做成真实可售的库存（供应商 → 商品 → 逐日报价与库存 → 内容绑定）。北京由此成为第一个「agent 检索的就是我们能卖的」的城市。

### 5.1 内容导入（本期只导北京）

脚本 `backend/scripts/import_seed_contents.py`：

- 景点：`import scripts.seed_knowledge` 读取 `CITY_ATTRACTIONS`，**只取北京**（`--cities 北京`，默认值即北京），逐条写入 `place_contents`（`kind='attraction'`、`source='seed'`、`status='published'`）。字段映射：`duration → visit_duration_hours`、`ticket → ticket_price_hint_cny`、`hours → opening_hours`、`suitable → suitable_for`。
- 酒店：读取 `backend/scripts/seed_hotels.py` 的 `BEIJING_HOTELS`（18 家），写入 `kind='hotel'`。字段映射：`area → landmark_hint`、`price_per_night_cny → ticket_price_hint_cny`（作为参考价）、`amenities → tags`、`location.lat/lng → lat/lng`。
- 其他城市（成都/北京以外的三亚等）的种子**本期不导入内容层**：它们没有库存，导入后只会产生一堆「参考价不可预订」的条目，反而拉低规划可信度。等这些城市补了库存再导入。
- 幂等：按 `(city, name)` 已存在则跳过（不覆盖运营手工改过的内容）。
- 输出统计：新增 / 跳过 条数。

### 5.2 北京试点库存（本期重点）

脚本 `backend/scripts/seed_beijing_inventory.py`，把北京这批种子变成**可卖的商品**。数据规模（来自现有种子）：

| 数据 | 数量 | 价格来源 |
|---|---|---|
| 北京酒店 | 18 家（260–4500 元/晚） | `price_per_night_cny` 作为售价 |
| 北京景点 | 10 个（收费 6 个：60/40/30/15/50/10 元；免费 4 个：南锣鼓巷、798、王府井大街、什刹海） | 种子 `ticket` 作为售价 |

**创建内容**：

1. 两个供应商：
   - 「北京酒店试点供应商」（`kind='hotel'`，启用）
   - 「北京票务试点供应商」（`kind='ticket'`，启用）
2. 商品：
   - 18 个酒店房型商品（`hotel_room`），属性 `room_name="标准大床房"`、`occupancy=2`、`breakfast="不含早"`，名称取酒店名 + 房型。
   - 6 个门票商品（`attraction_ticket`），属性 `ticket_name="成人票"`、`audience="成人"`。**4 个免费景点不建商品**，只保留内容 —— 它们用于验证「免费 · 无需预订」这条展示规则。
   - 所有商品绑定 POI：`source='seed'`、`source_id=f"bj-{kind}-{序号}"`、`name=地点名`、`city='北京'`。
3. 逐日报价与库存（覆盖未来 90 天，从执行日次日起）：
   - 酒店：`sale_fen = 售价 × 100`，`cost_fen = sale_fen × 0.7`，总投放 = 5（每晚每房型 5 间），预占 = 0，确认占用 = 0。
   - 门票：`sale_fen = 票价 × 100`，`cost_fen = sale_fen × 0.6`，总投放 = 200（每日 200 张），预占 = 0，确认占用 = 0。
   - `status='available'`。写入口径与《履约模块前置修改》第 2 节一致（总投放已设置即可售，占用由订单流程维护）。
4. 内容绑定：把 18 条北京酒店内容与 6 条收费景点内容分别绑定到对应商品（`place_content_products`）；4 条免费景点不绑定。
5. 幂等：按 `(supplier 名, 商品名)` 与 `(city, name)` 判断，已存在则跳过；报价按 `(product_id, service_date)` 已存在则跳过。重复执行不产生重复数据，也不重置已售数量。
6. 输出统计：创建供应商 / 商品 / 报价条数，跳过条数。

**为什么用种子数据当库存**：这些地点有坐标、有介绍、有价格量级，能立刻把「检索 → 展示 → 加购 → 下单」整条链跑通，而不必等运营手工录入 28 条数据。价格是示例值，运营后续按真实采购价在资源管理里调整。

### 5.3 执行顺序

```
1. import_seed_contents.py            北京 28 条内容进内容层
2. seed_beijing_inventory.py          北京生成库存（供应商/商品/报价/绑定）
3. sync_content_vectors.py --rebuild  向量库指向内容层
```

前三步可重复执行；第 3 步可随时重建。完成后再让 agent 检索，北京就会优先返回我们的可售商品，其他城市自动只用高德。

## 六、检索改造

### 6.1 两源合并

改造 `app/services/poi_service.py`：

```python
def _content_available() -> bool:
    """内容层集合里是否有可检索的数据（任意城市）。"""
    store = get_chroma_store()
    return store.collection_count("contents_attractions") > 0

async def search_attractions_hybrid(
    city, preferences=None, days=3, chroma_only=False,
    *, travel_date: date | None = None, anchor: tuple[float, float] | None = None,
    session=None,
) -> list[dict]
```

1. **内容层**：`store.search_contents("contents_attractions", query, city=city, k=limit)`。查不到该城市的数据就是空列表，不报错。
2. **高德**：不变，`_search_amap_items(...)`。**旧种子集合不再调用。**

合并：内容层结果在前、高德结果在后，`_merge_and_dedup` 按 `(poi_source, poi_id)` 或名称相似度去重，内容层优先保留。

| 城市 | 结果 |
|---|---|
| 北京 | 28 条库存内容 + 高德实时，合并去重 |
| 成都 / 上海 / 三亚等 | 内容层返回空 → 只用高德（结果全部 `sellable=false`） |

### 6.2 可售性标注

新增 `app/services/sellability.py`：

```python
async def annotate_offers(
    session, items: list[dict], *, kind: str, travel_date: date | None,
) -> list[dict]
```

对每个条目：

1. 取 `content_id`；没有 `content_id` 的条目（纯高德/旧种子）→ `sellable=false`，`offer=null`。
2. 批量查询该批 `content_id` 的绑定商品（一次 SQL，避免 N+1）：
   `select ... from place_content_products join products join suppliers left join price_offers on ... where content_id in (...) and service_date = :date`。
3. 计算 `sellable`、`price_cny`（最小售价）、`remaining`、`product_id`。
4. 写回 `item["offer"] = {"product_id":..., "price_cny":..., "remaining":..., "sellable":...}`；无可用商品时 `offer = null`。

`travel_date` 为空（未确定出行日期）时：只判断「是否有在售商品」，不判断当日库存，`remaining=None`，并在返回里标注 `date_unspecified=true`。

### 6.3 排序

在 `_rerank` 之后做一次**稳定排序**（保留语义顺序作为最后的比较项）：

```python
def _sort_candidates(items, *, anchor=None):
    def key(item):
        sellable = 1 if (item.get("offer") or {}).get("sellable") else 0
        distance = haversine_km(anchor, item["location"]) if anchor and item.get("location") else 0.0
        return (-sellable, round(distance, 2))
    return sorted(items, key=key)   # sorted 稳定，等价分数保持原有语义顺序
```

- 第一关键字：可售优先。
- 第二关键字：距 `anchor` 的距离（酒店传「当日第一个景点坐标」；景点传空，按语义顺序）。
- 语义分不再参与排序（已由上游 rerank 决定相对顺序，稳定排序保留它）。

### 6.4 阈值与兜底

- 内容层结果少于 `limit` 时，用高德补足。
- 内容层检索异常（Chroma 不可用）→ 记 warning，**只用高德**，不阻塞规划。
- 城市无内容层数据（非北京）→ 只用高德，结果全部 `sellable=false`（符合“没货就明示”）。
- 内容层返回的条目若 `city` 与请求城市不一致（向量库脏数据）→ 丢弃，避免串城。

## 七、规划节点改造

### 7.1 数据结构

`app/schemas/travel_state.py` 新增：

```python
class Offer(BaseModel):
    product_id: str
    price_cny: float
    remaining: int | None = None
    sellable: bool = False
    date_unspecified: bool = False
```

`Attraction` 与 `Hotel` 各增加：

```python
offer: Offer | None = None
```

保留原有字段（`ticket_price_cny`、`price_per_night_cny`）作为**参考价**，`offer.price_cny` 才是我们卖的价格。

### 7.2 `attraction_node`

- 读取 `state["travel_request"]` 的日期（若有 `travel_time` 可解析起始日；否则 `travel_date=None`）。
- 调用 `search_attractions_hybrid(..., travel_date=..., session=...)`。
- 对结果调用 `annotate_offers`，再把 `offer` 写进 LLM 提示（提示词增加一段：「以下 POI 中 `sellable=true` 的是平台可代订项，优先推荐」）。
- 输出 `Attraction` 时带上 `offer`。

### 7.3 `hotel_node`

- `anchor` 取当前行程中**第一个景点的坐标**（从 `state["day_plans"]` 或 `state["selected_attractions"]` 中取；为空则不排序）。
- 调用 `search_hotels_hybrid(..., anchor=..., travel_date=...)`，标注与排序同上。
- 提示词同步增加「优先推荐可代订且离景点近的酒店」。

### 7.4 编译器

`compiler.py` 在生成 `day_plans` 时把 `offer` 原样带入；`Itinerary` 顶层增加 `sellable_summary`（可选）：

```python
{"attractions": n_sellable, "hotels": n_sellable, "total": n_sellable}
```

供 C 端确认页快速判断「本次是否有可代订项」。

## 八、B 端内容管理

页面 `/admin/contents`（一个页面，`kind` 切换）：

1. **列表**：城市、名称、类型、状态、评分、是否已绑定商品（「可售 / 未绑定」）、更新时间；按城市/状态/关键词筛选。
2. **编辑抽屉/页面**：全部内容字段；坐标支持手工填写或从 POI 搜索选择器带入（复用现有商品 POI 选择器）；标签与适合人群为多选/逗号分隔。
3. **绑定商品**：弹窗内搜索商品（按名称/类型），多选后保存；已绑定商品显示上架状态与最近报价，便于运营判断。
4. **发布 / 下架**：发布前校验必填（城市、名称、介绍、坐标），否则 422 并指出缺项。
5. **同步向量**：按钮触发 `/admin/contents/sync-vectors`，返回增删改统计。

接口：

```
GET    /api/v1/admin/contents?kind=&city=&status=&keyword=&page=
POST   /api/v1/admin/contents
GET    /api/v1/admin/contents/{id}
PATCH  /api/v1/admin/contents/{id}
POST   /api/v1/admin/contents/{id}/publish
POST   /api/v1/admin/contents/{id}/unpublish
PUT    /api/v1/admin/contents/{id}/products      { product_ids: [...] }
POST   /api/v1/admin/contents/sync-vectors       { rebuild?: bool }
DELETE /api/v1/admin/contents/{id}               有绑定时 409
```

全部受 `require_operator` 保护。

## 九、迁移与回滚

- 新表由 `create_all` 建立；不改动任何现有表（`products`、`price_offers` 不动）。
- 内容层数据由导入脚本填充，不自动生成，避免凭空造数据。
- 检索链路直接切换，不留配置开关；上线前必须在本地完成验收（尤其是北京与非北京两类城市）。
- **回滚方式**：旧集合与 `scripts/seed_knowledge.py` 的数据保留在仓库与 Chroma 中，回滚只需把 `poi_service` 的两处调用改回旧函数（一次代码回退），不需要数据迁移。
- 切换后若某城市内容层数据为空，检索自动只用高德，不会出现空白结果。

## 十、验收

1. 执行导入脚本后，`place_contents` 中只有北京 28 条（10 景点 + 18 酒店，`source='seed'`）；重复执行不重复插入。
2. 执行北京试点脚本后：2 个供应商、24 个商品（18 酒店 + 6 门票）、覆盖未来 90 天的报价；4 个免费景点只有内容、没有商品；重复执行不重复创建、不重置已售数量。
3. 北京 28 条内容中，18 条酒店与 6 条收费景点已绑定商品，4 条免费景点未绑定。
4. 发布一条新景点内容并同步向量，`contents_attractions` 集合中能检索到该条。
5. 内容改为草稿或下架后同步，向量库中对应条目被删除。
6. 检索北京时：命中的酒店/景点带 `offer.sellable=true`、`price_cny` 等于我们录的售价、`remaining` 等于投放数量。
7. 检索北京时若把某商品的当日报价改为 `status='stopped'` 或售罄，该内容 `offer.sellable=false`。
8. 北京 4 个免费景点返回 `offer=null` 且参考价为 0，对应「免费 · 无需预订」。
9. **检索成都/上海等非北京城市：只返回高德结果，全部 `sellable=false`，不出现内容层条目**（旧种子集合不再被读取；断言结果中无 `source='seed'` 或 `content_id` 的条目）。
10. 排序：北京候选中可售项排在不可售项之前；同为可售时，酒店按距锚点景点更近优先。
11. 内容层集合被清空后，北京检索自动只用高德，规划仍能产出结果，不报错。
12. 规划产出的 `Itinerary` 中，可售条目带 `offer`，不可售为 `null`；`sellable_summary` 计数正确。
13. 后台内容页可完成：新建 → 绑定商品 → 发布 → 同步向量 → 检索可见 的完整闭环。
14. 删除仍有绑定商品的内容 → 409；先解绑可删。
15. 给成都录一条内容并同步向量后，成都检索立即变成「内容层 + 高德」，无需改代码或配置。

## 十一、测试与回归计划

- 新增 `backend/tests/test_contents.py`：内容 CRUD 与校验、发布状态与向量可见性、绑定商品、删除保护、导入幂等（用临时库与临时 Chroma 目录）。
- 新增 `backend/tests/test_sellability.py`：可售性四种组合（在架/下架、有报价/无报价、有库存/售罄、供应商停用）、`date_unspecified`、批量查询无 N+1（可用查询计数断言）。
- 新增 `backend/tests/test_poi_sorting.py`：可售优先、距离次之、稳定排序保留语义顺序、无锚点时不排序。
- 前端 `npm run build`；手工走查内容管理页与发布/同步。
- 回归：规划全链路（澄清 → 景点 → 酒店 → 编译 → 确认）在开关关闭与打开两种状态下都要跑通。

## 十二、分期

### 第一期（本规格）

内容层表、北京种子导入与库存生成、向量同步、两源检索（内容层 + 高德）与可售性标注、排序、规划节点接入、B 端内容管理页。

### 第二期

- 内容发布后自动触发向量同步（事件驱动，去掉手工按钮）。
- 内容与高德 POI 的自动匹配（按名称+坐标）、批量导入 Excel。
- 内容质量校验（缺坐标、缺介绍的提示清单）。
- 退役 `scripts/seed_knowledge.py` 的字典（数据已在库中）。

### 第三期

- 多语言与富文本、内容图片相册。
- 内容与推荐内容打通（首页卡片引用内容条目）。

## 十三、已确认决策

1. 内容层独立成表，不塞进商品表。
2. 内容与商品多对多：一条内容可绑多个票种/房型。
3. 向量库只存已发布内容；可售性实时 join，不写入向量库。
4. 排序规则：可售优先 > 距离 > 语义序。
5. 种子数据导入内容层后保留，字典本身在第二期退役。
6. **北京一期试点**：用北京种子数据直接生成可售库存（18 酒店 + 6 门票），4 个免费景点只做内容不做商品。
7. **链路一次性切换**：内容层 + 高德两源；北京有内容层，其他城市只走高德；不设灰度开关，回滚靠代码回退。
7. 试点价格与成本为示例值（成本分别按售价 70% / 60% 计），运营后续按真实采购价调整。

## 十四、待定项

1. 出行日期未确定时（`travel_time` 只有模糊描述），可售性只判断「有在售商品」，不判断当日库存——是否需要提示用户先选日期。
2. 同一内容绑定多个商品时，展示价取最低还是取「符合预算的」：当前取最低。
3. 酒店内容与房型商品的比例关系（一家酒店多个房型）在 C 端如何展示：当前按内容卡片展示最低价，进入加购才选房型。
4. 内容坐标由运营手工填写还是必须从 POI 选择器带入：当前两者都允许。

## 十五、验证记录

已实现（第一期，未含第二期的自动同步与种子字典退役）。

### 涉及文件

| 层 | 文件 |
|---|---|
| 模型 | `app/db/content_models.py`（`place_contents`、`place_content_products`）、`database.py` 注册 |
| 契约 | `app/schemas/contents.py` |
| 服务 | `app/services/contents.py`（CRUD、发布、绑定、文档生成、向量同步、可售查询）、`app/services/sellability.py`（标注与排序） |
| 向量 | `app/services/chroma_store.py`（`contents_attractions`、`contents_hotels` 集合与读写） |
| 检索 | `app/services/poi_service.py`（内容层 + 高德两源，旧种子集合不再读取） |
| 规划 | `app/graph/nodes/agents.py`（传 `travel_date` 与会话、酒店锚点）、`app/schemas/travel_state.py`（`Offer` 与 `content_id`）、`app/services/planning_quality.py`（content 身份与 offer 透传） |
| 接口 | `app/api/contents.py`、`app/api/admin.py` |
| 脚本 | `scripts/import_seed_contents.py`、`scripts/seed_beijing_inventory.py`、`scripts/sync_content_vectors.py` |
| 前端 | `api/contents.ts`、`types/contents.ts`、`views/AdminContentsPage.vue`、路由与导航 |
| 测试 | `tests/test_contents.py` |

### 已执行

- 端到端脚本（临时库 + 临时 Chroma 目录）15 项全部通过：内容 10 景点 + 18 酒店、供应商 2、商品 24、报价 2160、绑定 24、免费景点 4（无商品）；向量库 10 + 18 条；北京检索命中内容层且带 `offer`；可售项排在最前；免费景点 `offer` 为空；成都检索结果全部来自高德。
- 测试场景（等价脚本执行 `tests/test_contents.py`）7 项全部通过：导入与幂等、只索引已发布内容、可售标注（故宫 60 元 / 剩余 200）、停售后不可售、可售优先且近者优先、未登录访问 401。
- 在真实数据库上执行三个脚本：内容 28 条、供应商 2 个、商品 24 个、报价 2160 条、绑定 24 条，向量 28 条；重复执行不重复写入。
- `npm run build` 通过；OpenAPI 确认注册 6 条 `/api/v1/admin/contents` 路由。

### 偏离规格之处

- `sellable_summary`（第 7.4 节，标注为可选）未实现。
- 旧种子集合与 `scripts/seed_knowledge.py` 字典未删除，仅停止读取；退役按第二期执行。
- 发布与下架改为**自动同步向量**（原规格为手工触发），减少运营漏点；后台仍保留手动增量与重建按钮。

### 坐标录入与发布报错

- 编辑页新增「按名称查坐标」：以城市 + 名称查询 `/api/v1/admin/pois`，取首个带坐标的结果填入纬度与经度。`PoiReference` 增加可选 `lat`/`lng`，本地种子与高德两条来源都返回坐标。
- 发布缺字段时，后端在 `message` 中直接写明缺项（如「发布前需要补全：纬度、经度。」）并保留 `missing` 数组；前端发布被拒时自动打开编辑弹窗，把缺的字段摆在面前。

补充验证：

- `GET /api/v1/admin/pois?city=北京&keyword=太古里&type=attraction` 返回 200，本地种子「三里屯太古里」`39.9325 / 116.4583`、高德「红馆(三里屯太古里北区店)」`39.937413 / 116.454064`，均带坐标。
- 发布自动同步：新建一条草稿 → 发布 → `contents_attractions` 由 11 条变 12 条；下架后回到 11 条。
- 缺字段发布被拒时返回 `{'message': '发布前需要补全：纬度、经度。', 'missing': ['纬度', '经度']}`。

### 未验证

- 本机无 pytest，`tests/test_contents.py` 未通过 pytest 运行（上述脚本复用其场景函数）。
- 未在浏览器走查内容管理页（列表、编辑、绑定商品、发布、同步按钮）。
- 验收时后端进程未运行，未做 HTTP 级联调；改用进程内 OpenAPI 与服务层验证。
- 未跑真实规划链路（LLM 选点 + 排序）以观察 `offer` 在最终行程中的呈现。
- 未在 PostgreSQL 上验证。
