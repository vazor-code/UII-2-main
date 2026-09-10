<template>
  <div class="page-container">
    <v-row>
      <v-col cols="12" md="4">
        <v-card>
          <v-card-title>Новый отчёт</v-card-title>
          <v-card-text>
            <v-select
              v-model="form.report_type"
              :items="reportTypes"
              item-title="title"
              item-value="value"
              label="Тип отчёта"
            />
            <v-select
              v-model="form.format"
              :items="formatOptions"
              item-title="title"
              item-value="value"
              label="Формат"
            />
            <v-btn color="primary" block :loading="creating" @click="createReport">
              Сформировать
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="8">
        <v-card>
          <v-card-title>Задачи отчётов</v-card-title>
          <v-data-table
            :headers="headers"
            :items="jobs"
            density="compact"
            item-value="id"
          >
            <template #[`item.status`]="{ item }">
              <v-chip :color="jobColor(item.status)" size="small">{{ item.status }}</v-chip>
            </template>
            <template #[`item.created_at`]="{ item }">
              {{ formatDate(item.created_at) }}
            </template>
            <template #[`item.actions`]="{ item }">
              <v-btn
                v-if="item.status === 'COMPLETED'"
                size="small"
                color="primary"
                variant="tonal"
                @click="download(item)"
              >
                Скачать
              </v-btn>
            </template>
          </v-data-table>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { reportsApi } from '@/api/endpoints'
import { getAuthorizedBlob } from '@/api/client'
import type { ReportJob } from '@/types'

const jobs = ref<ReportJob[]>([])
const creating = ref(false)
const form = ref({ report_type: 'inventory_list', format: 'EXCEL' })

const reportTypes = [
  { title: 'Инвентарная опись', value: 'inventory_list' },
  { title: 'Ведомость по местам хранения', value: 'asset_statement' },
  { title: 'Реестр расхождений', value: 'discrepancies' },
  { title: 'Акт списания', value: 'write_off_act' },
  { title: 'Износ и остаточная стоимость', value: 'depreciation' },
]

const formatOptions = [
  { title: 'Excel', value: 'EXCEL' },
  { title: 'PDF', value: 'PDF' },
  { title: 'CSV', value: 'CSV' },
  { title: 'JSON', value: 'JSON' },
  { title: 'XML', value: 'XML' },
]

const headers = [
  { title: 'Тип', key: 'report_type' },
  { title: 'Формат', key: 'format' },
  { title: 'Статус', key: 'status' },
  { title: 'Создан', key: 'created_at' },
  { title: 'Действия', key: 'actions', sortable: false },
]

function jobColor(s: string): string {
  const map: Record<string, string> = {
    PENDING: 'grey',
    RUNNING: 'info',
    COMPLETED: 'success',
    FAILED: 'error',
  }
  return map[s] ?? 'default'
}

function formatDate(v: string): string {
  return new Date(v).toLocaleString('ru-RU')
}

async function download(job: ReportJob): Promise<void> {
  const blob = await getAuthorizedBlob(reportsApi.downloadUrl(job.id))
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const extension = job.format.toLowerCase().replace('excel', 'xlsx')
  link.href = url
  link.download = `report_${job.id}.${extension}`
  link.click()
  URL.revokeObjectURL(url)
}

async function load(): Promise<void> {
  try {
    jobs.value = await reportsApi.list()
  } catch {
    jobs.value = []
  }
}

async function createReport(): Promise<void> {
  creating.value = true
  try {
    await reportsApi.create(form.value)
    await load()
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  void load()
})

const refreshTimer = window.setInterval(() => {
  if (jobs.value.some((job) => job.status === 'PENDING' || job.status === 'RUNNING')) void load()
}, 2000)

onUnmounted(() => window.clearInterval(refreshTimer))
</script>
