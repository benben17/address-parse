from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib import resources

import ahocorasick


DIRECT_ADMIN_PROVINCES = {"北京市", "上海市", "天津市", "重庆市"}
PLACEHOLDER_CITY_NAMES = {
    "市辖区",
    "县",
    "省直辖县级行政区划",
    "自治区直辖县级行政区划",
}


@dataclass(frozen=True)
class AdminRecord:
    adcode: str
    name: str
    rank: str
    province: str
    city: str | None
    county: str | None

    def to_path(self) -> dict[str, str | None]:
        return {
            "adcode": self.adcode,
            "province": self.province,
            "city": self.city,
            "county": self.county,
        }


class AdminIndex:
    def __init__(self) -> None:
        self.records_by_rank_name: dict[str, dict[str, list[AdminRecord]]] = {
            "province": defaultdict(list),
            "city": defaultdict(list),
            "county": defaultdict(list),
        }
        self.records_by_name: dict[str, list[AdminRecord]] = defaultdict(list)
        self.counties_by_city: dict[tuple[str, str], list[AdminRecord]] = defaultdict(list)
        self.counties_by_province: dict[str, list[AdminRecord]] = defaultdict(list)
        self._load()
        self._build_matcher()

    def _load(self) -> None:
        with resources.as_file(resources.files("cpca.resources").joinpath("adcodes.csv")) as csv_path:
            with csv_path.open(encoding="utf-8") as file_obj:
                rows = list(csv.DictReader(file_obj))

        name_by_adcode = {row["adcode"][:6]: row["name"] for row in rows}

        for row in rows:
            adcode = row["adcode"][:6]
            name = row["name"]
            if adcode.endswith("0000"):
                rank = "province"
                province = name
                city = None
                county = None
            elif adcode.endswith("00"):
                rank = "city"
                province = name_by_adcode[f"{adcode[:2]}0000"]
                city = self._normalize_city_name(province, name)
                county = None
            else:
                rank = "county"
                province = name_by_adcode[f"{adcode[:2]}0000"]
                raw_city = name_by_adcode.get(f"{adcode[:4]}00")
                city = self._normalize_city_name(province, raw_city)
                county = name

            record = AdminRecord(
                adcode=adcode,
                name=name,
                rank=rank,
                province=province,
                city=city,
                county=county,
            )
            self.records_by_rank_name[rank][name].append(record)
            self.records_by_name[name].append(record)
            if rank == "county" and city is not None:
                self.counties_by_city[(province, city)].append(record)
                self.counties_by_province[province].append(record)

    @staticmethod
    def _normalize_city_name(province: str, city: str | None) -> str | None:
        if city is None:
            return None
        if province in DIRECT_ADMIN_PROVINCES and city in PLACEHOLDER_CITY_NAMES:
            return province
        if city in PLACEHOLDER_CITY_NAMES:
            return province
        return city

    def _build_matcher(self) -> None:
        self.matcher = ahocorasick.Automaton()
        for name in self.records_by_name:
            self.matcher.add_word(name, name)
        self.matcher.make_automaton()

    def find_exact_mentions(self, text: str) -> dict[str, list[AdminRecord]]:
        mentions = {
            "province": [],
            "city": [],
            "county": [],
        }
        seen = set()
        for _, name in self.matcher.iter(text):
            for record in self.records_by_name[name]:
                key = (record.rank, record.adcode)
                if key in seen:
                    continue
                seen.add(key)
                mentions[record.rank].append(record)
        return mentions

    def match_path(
        self,
        province: str | None = None,
        city: str | None = None,
        county: str | None = None,
    ) -> AdminRecord | None:
        if county:
            candidates = list(self.records_by_rank_name["county"].get(county, []))
            if province:
                candidates = [item for item in candidates if item.province == province]
            if city:
                candidates = [item for item in candidates if item.city == city]
            if len(candidates) == 1:
                return candidates[0]
            if not province and not city and len(self.records_by_rank_name["county"].get(county, [])) == 1:
                return self.records_by_rank_name["county"][county][0]
            return None

        if city:
            candidates = list(self.records_by_rank_name["city"].get(city, []))
            if province:
                candidates = [item for item in candidates if item.province == province]
            if len(candidates) == 1:
                return candidates[0]
            return None

        if province:
            candidates = list(self.records_by_rank_name["province"].get(province, []))
            if len(candidates) == 1:
                return candidates[0]
        return None

    def county_candidates(self, county_name: str) -> list[AdminRecord]:
        return list(self.records_by_rank_name["county"].get(county_name, []))

    def city_candidates(self, city_name: str) -> list[AdminRecord]:
        return list(self.records_by_rank_name["city"].get(city_name, []))

    def fuzzy_match(
        self,
        rank: str,
        fragment: str,
        province: str | None = None,
        city: str | None = None,
        min_ratio: float = 0.66,
    ) -> AdminRecord | None:
        fragment = fragment.strip()
        if len(fragment) < 2:
            return None

        if rank == "county":
            if province and city:
                candidates = self.counties_by_city.get((province, city), [])
            elif province:
                candidates = self.counties_by_province.get(province, [])
            else:
                candidates = []
        elif rank == "city":
            candidates = []
            for name, records in self.records_by_rank_name["city"].items():
                if province:
                    candidates.extend([record for record in records if record.province == province])
                else:
                    candidates.extend(records)
        else:
            candidates = []

        if not candidates:
            return None

        best_record = None
        best_score = 0.0
        second_best = 0.0

        for candidate in candidates:
            if rank == "county":
                candidate_name = candidate.county
            else:
                candidate_name = candidate.city
            if not candidate_name:
                continue
            score = SequenceMatcher(None, fragment, candidate_name).ratio()
            if len(fragment) == len(candidate_name):
                score += 0.04
            if fragment[-1] == candidate_name[-1]:
                score += 0.04
            if score > best_score:
                second_best = best_score
                best_score = score
                best_record = candidate
            elif score > second_best:
                second_best = score

        if best_record is None:
            return None
        if best_score < min_ratio or best_score - second_best < 0.08:
            return None
        return best_record
