import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from credit.api import create_app


@pytest.mark.parametrize(
    "kind,filename",
    [
        ("individuals", "salarie"),
        ("businesses", "pme_structuree"),
        ("individuals", "independant"),
        ("businesses", "petite_activite"),
    ],
)
def test_routes_history_restart(url, kind, filename, auth_headers):
    app = create_app(url)
    data = json.loads(Path(f"examples/{filename}.json").read_text())
    with TestClient(app, headers=auth_headers) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post(f"/{kind}", json=data)
        assert response.status_code == 201, response.text
        case_id = response.json()["id"]
        assert client.get(f"/{kind}/{case_id}").json()["data"] == response.json()["data"]
        response = client.post(f"/{kind}/{case_id}/analyses")
        assert response.status_code == 201, response.text
        analysis_id = response.json()["id"]
        historical = client.get(f"/analyses/{analysis_id}").json()
        assert historical["result"]["status"] == "complete"
        data["name"] = "Dossier modifié"
        assert client.put(f"/{kind}/{case_id}", json=data).status_code == 200
        assert client.get(f"/analyses/{analysis_id}").json() == historical
        assert client.get(f"/{kind}/{case_id}/analyses").json()[0]["id"] == analysis_id
        scenario = client.post(f"/{kind}/{case_id}/scenarios", json={"revenue_drop": "0.2"})
        assert scenario.status_code == 201
        assert client.get(f"/{kind}/absent").status_code == 404
        assert client.get("/analyses/absent").status_code == 404
        assert client.post(f"/{kind}", json={}).status_code == 422
        assert client.get("/health").headers.get("X-Request-ID")
    app.state.engine.dispose()
    restarted = create_app(url)
    with TestClient(restarted, headers=auth_headers) as client:
        assert client.get(f"/analyses/{analysis_id}").json() == historical
    restarted.state.engine.dispose()
