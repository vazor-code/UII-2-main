<template>
  <div class="page-container">
    <v-card>
      <v-card-title class="d-flex align-center">
        Типы имущества
        <v-spacer />
        <v-btn v-if="auth.isAdmin" color="primary" prepend-icon="mdi-plus" @click="openCreate">
          Добавить тип
        </v-btn>
      </v-card-title>
      <v-card-text>
        <v-alert v-if="!types.length" type="info" variant="tonal">
          Типов пока нет. Добавьте, например, «Компьютер».
        </v-alert>
        <v-data-table v-else :headers="headers" :items="types" density="compact" item-value="id">
          <template #[`item.actions`]="{ item }">
            <v-btn v-if="auth.isAdmin" size="small" variant="tonal" @click="openEdit(item)">Изменить</v-btn>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <v-dialog v-model="dialog" max-width="520">
      <v-card>
        <v-card-title>{{ editing ? 'Изменить тип имущества' : 'Новый тип имущества' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Название" required />
          <v-text-field v-model="form.code" label="Код" hint="Например: COMPUTER" persistent-hint required />
          <v-text-field v-model="form.number_template" label="Шаблон инвентарного номера" hint="Например: {Год}-{Тип}-{№}" persistent-hint />
          <v-textarea v-model="form.description" label="Описание" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :disabled="!form.name || !form.code" :loading="saving" @click="save">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { referenceApi } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import type { AssetType } from '@/types'

const auth = useAuthStore()
const types = ref<AssetType[]>([])
const dialog = ref(false)
const saving = ref(false)
const editing = ref<AssetType | null>(null)
const form = ref({ name: '', code: '', number_template: '', description: '' })
const headers = [
  { title: 'Название', key: 'name' },
  { title: 'Код', key: 'code' },
  { title: 'Шаблон номера', key: 'number_template' },
  { title: 'Описание', key: 'description' },
  { title: '', key: 'actions', sortable: false },
]

async function load(): Promise<void> {
  types.value = await referenceApi.assetTypes()
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      code: form.value.code.trim().toUpperCase(),
      number_template: form.value.number_template.trim() || null,
      description: form.value.description.trim() || null,
    }
    if (editing.value) await referenceApi.updateAssetType(editing.value.id, payload)
    else await referenceApi.createAssetType(payload)
    form.value = { name: '', code: '', number_template: '', description: '' }
    editing.value = null
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function openEdit(type: AssetType): void {
  editing.value = type
  form.value = {
    name: type.name,
    code: type.code,
    number_template: type.number_template ?? '',
    description: type.description ?? '',
  }
  dialog.value = true
}

function openCreate(): void {
  editing.value = null
  form.value = { name: '', code: '', number_template: '', description: '' }
  dialog.value = true
}

onMounted(() => { void load() })
</script>
