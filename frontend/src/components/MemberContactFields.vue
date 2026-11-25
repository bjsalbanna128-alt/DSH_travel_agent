<script setup lang="ts">
import { documentLabels, type ContactChanges, type ContactView } from '../types/membership'

defineProps<{ contact?: ContactView; prefix: string }>()
const form = defineModel<ContactChanges>({ required: true })
</script>

<template>
  <fieldset class="member-contacts">
    <legend>联系方式与证件</legend>
    <div class="resource-form-grid">
      <el-form-item label="联系电话" :for="`${prefix}-phone`">
        <el-input :id="`${prefix}-phone`" v-model="form.phone" :placeholder="contact?.phone_mask ?? '选填'"
          :disabled="form.clearPhone" autocomplete="off" maxlength="48" inputmode="tel" />
        <el-checkbox v-if="contact?.phone_mask" v-model="form.clearPhone">清除已保存的电话</el-checkbox>
      </el-form-item>
      <el-form-item label="证件类型">
        <el-select v-model="form.documentType" :aria-label="`${prefix === 'profile' ? '本人' : '出行人'}证件类型`"
          placeholder="选填" clearable value-on-clear="" :disabled="form.clearDocument">
          <el-option v-for="(label, key) in documentLabels" :key="key" :label="label" :value="key" />
        </el-select>
      </el-form-item>
      <el-form-item label="证件号码" :for="`${prefix}-document`">
        <el-input :id="`${prefix}-document`" v-model="form.documentNumber" :placeholder="contact?.document_mask ?? '选填'"
          :disabled="form.clearDocument" autocomplete="off" maxlength="80" />
        <el-checkbox v-if="contact?.document_filled" v-model="form.clearDocument">清除已保存的证件</el-checkbox>
      </el-form-item>
    </div>
    <p class="resource-muted">{{ contact?.document_filled ? '证件已填写' : '证件未填写' }}。留空可保留已保存内容。</p>
  </fieldset>
</template>

<style scoped>
.member-contacts { padding: 0; border: 0; min-width: 0; margin-bottom: 16px; }
.member-contacts legend { font-weight: 600; margin-bottom: 10px; }
</style>
