from app.api import app


def test_parse_returns_code_and_data_wrapper() -> None:
    client = app.test_client()
    response = client.post(
        "/api/v1/parse",
        json={"text": "北京市朝阳区酒仙桥东路1号m3c大厦A座1101室 王先生13511112222"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    assert "data" in payload
    assert payload["data"]["person"]["name"] == "王先生"
    assert payload["data"]["address"]["county"] == "朝阳区"


def test_parse_returns_400_for_empty_text() -> None:
    client = app.test_client()
    response = client.post("/api/v1/parse", json={"text": ""})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == 400
    assert "`text` must be a non-empty string" in payload["error"]


def test_regions_tree_returns_province_roots() -> None:
    client = app.test_client()
    response = client.get("/api/v1/regions/tree")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    assert payload["level"] == "province"
    assert any(node["value"] == "北京市" for node in payload["tree"])


def test_regions_tree_returns_city_children_by_province() -> None:
    client = app.test_client()
    response = client.get("/api/v1/regions/tree", query_string={"province": "上海市"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    assert payload["level"] == "city"
    assert payload["tree"][0]["value"] == "上海市"
    assert any(child["value"] == "上海市" for child in payload["tree"][0]["children"])


def test_regions_tree_returns_county_children_by_city() -> None:
    client = app.test_client()
    response = client.get(
        "/api/v1/regions/tree",
        query_string={"province": "上海市", "city": "上海市"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    city_node = payload["tree"][0]["children"][0]
    assert payload["level"] == "county"
    assert city_node["value"] == "上海市"
    assert any(child["value"] == "青浦区" for child in city_node["children"])


def test_regions_tree_returns_town_children_by_county() -> None:
    client = app.test_client()
    response = client.get(
        "/api/v1/regions/tree",
        query_string={"province": "上海市", "city": "上海市", "county": "青浦区"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    county_node = payload["tree"][0]["children"][0]["children"][0]
    assert payload["level"] == "town"
    assert county_node["value"] == "青浦区"
    assert any(child["value"] == "徐泾镇" for child in county_node["children"])


def test_regions_tree_trims_wrapped_quotes_in_query_values() -> None:
    client = app.test_client()
    response = client.get(
        "/api/v1/regions/tree",
        query_string={"province": "\"上海市\"", "city": "上海市", "county": "青浦区\""},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == 200
    assert payload["filters"]["county"] == "青浦区"


def test_regions_tree_rejects_city_without_province() -> None:
    client = app.test_client()
    response = client.get("/api/v1/regions/tree", query_string={"city": "上海市"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == 400
    assert "requires `province`" in payload["error"]


def test_regions_tree_returns_400_for_unknown_province() -> None:
    client = app.test_client()
    response = client.get("/api/v1/regions/tree", query_string={"province": "不存在省份"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == 400
