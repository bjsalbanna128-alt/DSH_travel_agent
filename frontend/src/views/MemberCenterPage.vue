<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminError } from '../api/adminResources'
import { membershipApi } from '../api/membership'
import MemberContactFields from '../components/MemberContactFields.vue'
import MemberPointHistory from '../components/MemberPointHistory.vue'
import MemberPointsOverview from '../components/MemberPointsOverview.vue'
import { useAdminQuery } from '../composables/useAdminQuery'
import { contactChanges, contactPayload, documentLabels, genderLabels, type Gender, type Traveler } from '../types/membership'

const { data: profile, loading, error, load: loadProfile } = useAdminQuery(membershipApi.profile)
const { data: travelers, loading: loadingTravelers, error: travelerLoadError, load: loadTravelers } =
  useAdminQuery(membershipApi.travelers)
const { data: points, error: pointsError, load: loadPoints } = useAdminQuery(membershipApi.points)
const form = ref({ nickname: '', avatar_url: '', birthday: '', gender: '' as Gender | '', real_name: '' })
const profileContact = ref(contactChanges())
const travelerContact = ref(contactChanges())
const newTraveler = () => ({ real_name: '', relationship: '', is_default: false })
const travelerForm = ref(newTraveler())
const travelerDialog = ref(false)
const selected = ref<Traveler>()
const profileError = ref('')
const travelerError = ref('')
const listError = ref('')
const busy = ref('')
let mutation: AbortController | undefined
let disposed = false
const avatar = computed(() => profile.value?.avatar_url)

onMounted(() => { void loadProfile(); void loadTravelers(); void loadPoints() })
onScopeDispose(() => { disposed = true; mutation?.abort(); profileContact.value = contactChanges(); travelerContact.value = contactChanges() })
watch(profile, value => {
  form.value = {
    nickname: value?.nickname ?? '', avatar_url: value?.avatar_url ?? '', birthday: value?.birthday ?? '',
    gender: value?.gender ?? '', real_name: value?.real_name ?? '',
  }
  profileContact.value = contactChanges(value)
})

async function perform(key: string, failure: typeof profileError, run: (signal: AbortSignal) => Promise<void>) {
  if (disposed || busy.value) return
  const request = new AbortController()
  mutation = request
  busy.value = key
  failure.value = ''
  try {
    await run(request.signal)
  } catch (problem) {
    if (!request.signal.aborted) failure.value = adminError(problem)
  } finally {
    if (mutation === request) busy.value = ''
  }
}

function saveProfile() {
  const current = profile.value
  void perform('profile', profileError, async signal => {
    const mainFields = Object.fromEntries(Object.entries(form.value).map(([key, value]) => [key, value.trim() || null]))
    const saved = await membershipApi.saveProfile({ ...mainFields, ...contactPayload(profileContact.value, current) }, signal)
    if (signal.aborted) return
    profile.value = saved
    ElMessage.success('会员档案已保存')
  })
}

function editTraveler(row?: Traveler) {
  selected.value = row
  travelerForm.value = row ? { real_name: row.real_name ?? '', relationship: row.relationship, is_default: row.is_default } : newTraveler()
  travelerContact.value = contactChanges(row)
  travelerError.value = ''
  travelerDialog.value = true
}

function saveTraveler() {
  const current = selected.value
  void perform('traveler', travelerError, async signal => {
    if (!travelerForm.value.real_name.trim() || !travelerForm.value.relationship.trim()) {
      throw new Error('请填写出行人姓名和关系。')
    }
    const changes = { ...travelerForm.value, ...contactPayload(travelerContact.value, current) }
    if (current) await membershipApi.editTraveler(current.id, changes, signal)
    else await membershipApi.addTraveler(changes, signal)
    if (signal.aborted) return
    travelerDialog.value = false
    travelerContact.value = contactChanges()
    ElMessage.success('出行人已保存')
    await loadTravelers()
  })
}

async function deleteTraveler(row: Traveler) {
  const confirmed = await ElMessageBox.confirm(`删除出行人「${row.real_name}」？`, '删除出行人', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => true, () => false)
  if (!confirmed) return
  await perform('delete', listError, async signal => {
    await membershipApi.deleteTraveler(row.id, signal)
    if (!signal.aborted) await loadTravelers()
  })
}
</script>

<template>
  <section class="resource-page support-page">
    <header class="resource-titlebar support-title">
      <h1>会员中心</h1>
      <router-link :to="{ name: 'profile' }" class="resource-link">返回个人中心</router-link>
    </header>
    <section class="resource-panel">
      <div class="resource-titlebar member-section">
        <h2>会员档案</h2>
        <img v-if="avatar" :src="avatar" class="member-avatar" alt="会员头像" referrerpolicy="no-referrer">
      </div>
      <el-alert v-if="error || profileError" :title="error || profileError" type="error" :closable="false" show-icon class="support-error" />
      <el-button v-if="error" @click="loadProfile">重试读取档案</el-button>
      <p v-if="loading && !profile" role="status">正在读取会员档案…</p>
      <el-form v-if="profile" label-position="top" :disabled="Boolean(busy)" autocomplete="off" @submit.prevent="saveProfile">
        <div class="resource-form-grid">
          <el-form-item label="昵称"><el-input v-model="form.nickname" maxlength="60" /></el-form-item>
          <el-form-item label="姓名"><el-input v-model="form.real_name" maxlength="100" /></el-form-item>
          <el-form-item label="生日"><el-input v-model="form.birthday" type="date" /></el-form-item>
          <el-form-item label="性别">
            <el-select v-model="form.gender" placeholder="选填" clearable value-on-clear="" aria-label="性别">
              <el-option v-for="(label, key) in genderLabels" :key="key" :label="label" :value="key" />
            </el-select>
          </el-form-item>
          <el-form-item label="头像图片地址" class="resource-form-wide">
            <el-input v-model="form.avatar_url" maxlength="500" placeholder="HTTPS 地址，选填" />
          </el-form-item>
        </div>
        <MemberContactFields v-model="profileContact" :contact="profile" prefix="profile" />
        <el-button type="primary" native-type="submit" :loading="busy === 'profile'">保存会员档案</el-button>
      </el-form>
    </section>

    <section class="resource-panel">
      <div class="resource-titlebar member-section">
        <h2>常用出行人</h2>
        <el-button :disabled="Boolean(busy)" @click="editTraveler()">新增出行人</el-button>
      </div>
      <el-alert v-if="travelerLoadError || listError" :title="travelerLoadError || listError" type="error" :closable="false" show-icon class="support-error" />
      <el-button v-if="travelerLoadError" @click="loadTravelers">重试读取出行人</el-button>
      <p v-if="loadingTravelers && !travelers" role="status">正在读取出行人…</p>
      <p v-if="travelers && !travelers.length" class="support-empty">暂无常用出行人</p>
      <ul v-if="travelers?.length" class="member-traveler-list">
        <li v-for="row in travelers" :key="row.id">
          <div class="resource-actions">
            <strong>{{ row.real_name }}</strong><span>{{ row.relationship }}</span>
            <el-tag v-if="row.is_default" size="small">默认</el-tag>
          </div>
          <p class="resource-muted">{{ row.phone_mask ?? '未填写电话' }} ·
            {{ row.document_type ? `${documentLabels[row.document_type]} ${row.document_mask}` : '证件未填写' }}</p>
          <div class="resource-actions">
            <el-button link type="primary" :disabled="Boolean(busy)" @click="editTraveler(row)">编辑</el-button>
            <el-button link type="danger" :disabled="Boolean(busy)" @click="deleteTraveler(row)">删除</el-button>
          </div>
        </li>
      </ul>
    </section>
    <MemberPointsOverview v-if="points" :points="points" />
    <section v-if="points" class="resource-panel resource-stack" aria-label="演示积分">
      <h2>演示积分</h2>
      <p>{{ points.demo_balance ?? 0 }} 分 · 模拟支付 {{ points.demo_payments ?? 0 }} 笔 · 模拟退款 {{ points.demo_refunds ?? 0 }} 笔</p>
      <small>仅用于演示交易，会员权益按正式积分计算。</small>
    </section>
    <div v-else-if="pointsError" class="resource-panel resource-stack">
      <el-alert :title="pointsError" type="error" :closable="false" show-icon />
      <div><el-button @click="loadPoints">重试读取积分</el-button></div>
    </div>
    <MemberPointHistory />

    <el-dialog v-model="travelerDialog" :title="selected ? '编辑出行人' : '新增出行人'"
      width="580px" class="resource-dialog" :show-close="!busy" :close-on-click-modal="!busy"
      :close-on-press-escape="!busy" @closed="travelerContact = contactChanges()" destroy-on-close>
      <el-alert v-if="travelerError" :title="travelerError" type="error" :closable="false" show-icon class="support-error" />
      <el-form label-position="top" autocomplete="off" :disabled="Boolean(busy)" @submit.prevent="saveTraveler">
        <div class="resource-form-grid">
          <el-form-item label="出行人姓名" required><el-input v-model="travelerForm.real_name" maxlength="100" /></el-form-item>
          <el-form-item label="关系" required><el-input v-model="travelerForm.relationship" maxlength="30" placeholder="例如家人、朋友" /></el-form-item>
        </div>
        <MemberContactFields v-model="travelerContact" :contact="selected" prefix="traveler" />
        <el-checkbox v-model="travelerForm.is_default">设为默认出行人</el-checkbox>
        <div class="resource-actions member-section">
          <el-button @click="travelerDialog = false">取消</el-button>
          <el-button type="primary" native-type="submit" :loading="busy === 'traveler'">保存出行人</el-button>
        </div>
      </el-form>
    </el-dialog>
  </section>
</template>

<style scoped>
.member-section { margin-bottom: 12px; }
.member-avatar { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; }
.member-traveler-list { list-style: none; }
.member-traveler-list li { border-top: 1px solid #e4e8ef; padding: 11px 0; }
.member-traveler-list p { margin: 5px 0; overflow-wrap: anywhere; }
</style>
