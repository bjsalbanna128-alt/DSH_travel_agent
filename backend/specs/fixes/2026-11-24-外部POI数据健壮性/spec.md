# 外部 POI 数据健壮性

## 原因与目标

高德 POI 的字段解析和请求参数缺少边界处理，且多条失败路径都直接返回空列表，调用方无法区分「该城市确实没有数据」和「接口或解析出错」。结果是景点、酒店、餐厅在特定条件下静默退化为纯大模型生成，坐标、评分、票价全部丢失，日志只有一行 warning。

本次修复要达到的效果：

- 单条 POI 数据异常不再作废整批结果。
- 长行程不再因高德 `offset` 上限而整批丢失景点候选。
- 重排模型不可用后只尝试加载一次，不再每次检索重复阻塞。
- POI 检索的失败原因返回给调用方，可区分、可观测。

## 范围和边界

涉及文件：`app/services/amap.py`、`app/services/poi_service.py`。配套测试放 `backend/tests/`。

### A1 高德 `biz_ext` 类型防御

位置：`app/services/amap.py:92、97、103、105、108、110、113`。

现状：统一写法 `p.get("biz_ext", {}).get(...)`。高德对无扩展信息的 POI 会返回 `"biz_ext": []` 或 `"biz_ext": null`，此时默认值 `{}` 不生效，`.get` 抛 `AttributeError`；异常被 `amap.py:128` 的 `except Exception` 接住，整个批次 `return []`。

要求：

- 取 `biz_ext` 时按类型判断，非 dict（含 None、list）一律按空 dict 处理，7 处统一。
- 单条 POI 的解析异常只跳过该条并计数，不放弃整批；整批仍返回已成功解析的部分。
- 被跳过的条数需要能返回给调用方（见 A0 的 `skipped`）。

### A2 高德 `offset` 上限（取截断方案）

位置：`app/services/poi_service.py:115`（`limit = days * 5`）、`:134`（`offset=limit`）。

现状：高德 `v3/place/text` 文档建议 `offset` 不超过 25，超过时可能报错。行程 ≥ 6 天时，原代码会请求超过 25 条，一旦接口报错，景点候选整批为空。

要求：

- 传给高德的 `offset` 不超过 25，超出时**截断**（不分页补齐），按截断后的量取候选。
- 触发截断时记录一条 info 日志，包含原请求量和实际取值，并通过 A0 的 `skipped` 之外的独立日志体现；截断属于正常降级，不置失败原因。
- 酒店（`count=10`）与餐厅（`count=15`）的 `offset` 未超限，不在本次改动内。

### A3 重排模型失败开关

位置：`app/services/poi_service.py:17-31`、`:70-73`。

现状有两个缺陷。缓存实例存在时，`_get_reranker` 在检查可用性之前就复用了它。`_rerank` 的异常分支只修改了局部变量，没有禁用模块级实例。实际模型在第一次重排时惰性加载，因此首次加载或预测失败后，后续检索仍会尝试使用该实例。

要求：

- 可用性判断优先于实例复用。
- 失败时同时清除实例并置不可用，且写入模块级状态。
- 判定不可用后，本次进程生命周期内不再尝试加载，直接按原顺序返回。

### A0 失败原因返回给调用方

位置：`app/services/amap.py:22`（`search_poi` 定义）、`:64-66`（status 异常）、`:128-130`（异常吞掉）。

现状「无数据」「接口报错」「解析出错」三种情况都返回 `[]`，调用方拿到空列表后无法判断发生了什么，降级是否发生只能靠猜日志。

要求：

- `search_poi` 的返回值由 `list[dict]` 改为结构化结果，包含三项：`items`（POI 列表）、`reason`（失败原因，`None` 表示本次调用成功）、`skipped`（A1 中被跳过的单条数量）。
- `reason` 使用固定取值，至少区分三种情况：未配置 API key、高德返回非成功 status、请求或整体解析失败。成功但结果为空时 `reason` 为 `None`（「没有数据」不等于「失败」）。
- `poi_service` 中三处调用点（`:130`、`:159`、`:196`）解包新结构，`reason` 非空时写 warning 日志（含城市、关键词、POI 类型、原因），`skipped > 0` 时写 info 日志。
- Redis 缓存中仍只存 POI 列表，不存结构体；缓存命中时按 `reason=None`、`skipped=0` 还原成功结果。
- 降级判定后写日志的行为保留，不能被「返回给调用方」取代。

### 非目标

- 不接入高德路径规划或换乘接口，交通方案的数据来源不在本次范围。
- 不改变 `search_attractions_hybrid` / `search_hotels_hybrid` / `search_restaurants_hybrid` 的返回类型（仍为 `list[dict]`），不把 `reason` 继续传给 Agent 节点；上层感知降级留待后续单独评估。
- 不改变缓存 key 格式。
- 不调整景点/酒店/餐厅的检索策略、召回数量或重排算法。

### 可能受影响的现有行为

- `search_poi` 返回类型变化，三处调用点必须同步解包；仓库内无其它调用方，现有测试未引用该函数。
- 原本整批为空的场景现在会返回部分或全部结果，候选数量和排序会变化；依赖「空结果」的既有用例需复核。
- A2 改变 `offset` 后缓存 key 随之变化，旧缓存自然失效，不影响正确性；异常路径本就不写缓存。
- A3 判定不可用后，候选顺序退回「Chroma 优先 + 高德补充」的合并顺序，不再经过重排。

## 验收条件

1. 一批响应中同时包含 `biz_ext` 为列表、为 `null` 和为字典的 POI 时，只要其余字段可解析，三种记录都应保留。`skipped` 只计入整条无法解析的 POI。
2. POI 中 `location` 等其它字段格式异常时，同样只跳过该条，不影响同批其它结果。
3. `days = 7` 调用景点检索时，传给高德的 `offset <= 25`，并留有截断日志。
4. 重排模型读取失败后，连续两次检索只尝试加载一次，第二次直接按原顺序返回。
5. 未配置 API key、高德返回非成功 status、请求失败三种情况，调用方拿到的 `reason` 各不相同；成功但结果为空时 `reason` 为 `None`。
6. 缓存命中时返回的成功结果 `reason` 为 `None`、`skipped` 为 0。
7. 现有 `backend/tests/test_planning_regressions.py` 中与 POI 检索相关的断言仍通过。

## 测试与回归计划

新增 `backend/tests/test_poi_robustness.py`，全部使用假响应或 monkeypatch，不依赖网络、不依赖真实 API key：

1. `test_biz_ext_list_and_null_keep_poi`：只有 `biz_ext` 为列表或 null 的 POI 仍保留并使用默认扩展字段。确实无法解析的整条记录才计入 `skipped`。
2. `test_bad_poi_fields_do_not_drop_batch`：构造字段格式异常的 POI，断言整批未被作废。
3. `test_offset_capped_for_long_trips`：`days=7` 时断言传入的 `offset <= 25`。
4. `test_reranker_disabled_after_first_failure`：`rerank` 抛异常，连续两次调用断言加载只发生一次。
5. `test_failure_reason_returned_to_caller`：分别构造缺少 key、status 非成功、请求异常三种响应，断言 `reason` 取值互不相同且符合约定；成功但为空时 `reason` 为 `None`。

回归：`backend/tests/test_planning_regressions.py` 中 `test_chroma_combines_metadata_filters` 等涉及 POI 合并的用例保持通过。前端无需改动，验证时以详情页景点/酒店/餐厅的数量与字段完整度为准。

## 待定项

无。A2 截断、A0 返回失败原因均已确认，实现按上述要求执行。

## 验证记录

- 在后端目录运行 `python -m pytest -q --basetemp <隔离目录>`，43 项通过，其中本次新增 15 项。覆盖扩展字段容错、部分与整批解析失败、失败原因和降级日志、缓存命中、长行程截断、重排加载和预测失败后的回退。
- 用模拟高德响应为景点、酒店、餐厅各提供一条有效记录和一条坐标异常记录。三类检索各保留一条有效记录。在本地隔离环境打开路书详情，确认各展示一条，名称、评分和费用与测试输入一致，费用合计为 ¥335。
- 本次验证使用模拟高德响应和缓存，未连接真实高德 API、Redis 或重排模型。
