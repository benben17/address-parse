from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


TOWN_SUFFIXES = (
    "街道办事处",
    "民族乡",
    "苏木乡",
    "街道",
    "苏木",
    "镇",
    "乡",
)
ADDRESS_CUE_TOKENS = (
    "路",
    "街",
    "巷",
    "号",
    "栋",
    "幢",
    "单元",
    "室",
    "村",
    "社区",
    "小区",
    "大道",
    "大街",
    "里",
    "弄",
    "桥",
    "园",
    "苑",
    "座",
    "厦",
    "广场",
    "花园",
)
JOINED_ROAD_NAME_PREFIXES = (
    "东路",
    "西路",
    "南路",
    "北路",
    "中路",
    "东街",
    "西街",
    "南街",
    "北街",
    "中街",
)
TOWN_NAME_OVERRIDES = {
    ("重庆市", "重庆市", "忠县", "忠州镇"): ("忠州街道", "忠州"),
}


@dataclass(frozen=True)
class TownRecord:
    province: str
    city: str
    county: str
    name: str
    alias: str | None
    suffix: str | None


@dataclass(frozen=True)
class TownMatch:
    record: TownRecord
    matched_text: str
    method: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.record.name,
            "alias": self.record.alias,
            "method": self.method,
            "matched_text": self.matched_text,
        }


class TownIndex:
    def __init__(self) -> None:
        self.records_by_county: dict[tuple[str, str, str], list[TownRecord]] = defaultdict(list)
        self.alias_map_by_county: dict[tuple[str, str, str], dict[str, list[TownRecord]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._load()

    def _load(self) -> None:
        clean_path = Path(__file__).resolve().parents[1] / "data" / "clean" / "towns.csv"
        with clean_path.open(encoding="utf-8", newline="") as file_obj:
            for row in csv.DictReader(file_obj):
                override = TOWN_NAME_OVERRIDES.get(
                    (row["province_name"], row["city_name"], row["county_name"], row["town_name"])
                )
                if row.get("enabled") != "1" and override is None:
                    continue
                town_name = override[0] if override else row["town_name"]
                alias = override[1] if override else (row["town_short_name"].strip() or None)
                if alias == town_name:
                    alias = None
                suffix = self._derive_alias(town_name)[1]
                record = TownRecord(
                    province=row["province_name"],
                    city=row["city_name"],
                    county=row["county_name"],
                    name=town_name,
                    alias=alias,
                    suffix=suffix,
                )
                county_key = (record.province, record.city, record.county)
                self.records_by_county[county_key].append(record)
                if alias:
                    self.alias_map_by_county[county_key][alias].append(record)

    @staticmethod
    def _derive_alias(town_name: str) -> tuple[str | None, str | None]:
        for suffix in TOWN_SUFFIXES:
            if town_name.endswith(suffix) and len(town_name) > len(suffix):
                alias = town_name[: -len(suffix)]
                if len(alias) >= 2:
                    return alias, suffix
        return None, None

    def match(
        self,
        province: str | None,
        city: str | None,
        county: str | None,
        detail: str | None,
    ) -> TownMatch | None:
        if not province or not city or not county or not detail:
            return None

        county_key = (province, city, county)
        detail = detail.strip()
        if not detail:
            return None

        for record in self.records_by_county.get(county_key, []):
            if detail.startswith(record.name):
                return TownMatch(record=record, matched_text=record.name, method="full")

        alias_candidates = []
        for alias, records in self.alias_map_by_county.get(county_key, {}).items():
            if len(records) != 1:
                continue
            if not detail.startswith(alias):
                continue
            remainder = detail[len(alias):].strip()
            if self._looks_like_joined_road_name(remainder):
                continue
            if not self._has_address_cue(remainder):
                continue
            alias_candidates.append((len(alias), records[0]))

        if not alias_candidates:
            return None

        alias_candidates.sort(key=lambda item: item[0], reverse=True)
        best_record = alias_candidates[0][1]
        return TownMatch(record=best_record, matched_text=best_record.alias or "", method="alias")

    @staticmethod
    def _has_address_cue(remainder: str) -> bool:
        if not remainder:
            return False
        window = remainder[:8]
        return any(token in window for token in ADDRESS_CUE_TOKENS)

    @staticmethod
    def _looks_like_joined_road_name(remainder: str) -> bool:
        if not remainder:
            return False
        return remainder.startswith(JOINED_ROAD_NAME_PREFIXES)
