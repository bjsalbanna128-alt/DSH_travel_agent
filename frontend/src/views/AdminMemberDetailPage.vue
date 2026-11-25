<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { membershipApi } from '../api/membership'
import MemberPointHistory from '../components/MemberPointHistory.vue'
import MemberPointsOverview from '../components/MemberPointsOverview.vue'
import PreferenceCard from '../components/PreferenceCard.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { documentLabels, genderLabels, memberTime, type ContactView } from '../types/membership'

const route = useRoute()
const { data, loading, error, load, clear } = useAdminQuery(signal => membershipApi.member(String(route.params.id), signal))
watch(() => route.params.id, () => { clear(); void load() }, { immediate: true })

function documentText(contact: ContactView) {
  return contact.document_type ? `${documentLabels[contact.document_type]} ${contact.document_mask}（证件已填写）` : '证件未填写'
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>会员详情</h1>
      <router-link :to="{ name: 'admin-members' }" class="resource-link">返回用户会员</router-link>
    </header>
    <div v-if="error" class="resource-panel resource-stack">
      <el-alert :title="error" type="error" :closable="false" show-icon />
      <div><el-button @click="load">重试</el-button></div>
    </div>
    <p v-else-if="loading" role="status">正在加载会员资料…</p>
    <template v-else-if="data">
      <section class="resource-panel">
        <h2>{{ data.username }}</h2>
        <dl class="support-meta">
          <div><dt>账号 ID</dt><dd>{{ data.id }}</dd></div>
          <div><dt>注册时间</dt><dd>{{ memberTime(data.registered_at) }}</dd></div>
          <div><dt>资料状态</dt><dd>{{ data.profile_complete ? '已完善' : '待完善' }}</dd></div>
        </dl>
      </section>
      <section class="resource-panel">
        <h2>会员档案</h2>
        <p class="resource-muted member-source">来源为游客填写</p>
        <p v-if="!data.profile.exists" class="support-empty">该游客尚未填写会员档案</p>
        <dl v-else class="support-meta">
          <div><dt>公开昵称</dt><dd>{{ data.profile.nickname ?? '—' }}</dd></div>
          <div><dt>姓名</dt><dd>{{ data.profile.real_name ?? '—' }}</dd></div>
          <div><dt>联系电话</dt><dd>{{ data.profile.phone_mask ?? '—' }}</dd></div>
          <div><dt>证件</dt><dd>{{ documentText(data.profile) }}</dd></div>
          <div><dt>生日</dt><dd>{{ data.profile.birthday ?? '—' }}</dd></div>
          <div><dt>性别</dt><dd>{{ data.profile.gender ? genderLabels[data.profile.gender] : '—' }}</dd></div>
        </dl>
      </section>
      <section class="resource-panel">
        <h2>常用出行人</h2>
        <el-table :data="data.travelers" row-key="id" empty-text="暂无常用出行人" class="member-travelers">
          <el-table-column prop="real_name" label="姓名" min-width="90" />
          <el-table-column prop="relationship" label="关系" min-width="90" />
          <el-table-column label="联系电话" min-width="130">
            <template #default="{ row }">{{ row.phone_mask ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="证件" min-width="190">
            <template #default="{ row }">{{ documentText(row) }}</template>
          </el-table-column>
          <el-table-column label="默认" width="70">
            <template #default="{ row }">{{ row.is_default ? '是' : '—' }}</template>
          </el-table-column>
        </el-table>
      </section>
      <section class="resource-panel">
        <h2>旅行偏好</h2>
        <p class="resource-muted member-source">来源为 AI 旅行画像</p>
        <PreferenceCard :profile="data.preferences" />
      </section>
      <MemberPointsOverview :points="data.points" />
      <MemberPointHistory :key="data.id" :member-id="data.id" />
    </template>
  </section>
</template>

<style scoped>
.member-source { margin: 7px 0 12px; }
.member-travelers { margin-top: 10px; }
</style>
