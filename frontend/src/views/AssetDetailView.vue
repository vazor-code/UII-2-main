<template>
  <div class="page-container">
    <v-card v-if="asset" class="asset-card" elevation="0">
      <div class="asset-header">
        <v-btn icon="mdi-arrow-left" variant="text" @click="router.back()" />
        <div class="asset-heading">
          <div class="asset-kicker">КАРТОЧКА ИМУЩЕСТВА</div>
          <h1>{{ asset.name }}</h1>
          <span>Инвентарный номер · <strong>{{ asset.inventory_number }}</strong></span>
        </div>
        <v-spacer />
        <v-chip :color="statusColor(asset.status)" variant="flat" class="status-chip">
          {{ statusLabel(asset.status) }}
        </v-chip>
      </div>

      <v-card-text class="asset-content">
        <v-row>
          <v-col cols="12" md="4" lg="3">
            <section class="photo-panel">
            <v-img
              v-if="photoUrl"
              :src="photoUrl"
              height="220"
              contain
              class="asset-photo"
            />
            <div v-else class="photo-placeholder">
              <v-icon size="42" color="blue-grey-lighten-2">mdi-image-outline</v-icon>
              <span>Фото не загружено</span>
            </div>
            <v-file-input
              v-if="auth.isZavhoz"
              class="mt-4"
              label="Загрузить фото"
              accept="image/*"
              prepend-icon="mdi-camera"
              density="compact"
              hide-details
              :loading="photoUploading"
              @update:model-value="onPhotoChange"
            />
            </section>
          </v-col>
          <v-col cols="12" md="8" lg="9">
            <div class="details-title">Основные сведения</div>
            <div class="details-grid">
              <div class="detail-item"><v-icon>mdi-package-variant</v-icon><div><span>Тип</span><strong>{{ assetTypeName }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-tag-outline</v-icon><div><span>Модель</span><strong>{{ asset.model || '—' }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-domain</v-icon><div><span>Бренд</span><strong>{{ asset.brand || '—' }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-barcode</v-icon><div><span>Серийный номер</span><strong>{{ asset.serial_number || '—' }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-currency-rub</v-icon><div><span>Стоимость</span><strong>{{ formatMoney(asset.cost) }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-counter</v-icon><div><span>Количество</span><strong>{{ formatQuantity(asset.quantity) }} {{ asset.unit || 'шт.' }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-home-outline</v-icon><div><span>Помещение</span><strong>{{ roomName || 'Не назначено' }}</strong></div></div>
              <div class="detail-item"><v-icon>mdi-calendar-outline</v-icon><div><span>Год покупки</span><strong>{{ asset.purchase_year || '—' }}</strong></div></div>
            </div>
          </v-col>
        </v-row>

        <v-divider class="my-6" />

        <div v-if="auth.isZavhoz" class="actions-panel">
          <div><div class="details-title">Действия</div><div class="text-caption text-medium-emphasis">Изменения сохраняются в журнале аудита</div></div>
          <div class="action-buttons">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-pencil" @click="openEdit">
            Изменить
          </v-btn>
          <v-btn color="info" prepend-icon="mdi-arrow-right" @click="moveDialog = true">
            Переместить
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-package-variant-plus" @click="receiptDialog = true">
            Поступление
          </v-btn>
          <v-btn color="warning" prepend-icon="mdi-wrench" @click="repairDialog = true">
            В ремонт
          </v-btn>
          <v-btn color="secondary" prepend-icon="mdi-hand-okay" @click="issueDialog = true">
            Выдать
          </v-btn>
          <v-btn color="error" prepend-icon="mdi-delete" @click="writeOffDialog = true">
            Списать
          </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-alert v-else type="info" class="mt-4">Карточка не найдена</v-alert>

    <v-dialog v-model="editDialog" max-width="520">
      <v-card>
        <v-card-title>Изменить карточку</v-card-title>
        <v-card-text>
          <v-text-field v-model="editForm.inventory_number" label="Инвентарный номер" required />
          <v-text-field v-model="editForm.name" label="Наименование" required />
          <v-text-field v-model="editForm.model" label="Модель" />
          <v-text-field v-model="editForm.brand" label="Бренд" />
          <v-text-field v-model="editForm.serial_number" label="Серийный номер" />
          <v-text-field v-model.number="editForm.cost" label="Стоимость" type="number" />
          <v-text-field v-model.number="editForm.quantity" label="Количество" type="number" />
          <v-select v-model="editForm.room_id" :items="rooms" item-title="name" item-value="id" label="Помещение" clearable />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="editDialog = false">Отмена</v-btn><v-btn color="primary" :loading="busy" @click="saveEdit">Сохранить</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог перемещения -->
    <v-dialog v-model="moveDialog" max-width="500">
      <v-card>
        <v-card-title>Перемещение</v-card-title>
        <v-card-text>
          <v-select
            v-model="moveToRoomId"
            :items="rooms"
            item-title="name"
            item-value="id"
            label="Помещение назначения"
          />
          <v-text-field v-model="moveReason" label="Причина" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="moveDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="busy" @click="doMove">Переместить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="receiptDialog" max-width="500">
      <v-card>
        <v-card-title>Оформить поступление</v-card-title>
        <v-card-text>
          <v-select v-model="receiptForm.receipt_type" :items="receiptTypes" item-title="title" item-value="value" label="Вид поступления" />
          <v-text-field v-model="receiptForm.received_at" type="date" label="Дата" />
          <v-text-field v-model="receiptForm.counterparty" label="Поставщик / передающая сторона" />
          <v-text-field v-model="receiptForm.basis_number" label="Номер основания" />
          <v-textarea v-model="receiptForm.comment" label="Комментарий" />
          <v-alert type="info" density="compact">Для завершения поступления добавьте договор, накладную или акт в разделе документов.</v-alert>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn text @click="receiptDialog = false">Отмена</v-btn><v-btn color="primary" :loading="busy" @click="createReceipt">Создать</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог ремонта -->
    <v-dialog v-model="repairDialog" max-width="500">
      <v-card>
        <v-card-title>В ремонт</v-card-title>
        <v-card-text>
          <v-text-field v-model="repairForm.contractor" label="Подрядчик" />
          <v-text-field v-model="repairForm.description" label="Описание" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="repairDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="busy" @click="doRepair">Направить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог выдачи -->
    <v-dialog v-model="issueDialog" max-width="500">
      <v-card>
        <v-card-title>Выдача</v-card-title>
        <v-card-text>
          <v-select
            v-model="issueToId"
            :items="users"
            item-title="full_name"
            item-value="id"
            label="Кому"
          />
          <v-text-field v-model="issueReason" label="Причина" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="issueDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="busy" @click="doIssue">Выдать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог списания -->
    <v-dialog v-model="writeOffDialog" max-width="500">
      <v-card>
        <v-card-title>Списание</v-card-title>
        <v-card-text>
          <v-textarea v-model="writeOffReason" label="Причина" required />
          <v-text-field v-model="writeOffCommission" label="Состав комиссии" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn text @click="writeOffDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="busy" @click="doWriteOff">Списать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getAuthorizedBlob } from '@/api/client'
import { assetsApi, receiptsApi, referenceApi, structureApi, usersApi } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import type { Asset, AssetType, Room, User } from '@/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const asset = ref<Asset | null>(null)
const assetTypes = ref<AssetType[]>([])
const rooms = ref<Room[]>([])
const users = ref<User[]>([])
const busy = ref(false)

const photoUrl = ref<string | null>(null)
const photoUploading = ref(false)

const moveDialog = ref(false)
const repairDialog = ref(false)
const issueDialog = ref(false)
const writeOffDialog = ref(false)
const receiptDialog = ref(false)
const editDialog = ref(false)

const moveToRoomId = ref<string | null>(null)
const moveReason = ref('')
const repairForm = ref({ contractor: '', description: '' })
const issueToId = ref<string | null>(null)
const issueReason = ref('')
const writeOffReason = ref('')
const writeOffCommission = ref('')
const receiptForm = ref({ receipt_type: 'PURCHASE', received_at: new Date().toISOString().slice(0, 10), counterparty: '', basis_number: '', comment: '' })
const editForm = ref({ inventory_number: '', name: '', model: '', brand: '', serial_number: '', cost: null as number | null, quantity: 1, room_id: null as string | null })
const receiptTypes = [
  { title: 'Закупка', value: 'PURCHASE' }, { title: 'Безвозмездная передача', value: 'GRANT' },
  { title: 'Дарение', value: 'GIFT' }, { title: 'Передача от муниципалитета', value: 'MUNICIPAL_TRANSFER' },
]

const assetTypeName = computed(
  () => assetTypes.value.find((t) => t.id === asset.value?.asset_type_id)?.name ?? '—',
)
const roomName = computed(
  () => rooms.value.find((r) => r.id === asset.value?.room_id)?.name ?? null,
)

const statusOptions = [
  { title: 'На учёте', value: 'IN_STOCK' },
  { title: 'Перемещено', value: 'MOVED' },
  { title: 'В ремонте', value: 'ON_REPAIR' },
  { title: 'Выдано', value: 'ISSUED' },
  { title: 'Списано', value: 'WRITTEN_OFF' },
  { title: 'Зарезервировано', value: 'RESERVED' },
]

function statusLabel(s: string): string {
  return statusOptions.find((o) => o.value === s)?.title ?? s
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    IN_STOCK: 'success',
    MOVED: 'info',
    ON_REPAIR: 'warning',
    ISSUED: 'secondary',
    WRITTEN_OFF: 'error',
    RESERVED: 'grey',
  }
  return map[s] ?? 'default'
}

function formatMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' }).format(v)
}

function formatQuantity(v: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(v)
}

async function loadAsset(): Promise<void> {
  try {
    asset.value = await assetsApi.get(String(route.params.id))
  } catch {
    asset.value = null
  }
  await loadPhoto()
}

async function loadPhoto(): Promise<void> {
  if (photoUrl.value) URL.revokeObjectURL(photoUrl.value)
  photoUrl.value = null
  if (!asset.value?.photo_path) return
  try {
    const blob = await getAuthorizedBlob(`/assets/${asset.value.id}/photo`)
    photoUrl.value = URL.createObjectURL(blob)
  } catch {
    photoUrl.value = null
  }
}

async function onPhotoChange(value: File | File[] | null | undefined): Promise<void> {
  const file = Array.isArray(value) ? value[0] : value
  if (!asset.value || !file) return
  photoUploading.value = true
  try {
    await assetsApi.uploadPhoto(asset.value.id, file)
    await loadAsset()
  } finally {
    photoUploading.value = false
  }
}

async function doMove(): Promise<void> {
  if (!asset.value) return
  busy.value = true
  try {
    await assetsApi.createMove({
      asset_id: asset.value.id,
      to_room_id: moveToRoomId.value,
      reason: moveReason.value || undefined,
    })
    moveDialog.value = false
    await loadAsset()
  } finally {
    busy.value = false
  }
}

function openEdit(): void {
  if (!asset.value) return
  editForm.value = {
    inventory_number: asset.value.inventory_number,
    name: asset.value.name,
    model: asset.value.model ?? '',
    brand: asset.value.brand ?? '',
    serial_number: asset.value.serial_number ?? '',
    cost: asset.value.cost,
    quantity: asset.value.quantity,
    room_id: asset.value.room_id,
  }
  editDialog.value = true
}

async function saveEdit(): Promise<void> {
  if (!asset.value || !editForm.value.inventory_number || !editForm.value.name) return
  busy.value = true
  try {
    await assetsApi.update(asset.value.id, {
      ...editForm.value,
      model: editForm.value.model || null,
      brand: editForm.value.brand || null,
      serial_number: editForm.value.serial_number || null,
    })
    editDialog.value = false
    await loadAsset()
  } finally {
    busy.value = false
  }
}

async function createReceipt(): Promise<void> {
  if (!asset.value) return
  busy.value = true
  try {
    await receiptsApi.create({ ...receiptForm.value, asset_ids: [asset.value.id] })
    receiptDialog.value = false
  } finally {
    busy.value = false
  }
}

async function doRepair(): Promise<void> {
  if (!asset.value) return
  busy.value = true
  try {
    await assetsApi.createRepair({
      asset_id: asset.value.id,
      contractor: repairForm.value.contractor || null,
      description: repairForm.value.description || undefined,
    })
    repairDialog.value = false
    await loadAsset()
  } finally {
    busy.value = false
  }
}

async function doIssue(): Promise<void> {
  if (!asset.value || !issueToId.value) return
  busy.value = true
  try {
    await assetsApi.createIssuance({
      asset_id: asset.value.id,
      issued_to_id: issueToId.value,
      reason: issueReason.value || undefined,
    })
    issueDialog.value = false
    await loadAsset()
  } finally {
    busy.value = false
  }
}

async function doWriteOff(): Promise<void> {
  if (!asset.value || !writeOffReason.value) return
  busy.value = true
  try {
    await assetsApi.createWriteOff({
      asset_id: asset.value.id,
      reason: writeOffReason.value,
      commission_members: writeOffCommission.value || null,
    })
    writeOffDialog.value = false
    await loadAsset()
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await loadAsset()
  try {
    assetTypes.value = await referenceApi.assetTypes()
  } catch {
    assetTypes.value = []
  }
  try {
    rooms.value = await structureApi.rooms()
  } catch {
    rooms.value = []
  }
  try {
    users.value = await usersApi.listActive()
  } catch {
    users.value = []
  }
})
</script>

<style scoped>
.asset-card { border: 1px solid #e5eaf0; border-radius: 16px; overflow: hidden; background: #fff; }
.asset-header { display: flex; align-items: center; gap: 14px; padding: 24px 28px; background: linear-gradient(135deg, #f7fbff, #fff); border-bottom: 1px solid #e8eef5; }
.asset-heading h1 { margin: 2px 0 3px; font-size: 25px; line-height: 1.2; font-weight: 650; color: #172b4d; }
.asset-heading span { color: #718096; font-size: 14px; }.asset-kicker { color: #1976d2; font-weight: 700; font-size: 11px; letter-spacing: .09em; }.status-chip { font-weight: 600; }.asset-content { padding: 28px !important; }
.photo-panel { padding: 14px; border: 1px solid #e5eaf0; border-radius: 12px; background: #fafcff; }.asset-photo { border-radius: 8px; background: #fff; }.photo-placeholder { height: 220px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #8391a5; border: 1px dashed #c8d4e3; border-radius: 8px; background: #fff; }
.details-title { font-size: 16px; font-weight: 700; color: #203a5f; margin-bottom: 16px; }.details-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.detail-item { display: flex; gap: 12px; align-items: center; min-height: 76px; padding: 14px; border: 1px solid #e6edf5; border-radius: 10px; background: #fff; }.detail-item > .v-icon { color: #1976d2; background: #eaf4ff; padding: 9px; border-radius: 8px; }.detail-item span { display: block; color: #718096; font-size: 12px; margin-bottom: 3px; }.detail-item strong { display: block; color: #243b53; font-size: 14px; font-weight: 600; }.actions-panel { display: flex; align-items: center; justify-content: space-between; gap: 18px; }.actions-panel .details-title { margin-bottom: 2px; }.action-buttons { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
@media (max-width: 700px) { .asset-header { padding: 16px; align-items: flex-start; }.asset-heading h1 { font-size: 20px; }.status-chip { margin-top: 4px; }.asset-content { padding: 16px !important; }.details-grid { grid-template-columns: 1fr; }.actions-panel { align-items: flex-start; flex-direction: column; }.action-buttons { justify-content: flex-start; }.action-buttons .v-btn { flex: 1 1 auto; } }
</style>
