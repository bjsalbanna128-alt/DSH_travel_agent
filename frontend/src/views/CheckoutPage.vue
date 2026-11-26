<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminError } from '../api/adminResources'
import { checkoutApi } from '../api/checkout'
import { ordersApi } from '../api/orders'
import { useAdminQuery } from '../composables/useAdminQuery'
import { formatFen, kindLabels, type CheckoutItem } from '../types/checkout'

const route = useRoute()
const router = useRouter()
const tripId = computed(() => String(route.params.tripId))
const { data, loading, error, load } = useAdminQuery(signal => checkoutApi.options(tripId.value, signal))

const chosen = reactive<Record<string, number>>({})
const contact = reactive({ name: '', phone: '' })
const travelers = reactive([{ name: '', document_type: '身份证', document_number: '', phone: '' }])
const submitting = ref(false)


const total = computed(() => (data.value?.items ?? [])
  .filter(item => item.sellable && chosen[item.product_id])
  .reduce((sum, item) => sum + item.unit_price_fen * (chosen[item.product_id] ?? 0), 0))

const selectedCount = computed(() => Object.values(chosen).filter(Boolean).length)

function key(item: CheckoutItem) {
  return item.product_id
}

function toggle(item: CheckoutItem) {
  if (!item.sellable) return
  chosen[key(item)] = chosen[key(item)] ? 0 : item.quantity
}

function quantity(item: CheckoutItem) {
  return chosen[key(item)] ?? 0
}

function setQuantity(item: CheckoutItem, value: number) {
  chosen[key(item)] = Math.max(0, Math.min(30, value || 0))
}

function addTraveler() {
  travelers.push({ name: '', document_type: '身份证', document_number: '', phone: '' })
}

async function submit() {
  if (!selectedCount.value) {
    ElMessage.warning('请至少勾选一项。')
    return
  }
  if (!contact.name.trim() || !contact.phone.trim()) {
    ElMessage.warning('请填写联系人与联系电话。')
    return
  }
  const filled = travelers.filter(item => item.name.trim())
  if (!filled.length) {
    ElMessage.warning('请至少填写一位出行人。')
    return
  }
  submitting.value = true
  try {
    const selected = (data.value?.items ?? [])
      .filter(item => item.sellable && chosen[key(item)])
      .map(item => item.kind === 'hotel'
        ? {
            kind: 'hotel', product_id: item.product_id,
            check_in: item.check_in, check_out: item.check_out,
            quantity: chosen[key(item)],
          }
        : {
            kind: 'ticket', product_id: item.product_id,
            service_date: item.service_date, quantity: chosen[key(item)],
          })
    const order = await ordersApi.create({
      contact_name: contact.name.trim(),
      contact_phone: contact.phone.trim(),
      trip_id: tripId.value,
      travelers: filled,
      selected,
    }, crypto.randomUUID())
    ElMessage.success(`订单 ${order.order_no} 已创建，请在 15 分钟内完成支付`)
    void router.push({ name: 'orders' })
  } catch (failure) {
    ElMessage.error(adminError(failure))
  } finally {
    submitting.value = false
  }
}

function renderGroup(kind: 'hotel' | 'ticket') {
  return (data.value?.items ?? []).filter(item => item.kind === kind)
}

onMounted(load)
</script>

<template>
  <section class="checkout-page">
    <header class="checkout-header">
      <el-button text @click="router.back()">← 返回行程</el-button>
      <h1>选择要预订的项目</h1>
      <span class="checkout-hint">只订需要的，也可以全部不选直接看路书</span>
    </header>

    <p v-if="loading" role="status">正在核对价格与库存…</p>
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="data?.undated_count" type="warning" :closable="false" show-icon
      title="这份行程还没有确定出行日期，价格与库存无法校验；先在聊天里补充日期后重新生成行程，即可预订。" />
    <p v-if="data && !data.items.length" class="checkout-empty">
      <template v-if="!data.offer_count">
        本次规划没有拿到我们的库存（商品检索异常，或该城市暂无上架商品）。请重新生成行程后再试。
      </template>
      <template v-else>
        这份行程里没有可预订的项目（未绑定商品的地点只能看，不能订）。
      </template>
    </p>

    <template v-else>
      <section v-for="kind in (['hotel', 'ticket'] as const)" :key="kind">
        <template v-if="renderGroup(kind).length">
          <h2>{{ kindLabels[kind] }}</h2>
          <div v-for="item in renderGroup(kind)" :key="item.product_id + item.service_date"
            class="checkout-item" :class="{ 'checkout-item-off': !item.sellable }">
            <el-checkbox :model-value="!!chosen[item.product_id]" :disabled="!item.sellable"
              @change="toggle(item)">
              {{ item.name }}
            </el-checkbox>
            <span class="checkout-meta">{{ item.service_date }}</span>
            <span class="checkout-meta">{{ formatFen(item.unit_price_fen) }}</span>
            <el-tag v-if="item.needs_date" type="warning" size="small">需先确定出行日期</el-tag>
            <el-tag v-else-if="!item.sellable" type="info" size="small">已售罄 / 不可售</el-tag>
            <el-tag v-else-if="item.remaining !== null && item.remaining <= 5" type="warning" size="small">
              剩 {{ item.remaining }}
            </el-tag>
            <el-input-number :model-value="quantity(item)" :min="0" :max="30" size="small"
              :disabled="!chosen[item.product_id]"
              @update:model-value="(value: number | undefined) => setQuantity(item, value ?? 0)" />
          </div>
        </template>
      </section>

      <section class="checkout-form">
        <h2>联系人与出行人</h2>
        <div class="checkout-grid">
          <el-input v-model="contact.name" placeholder="联系人姓名" maxlength="50" />
          <el-input v-model="contact.phone" placeholder="联系电话" maxlength="32" />
        </div>
        <div v-for="(traveler, index) in travelers" :key="index" class="checkout-grid">
          <el-input v-model="traveler.name" :placeholder="`出行人 ${index + 1}`" maxlength="50" />
          <el-input v-model="traveler.document_number" placeholder="证件号（仅保存掩码）" maxlength="64" />
          <el-input v-model="traveler.phone" placeholder="手机号" maxlength="32" />
        </div>
        <el-button text @click="addTraveler">+ 添加出行人</el-button>
      </section>

      <footer class="checkout-footer">
        <span>已选 {{ selectedCount }} 项，合计 <strong>{{ formatFen(total) }}</strong></span>
        <el-button type="primary" :loading="submitting" @click="submit">提交订单</el-button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.checkout-page { max-width: 900px; margin: 0 auto; padding: 20px 16px 40px; }
.checkout-header { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px; }
.checkout-header h1 { margin: 0; font-size: 22px; }
.checkout-hint { color: #909399; font-size: 13px; }
.checkout-empty { color: #909399; padding: 40px 0; text-align: center; }
.checkout-item { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #ebeef5; }
.checkout-item-off { opacity: .55; }
.checkout-meta { color: #606266; font-size: 13px; }
.checkout-form { margin-top: 24px; }
.checkout-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }
.checkout-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }
</style>



