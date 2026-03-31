from __future__ import annotations

import csv
from pathlib import Path


class RegionTreeService:
    def __init__(self) -> None:
        clean_dir = Path(__file__).resolve().parents[1] / "data" / "clean"
        self.provinces = self._load_csv(clean_dir / "provinces.csv")
        self.cities = self._load_csv(clean_dir / "cities.csv")
        self.counties = self._load_csv(clean_dir / "counties.csv")
        self.towns = self._load_csv(clean_dir / "towns.csv")

    @staticmethod
    def _load_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as file_obj:
            return [row for row in csv.DictReader(file_obj) if row.get("enabled") == "1"]

    @staticmethod
    def _matches_name(row: dict[str, str], value: str, primary_key: str, secondary_keys: tuple[str, ...]) -> bool:
        candidates = [row.get(primary_key, "").strip()]
        candidates.extend(row.get(key, "").strip() for key in secondary_keys)
        return value.strip() in {candidate for candidate in candidates if candidate}

    def _find_province(self, province: str) -> dict[str, str] | None:
        for row in self.provinces:
            if self._matches_name(row, province, "province_name", ("province_short_name", "province_alias_name")):
                return row
        return None

    def _find_city(self, province_name: str, city: str) -> dict[str, str] | None:
        for row in self.cities:
            if row["province_name"] != province_name:
                continue
            if self._matches_name(row, city, "city_name", ("city_short_name",)):
                return row
        return None

    def _find_county(self, province_name: str, city_name: str, county: str) -> dict[str, str] | None:
        for row in self.counties:
            if row["province_name"] != province_name or row["city_name"] != city_name:
                continue
            if self._matches_name(row, county, "county_name", ("county_short_name",)):
                return row
        return None

    @staticmethod
    def _province_node(row: dict[str, str], children: list[dict] | None = None) -> dict:
        return {
            "label": row["province_name"],
            "value": row["province_name"],
            "code": row["province_code"],
            "level": "province",
            "children": children or [],
        }

    @staticmethod
    def _city_node(row: dict[str, str], children: list[dict] | None = None) -> dict:
        return {
            "label": row["city_name"],
            "value": row["city_name"],
            "code": row["source_id"],
            "level": "city",
            "children": children or [],
        }

    @staticmethod
    def _county_node(row: dict[str, str], children: list[dict] | None = None) -> dict:
        return {
            "label": row["county_name"],
            "value": row["county_name"],
            "code": row["source_id"],
            "level": "county",
            "children": children or [],
        }

    @staticmethod
    def _town_node(row: dict[str, str]) -> dict:
        return {
            "label": row["town_name"],
            "value": row["town_name"],
            "code": row["source_id"],
            "level": "town",
            "children": [],
        }

    def _province_children(self, province_name: str) -> list[dict]:
        return [
            self._city_node(row)
            for row in self.cities
            if row["province_name"] == province_name
        ]

    def _city_children(self, province_name: str, city_name: str) -> list[dict]:
        return [
            self._county_node(row)
            for row in self.counties
            if row["province_name"] == province_name and row["city_name"] == city_name
        ]

    def _county_children(self, province_name: str, city_name: str, county_name: str) -> list[dict]:
        return [
            self._town_node(row)
            for row in self.towns
            if row["province_name"] == province_name
            and row["city_name"] == city_name
            and row["county_name"] == county_name
        ]

    def build_tree(
        self,
        province: str | None = None,
        city: str | None = None,
        county: str | None = None,
    ) -> dict:
        if county and (not province or not city):
            raise ValueError("`county` requires both `province` and `city`.")
        if city and not province:
            raise ValueError("`city` requires `province`.")

        if not province:
            tree = [self._province_node(row) for row in self.provinces]
            return {
                "level": "province",
                "filters": {"province": None, "city": None, "county": None},
                "tree": tree,
            }

        province_row = self._find_province(province)
        if province_row is None:
            raise LookupError(f"Province `{province}` not found.")

        province_name = province_row["province_name"]
        if not city:
            tree = [self._province_node(province_row, self._province_children(province_name))]
            return {
                "level": "city",
                "filters": {"province": province_name, "city": None, "county": None},
                "tree": tree,
            }

        city_row = self._find_city(province_name, city)
        if city_row is None:
            raise LookupError(f"City `{city}` not found under province `{province_name}`.")

        city_name = city_row["city_name"]
        if not county:
            tree = [
                self._province_node(
                    province_row,
                    [self._city_node(city_row, self._city_children(province_name, city_name))],
                )
            ]
            return {
                "level": "county",
                "filters": {"province": province_name, "city": city_name, "county": None},
                "tree": tree,
            }

        county_row = self._find_county(province_name, city_name, county)
        if county_row is None:
            raise LookupError(
                f"County `{county}` not found under province `{province_name}` and city `{city_name}`."
            )

        county_name = county_row["county_name"]
        tree = [
            self._province_node(
                province_row,
                [
                    self._city_node(
                        city_row,
                        [self._county_node(county_row, self._county_children(province_name, city_name, county_name))],
                    )
                ],
            )
        ]
        return {
            "level": "town",
            "filters": {"province": province_name, "city": city_name, "county": county_name},
            "tree": tree,
        }
