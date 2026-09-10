"""E2E: поступление с основанием и расследование расхождения."""

from tests.conftest import login
from tests.helpers import create_asset, create_asset_type, create_building, create_room


async def _asset(client, headers):
    building = await create_building(client, headers)
    room = await create_room(client, headers, building["id"])
    asset_type = await create_asset_type(client, headers, "REC")
    return await create_asset(client, headers, asset_type["id"], room["id"])


async def test_receipt_requires_basis_document_to_complete(client):
    headers = await login(client, "zavhoz")
    asset = await _asset(client, headers)
    receipt = (await client.post("/operations/receipts", json={
        "receipt_type": "PURCHASE", "received_at": "2026-09-10", "asset_ids": [asset["id"]],
    }, headers=headers)).json()

    blocked = await client.post(f"/operations/receipts/{receipt['id']}/complete", headers=headers)
    assert blocked.status_code == 400

    doc = (await client.post("/documents", json={
        "doc_type": "INVOICE", "title": "Накладная", "receipt_id": receipt["id"],
    }, headers=headers)).json()
    assert doc["receipt_id"] == receipt["id"]
    done = await client.post(f"/operations/receipts/{receipt['id']}/complete", headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "APPROVED"


async def test_discrepancy_can_be_resolved_with_document_and_approved_inventory_is_locked(client):
    headers = await login(client, "zavhoz")
    asset = await _asset(client, headers)
    inv = (await client.post("/inventories", json={"name": "Проверка"}, headers=headers)).json()
    await client.post(f"/inventories/{inv['id']}/start", headers=headers)
    item = (await client.get(f"/inventories/{inv['id']}/items", headers=headers)).json()[0]
    assert item["asset_inventory_number"] == asset["inventory_number"]
    await client.patch(f"/inventories/{inv['id']}/items/{item['id']}", json={"actual_quantity": "0"}, headers=headers)
    await client.post(f"/inventories/{inv['id']}/complete", headers=headers)
    discrepancy = (await client.get(f"/inventories/{inv['id']}/discrepancies", headers=headers)).json()[0]
    doc = (await client.post("/documents", json={
        "doc_type": "EXPLANATION", "title": "Объяснительная", "discrepancy_id": discrepancy["id"],
    }, headers=headers)).json()
    update = await client.patch(f"/inventories/{inv['id']}/discrepancies/{discrepancy['id']}", json={
        "status": "RESOLVED", "explanation": "Проверено", "resolution": "Закрыто", "document_id": doc["id"],
    }, headers=headers)
    assert update.status_code == 200, update.text
    assert update.json()["document_id"] == doc["id"]
    await client.post(f"/inventories/{inv['id']}/approve", json={}, headers=headers)
    locked = await client.patch(f"/inventories/{inv['id']}/items/{item['id']}", json={"actual_quantity": "1"}, headers=headers)
    assert locked.status_code == 400
