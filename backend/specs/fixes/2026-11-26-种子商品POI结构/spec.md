# 种子商品的 POI 结构不符合契约导致商品页 500

任务日期 2026-11-26。状态已修复。

## 原因

北京试点库存脚本把商品 POI 写成 `{"source": "seed", "source_id": "bj-hotel-1", "name": ..., "city": ...}`，而 `PoiReference` 的契约是：

```
source ∈ {amap, chroma}   id 必填   type 必填   source_id 不允许
```

于是 `ProductResponse` 校验失败，`GET /api/v1/admin/products` 直接 500，后台商品管理页只显示「请求失败（500）」。

## 范围与边界

- 种子脚本改为写入规范结构：`{"source": "seed", "id": "bj-hotel-1", "name": ..., "city": "北京", "type": "hotel"|"attraction"}`。
- `PoiReference.source` 增加 `"seed"`，容纳自建种子来源；`id`、`type` 仍必填，未知来源仍被拒绝。
- 一次性修复库中已写入的 24 条商品（把 `source_id` 迁移为 `id`，补齐 `type`）。
- 不改后台商品页与 POI 选择器逻辑。

## 验收

1. `GET /api/v1/admin/products` 返回 200，列表可正常渲染。
2. 商品详情与报价列表返回 200。
3. 新建商品时 POI 校验仍要求 `source`、`id`、`name`、`city`、`type`，来源只接受三种。

## 验证记录

- 修复后实测：商品列表 200、total 24；供应商列表 200、total 2；商品详情 200；报价列表 200、total 90，首日 `can_sell = true`，投放/剩余 `200 / 200`。
- 已修复库中 24 条商品的 POI 结构。
- 未在浏览器复测页面；未运行 pytest。
