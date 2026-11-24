# 交通调度空转

## 原因与目标

supervisor 用「交通产出是否非空」判断「交通这步做没做完」：

```python
has_transport = bool(state.get("transport", {}).get("intercity") or
                     state.get("transport", {}).get("intraday"))
```

本地游、全程步行或无需额外交通安排时，城际和城内交通清单可以都为空。出发城市未知时，`intercity` 可以为空，`intraday` 仍可包含安排。两类清单都为空时，原规则会再次派发 `transport`，超过调度上限后才强制进入编译。

同时安全阀写死 `iteration > 15`，`sse.py` / `ws.py` 传入的 `max_iterations` 从未被读取。

重复派发会增加模型调用次数和等待时间，进度面板可能重复出现「规划交通」。

目标：让「交通是否已尝试」由状态键是否存在决定，与产出内容无关；让迭代上限读配置。

## 范围和边界

### 判断依据改为「是否已尝试」

`app/graph/nodes/supervisor.py`：

- `has_transport` 改为 `"transport" in state`。键存在即视为已尝试，空列表也算完成。
- `_build_state_summary` 中的交通状态同步改为同一口径，避免提示词与调度判断不一致。

### 节点输出规整

`app/graph/nodes/agents.py`：

- 新增 `_normalize_transport(plan)`，把模型输出收敛为 `{"intercity": [...], "intraday": [...]}`。
- JSON 解析后的值为非字典（`None`、数组、字符串等）时，两类清单都取空列表。字典中缺少的字段按空列表处理，类型错误的字段单独回退，保留另一个可用列表。收到非字典或错误字段类型时记录警告。模型调用失败或无法解析成 JSON 时沿用现有错误处理。
- `transport_node` 的返回值改用该结构，保证只要节点跑过，状态里就一定有这两个键。

### 迭代上限可配置

`app/graph/nodes/supervisor.py`：

- `if iteration > state.get("max_iterations", 15)`，缺省值仍为 15。
- 安全阀日志与状态摘要中的上限改为实际取值。
- 安全阀和重排分支在追加当前调度记录时保留已有执行历史。

### 非目标

- 不改变 `_rule_based_fallback` 的调度顺序（景点 → 路线 → 酒店 → 餐厅 → 交通 → 编译）。
- 不改变交通方案的数据来源，仍由 `transport_node` 的大模型调用产出。
- 重排景点和路线时保留已尝试的交通，理由见下。
- 不调整编译阶段 `_group_transport` 的按天映射逻辑。

### 可能受影响的现有行为

- **重排（`needs_replan`）后复用已尝试的交通。** `transport_node` 的输入只有出发城市、目的地和天数，景点与路线重排不会改变这些输入。
- **减少重复调用。** 空交通结果可直接进入编译，`agent_history` 保留单次 `transport_agent` 记录。
- **`max_iterations` 开始生效。** 默认值仍为 15，调小该值会使调度更早进入编译。
- **交通为空时编译行为不变。** `_group_transport` 本就接受空结构，规整后输入形状更稳定。

## 验收与回归

1. 不需要城际交通的行程（本地游、全程步行）中，`transport` 只被调度一次，`agent_history` 只有一条 `transport_agent` 记录，进度面板不再出现重复的「规划交通」。
2. 模型返回 `{}`、`null`、数组或两类字段均为错误类型时，`state["transport"]` 为 `{"intercity": [], "intraday": []}`。只有一个字段类型错误时，保留另一个合法列表。
3. `max_iterations` 设为 5 且已用 5 轮时，第 6 轮强制进入编译。设为 30 且已用 15 轮时，仍能继续调度。两条分支都保留已有执行历史。
4. 景点 → 路线 → 酒店 → 餐厅 → 交通 → 编译的单次顺序不变；交通为空时正常进入编译。
5. 回归用例 `backend/tests/test_transport_scheduling.py` 覆盖上述行为，并验证约束重排只重跑景点和路线、仍保留原来的交通记录。

## 验证记录

- 使用项目已有的 Python 测试环境，在 `backend/` 运行全量 pytest。58 项通过，其中 `test_transport_scheduling.py` 15 项。覆盖空方案、错误字段归一化、保留有效交通段、迭代上限及已有执行历史。
- 运行真实 LangGraph 编排，模拟模型响应和其他节点的数据。无论是否触发一次约束重排，空交通都只执行一次，图进入待确认，执行历史保留一条交通记录。
- 验证使用模拟数据，未调用真实 DeepSeek、未测量线上耗时，也未在浏览器检查进度展示。
