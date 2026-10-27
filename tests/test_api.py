from fastapi.testclient import TestClient

from chemlab.api import create_app
from chemlab.registry import Registry


def test_web_application_runs_the_real_pipeline(lab):
    store, config, *_ = lab
    registry = Registry(store)
    registry.register("generator", "model_manifest", config.backward_manifest)
    registry.register("checker", "model_manifest", config.forward_manifest)
    registry.register("stock", "stock", config.stock_ref)
    with TestClient(create_app(store.root)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["identity"] == "identity-v1"
        assert len(client.get("/api/registry").json()) == 3
        response = client.post(
            "/api/runs", json={"target": "CCOC(C)=O", "config": config.model_dump(mode="json")}
        )
        assert response.status_code == 202
        run_id = response.json()["id"]
        app = client.app.state.application
        # Wait on the actual worker lock, without substituting a fake search service.
        import time

        for _ in range(500):
            row = app.run(run_id)
            if row["state"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        assert row["state"] == "complete", row
        result = client.get(f"/api/runs/{run_id}")
        assert result.status_code == 200
        assert len(result.json()["result"]["groups"]["verified_consistent"]) == 1
        assert client.get(f"/api/runs/{run_id}/bundle").headers["content-type"] == "application/zip"
        assert client.get("/api/molecule.svg", params={"smiles": "CCO"}).status_code == 200


def test_api_rejects_bad_inputs_and_cross_origin_writes(tmp_path):
    with TestClient(create_app(tmp_path / "store")) as client:
        assert client.get("/api/molecule.svg", params={"smiles": "invalid"}).status_code == 400
        assert client.get("/api/runs/missing").status_code == 404
        assert (
            client.post(
                "/api/stocks", json={}, headers={"Origin": "https://unrelated.example"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/stocks",
                json={"alias": "bad", "smiles": ["invalid"], "source": "test", "license": "test"},
            ).status_code
            == 400
        )
