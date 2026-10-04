"""Items Prices in Future: access control, model lifecycle and pricing logic."""

from __future__ import annotations

import pytest

from app.ml import dataset

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --------------------------------------------------------------- access control
async def test_every_ipf_route_is_owner_only(client, cashier):
    assert (await client.get("/api/ipf/model", headers=cashier)).status_code == 403
    assert (await client.get("/api/ipf/forecast", headers=cashier)).status_code == 403
    assert (await client.post("/api/ipf/train", headers=cashier)).status_code == 403


async def test_every_ipf_route_requires_a_session(client):
    assert (await client.get("/api/ipf/model")).status_code == 401
    assert (await client.get("/api/ipf/forecast")).status_code == 401
    assert (await client.post("/api/ipf/train")).status_code == 401


# ------------------------------------------------------------- model lifecycle
async def test_untrained_model_reports_itself_and_blocks_forecasting(client, owner, clean_model_dir):
    status = (await client.get("/api/ipf/model", headers=owner)).json()
    assert status["trained"] is False
    assert status["mae"] is None

    forecast = await client.get("/api/ipf/forecast", headers=owner)
    assert forecast.status_code == 409
    assert "not been trained" in forecast.json()["detail"]


async def test_training_without_enough_history_is_refused(client, owner, clean_model_dir, make_product):
    await make_product()
    response = await client.post("/api/ipf/train", headers=owner)
    assert response.status_code == 409
    assert "sales" in response.json()["detail"].lower()


async def test_training_produces_a_scored_model(client, owner, clean_model_dir, sales_history):
    response = await client.post("/api/ipf/train", headers=owner)
    assert response.status_code == 201 or response.status_code == 200, response.text

    model = response.json()
    assert model["trained"] is True
    assert model["n_samples"] > 0
    assert model["n_train"] > 0 and model["n_test"] > 0
    assert model["horizon_days"] == dataset.HORIZON_DAYS
    # The honest comparison must always be reported, whichever way it falls.
    assert model["baseline_mae"] >= 0
    assert isinstance(model["beats_baseline"], bool)

    # It is persisted: a fresh status read returns the same figures.
    status = (await client.get("/api/ipf/model", headers=owner)).json()
    assert status["trained"] is True
    assert status["mae"] == model["mae"]


async def test_forecast_splits_opportunities_from_risks(client, owner, clean_model_dir, sales_history):
    await client.post("/api/ipf/train", headers=owner)
    forecast = (await client.get("/api/ipf/forecast?limit=10", headers=owner)).json()

    assert forecast["horizon_days"] == dataset.HORIZON_DAYS
    assert forecast["generated_rows"] > 0
    assert all(row["recommendation"] == "PRICE_UP" for row in forecast["opportunities"])
    assert all(row["recommendation"] == "LOSS_RISK" for row in forecast["risks"])
    assert len(forecast["opportunities"]) <= 10

    for row in forecast["opportunities"] + forecast["risks"]:
        assert row["reason"], "every suggestion must explain itself"
        assert row["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        assert row["predicted_units"] >= 0


async def test_forecast_never_suggests_a_price_above_the_market(client, owner, clean_model_dir, sales_history):
    await client.post("/api/ipf/train", headers=owner)
    forecast = (await client.get("/api/ipf/forecast?limit=50", headers=owner)).json()
    for row in forecast["opportunities"]:
        assert row["suggested_price"] <= row["market_price"] + 0.01
