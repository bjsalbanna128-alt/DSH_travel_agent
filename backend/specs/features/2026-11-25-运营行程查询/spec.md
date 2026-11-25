# 运营行程查询

## 原因与目标

C 端用户完成行程规划并确认后，行程写入 `trips` 表，但 B 端没有任何入口可以查到它：`/api/v1/trips/{id}` 强制按归属过滤，运营拿别人的行程号只会得到 404；后台也没有行程页面。

客服核实问题、运营抽查质量都需要按用户或行程号查已确认的行程。本次提供只读查询入口，并补一个「用户确认的是哪一版」的标记字段。

目标：

- 运营可按用户名、目的地、时间范围查询**已确认**的行程，并按行程号查看详情。
- 详情可查看当前行程内容与历史版本，**不可修改**。
- 记录用户确认时的版本号，避免把草稿期的 AI 调整版本误认为确认版本。

## 范围和边界

### 一、数据变更

1. `trips` 新增可空整数列 `confirmed_version`，语义为「用户确认行程时的版本号」。
2. `trips` 新增索引 `ix_trips_user_status_updated(user_id, status, updated_at)`，支撑按用户与状态筛选、按更新时间排序。

写入时机（本规格的核心约束）：

| 动作 | `trips.version` | `confirmed_version` |
|---|---|---|
| 生成草稿 | 1 | 空 |
| 草稿期 AI 调整 | +1 | 空 |
| **确认行程** | 不变 | **写入当时版本号** |
| 重复确认同一版本 | 不变 | 不变（幂等，保留首次值） |
| 确认后手动编辑 | +1 | **不变** |
| 回滚到历史版本 | **+1（追加一个新版本，内容取目标版本）** | **不变** |

回滚沿用现有 C 端实现：它不把版本号回退，而是用目标版本的内容追加一个新版本，历史保持只增不改。「当前版本」指向这个新追加的版本。

旧数据：迁移后保持为空，不猜测历史确认版本；B 端显示「未记录（该功能上线前确认）」。

### 二、接口

运营端，全部只读，挂在 `/api/v1/admin/trips`，沿用 `require_operator`。

```
GET /api/v1/admin/trips
    username       模糊匹配用户名，留空为全部
    destination    模糊匹配目的地，留空为全部
    start / end    按 updated_at 的日期范围（含首尾），留空不限
    page / page_size
    → 仅 status = 'completed'，按 updated_at 倒序、id 倒序（保证分页稳定）
```

列表项字段：`id`、`username`、`title`、`destination`、`duration_days`、`budget_total`、`version`、`confirmed_version`、`created_at`、`updated_at`。

```
GET /api/v1/admin/trips/{trip_id}
    → 行程基础信息 + 当前 itinerary + 全部版本元数据
```

版本元数据字段：`version`、`description`、`created_at`，并带两个布尔标记：`is_current`（等于 `trips.version`）、`is_confirmed`（等于 `confirmed_version`）。

```
GET /api/v1/admin/trips/{trip_id}/versions/{version}
    → 该版本的完整 itinerary，供对比历史版本
```

约定：

1. 行程不存在或 `status != 'completed'` 时，详情与版本接口一律返回 404，不区分「不存在」与「是草稿」，避免暴露草稿存在。
2. 用户名不存在时列表返回空结果，不返回 404。
3. 详情返回 `travel_request`（出发城市、偏好、人数、预算等），供客服核对需求；不返回任何账号联系方式。
4. 不提供任何写接口：不改单、不回滚、不删除。

### 三、前端

1. 后台导航新增「行程查询」，路由 `/admin/trips`、`/admin/trips/:id`，随 `/admin` 继承 `area: 'b'`。
2. 列表页：用户名、目的地、日期范围筛选 + 表格 + 分页；空态与错误态分开显示。
3. 详情页：基础信息卡片 + 当前行程（复用现有 `DayPlanList` 逐日展示）+ 版本时间线。
4. 版本时间线：标注「当前版本」与「确认版本」，点击某一版按需拉取该版内容并展示对比区域；无任何编辑或回滚入口。
5. `confirmed_version` 为空时，版本区显示「未记录（该功能上线前确认）」。

### 非目标

- 不提供行程编辑、回滚、删除。
- 不做订单维度的行程查询（订单系统未上线）。
- 不做行程导出、分享或二维码。
- 不在 B 端展示地图。
- 不改变 C 端的行程列表与详情行为。

### 可能受影响的现有行为

- `trips` 加列与索引，旧库需要迁移；新库随初始化流程建表。
- 确认流程（`apply_draft_decision`）新增一次字段写入；编辑与回滚逻辑不写该字段，行为不变。
- 新增后台导航入口与两个页面，`area: 'b'` 已由现有守卫保证只有运营可进。
- 列表查询跨越用户维度，需 `trips` 与 `users` 联表取用户名；`username` 匹配沿用会员列表的模糊匹配写法。

## 验收与回归

1. 草稿行程不出现在列表；直接用草稿的 `trip_id` 请求详情返回 404。
2. 已确认行程出现在列表中；用户名模糊匹配可命中该用户的全部已确认行程；用户名不存在返回空列表。
3. 分页翻页结果稳定，不出现重复或遗漏。
4. 确认一份草稿后，`confirmed_version` 等于当时的 `version`。
5. 确认后手动编辑一次，`version` 加 1，`confirmed_version` 不变。
6. 回滚到历史版本后，版本号加 1、新版本内容等于目标版本，`confirmed_version` 不变；详情中「当前版本」指向新追加的版本。
7. 重复确认同一版本，`confirmed_version` 保持不变（幂等）。
8. 旧行程 `confirmed_version` 为空时，详情显示「未记录」而不是猜测值。
9. 详情返回当前 itinerary 与全部版本元数据；按版本号可取到该版 itinerary。
10. 游客调用任一运营行程接口返回 403；未登录返回 401。
11. 所有接口仅 GET，不存在写入路由。

## 测试与回归计划

后端用例（隔离 SQLite，复用现有会员/资源测试的初始化方式）：

1. `test_draft_trip_is_hidden_from_operator`：草稿不出现在列表，详情 404。
2. `test_operator_lists_confirmed_trips_by_username`：模糊匹配、留空为全部、用户名不存在为空。
3. `test_confirm_records_version`：确认后 `confirmed_version` 等于确认时版本。
4. `test_edit_after_confirm_keeps_confirmed_version`：编辑后版本加 1 而确认版本不变。
5. `test_rollback_keeps_confirmed_version`：回滚后当前版本变化、确认版本不变。
6. `test_repeat_confirm_is_idempotent`：重复确认不改确认版本。
7. `test_legacy_trip_without_confirmed_version`：空值正常返回，不报错。
8. `test_operator_only_and_read_only`：游客 403、未登录 401、无写路由。

回归：C 端行程列表与详情、草稿确认流程、回滚流程、前端构建。

## 待定项

1. 日期筛选依据 `updated_at`（默认）还是 `created_at`。
2. 详情是否返回 `travel_request`。默认返回，便于核对用户原始需求。
3. 历史版本内容按需单独取（默认）还是一次性随详情返回。默认按需，避免详情响应过大。
4. 旧数据是否回填 `confirmed_version`。默认不回填，显示「未记录」。

## 验证记录

已实现。涉及文件：

- 后端：`db/models.py`（`confirmed_version` + 索引）、`db/trip_operator_migration.py`（旧库补列与索引）、`db/database.py`（初始化时调用迁移）、`services/trip_store.py`（确认时写入、字典输出新增字段）、`schemas/admin_trips.py`、`services/admin_trips.py`、`api/admin_trips.py`、`api/admin.py`（挂载）
- 前端：`types/adminTrips.ts`、`api/adminTrips.ts`、`views/AdminTripsPage.vue`、`views/AdminTripDetailPage.vue`、`router/index.ts`、`components/AdminLayout.vue`

与规格的偏差（按实际实现修正，已同步上文）：

- **回滚语义**：现有 `rollback_trip` 不把版本号回退，而是用目标版本内容追加一个新版本。规格原先写的是「版本变为目标版本」，已改为「版本 +1、内容取目标版本」，`confirmed_version` 不变这一条不变。

已执行：

- 9 个验收场景全部通过（等价脚本直接调用服务与 HTTP 接口，每个场景使用独立临时库）：草稿隐藏与 404、按用户名/目的地筛选与分页、确认写入 `confirmed_version`、确认后编辑不改确认版本、回滚追加新版本且确认版本不变、重复确认幂等、旧数据空值正常返回、权限与只读（游客 403、未登录 401、POST/PATCH/DELETE 均为 405）、迁移可重复执行并补回缺失列与索引。
- OpenAPI 确认仅注册 3 个 GET 路由：`/api/v1/admin/trips`、`/api/v1/admin/trips/{trip_id}`、`/api/v1/admin/trips/{trip_id}/versions/{version}`。
- 前端 `npm run build` 通过（`vue-tsc` 类型检查 + vite 构建，646ms，仅既存 chunk 体积提示）。

未验证：

- 本机没有 pytest，`backend/tests/test_admin_trips.py` 未通过 pytest 运行；上述脚本复用了该文件的场景函数，但执行器不同。
- 未在浏览器走查「行程查询」列表与详情页（列表渲染、版本弹窗、时间显示）。
- 迁移只在临时库上用「建表后删列再加列」模拟过，未在真实旧库上执行；未在 PostgreSQL 上验证。
- 未验证列表在大量数据下的分页稳定性与索引效果。
