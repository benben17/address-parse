from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import ahocorasick
from pypinyin import lazy_pinyin


DIRECT_ADMIN_PROVINCES = {"北京市", "上海市", "天津市", "重庆市"}
PLACEHOLDER_CITY_NAMES = {
    "市辖区",
    "县",
    "省直辖县级行政区划",
    "自治区直辖县级行政区划",
}
CITY_SUFFIXES = (
    "特别行政区",
    "自治州",
    "地区",
    "盟",
    "市",
)
COUNTY_SUFFIXES = (
    "自治县",
    "自治旗",
    "矿区",
    "林区",
    "特区",
    "新区",
    "区",
    "县",
    "旗",
    "市",
)


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
        self.fuzzy_variants_by_key: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.pinyin_index_by_rank: dict[str, dict[str, list[AdminRecord]]] = {
            "city": defaultdict(list),
            "county": defaultdict(list),
        }
        self._load()
        self._build_matcher()
        self._build_pinyin_index()

    def _load(self) -> None:
        clean_dir = Path(__file__).resolve().parents[1] / "data" / "clean"
        province_path = clean_dir / "provinces.csv"
        city_path = clean_dir / "cities.csv"
        county_path = clean_dir / "counties.csv"

        with province_path.open(encoding="utf-8", newline="") as file_obj:
            province_rows = list(csv.DictReader(file_obj))
        with city_path.open(encoding="utf-8", newline="") as file_obj:
            city_rows = list(csv.DictReader(file_obj))
        with county_path.open(encoding="utf-8", newline="") as file_obj:
            county_rows = list(csv.DictReader(file_obj))

        for row in province_rows:
            if row.get("enabled") != "1":
                continue
            self._add_record(
                AdminRecord(
                    adcode=row["province_code"],
                    name=row["province_name"],
                    rank="province",
                    province=row["province_name"],
                    city=None,
                    county=None,
                )
            )

        for row in city_rows:
            if row.get("enabled") != "1":
                continue
            city_name = self._normalize_city_name(row["province_name"], row["city_name"])
            self._add_record(
                AdminRecord(
                    adcode=row["source_id"],
                    name=city_name,
                    rank="city",
                    province=row["province_name"],
                    city=city_name,
                    county=None,
                )
            )

        for row in county_rows:
            if row.get("enabled") != "1":
                continue
            city_name = self._normalize_city_name(row["province_name"], row["city_name"])
            self._add_record(
                AdminRecord(
                    adcode=row["source_id"],
                    name=row["county_name"],
                    rank="county",
                    province=row["province_name"],
                    city=city_name,
                    county=row["county_name"],
                )
            )

    def _add_record(self, record: AdminRecord) -> None:
        self.records_by_rank_name[record.rank][record.name].append(record)
        self.records_by_name[record.name].append(record)
        if record.rank == "county" and record.city is not None:
            self.counties_by_city[(record.province, record.city)].append(record)
            self.counties_by_province[record.province].append(record)

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

    def _build_pinyin_index(self) -> None:
        for rank in ("city", "county"):
            for records in self.records_by_rank_name[rank].values():
                for record in records:
                    key = (rank, record.adcode)
                    variants = []
                    seen = set()
                    for variant in self._name_variants(self._display_name(rank, record), rank):
                        pinyin = self._to_pinyin(variant)
                        if not pinyin or (variant, pinyin) in seen:
                            continue
                        seen.add((variant, pinyin))
                        variants.append((variant, pinyin))
                        self.pinyin_index_by_rank[rank][pinyin].append(record)
                    self.fuzzy_variants_by_key[key] = variants

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

    @staticmethod
    def _display_name(rank: str, record: AdminRecord) -> str | None:
        if rank == "county":
            return record.county
        if rank == "city":
            return record.city
        return None

    @staticmethod
    def _to_pinyin(text: str) -> str:
        return "".join(lazy_pinyin(text))

    @staticmethod
    def _name_variants(name: str | None, rank: str) -> list[str]:
        if not name:
            return []
        variants = [name]
        suffixes = CITY_SUFFIXES if rank == "city" else COUNTY_SUFFIXES
        for suffix in suffixes:
            if name.endswith(suffix) and len(name) > len(suffix):
                stripped = name[: -len(suffix)]
                if len(stripped) >= 2:
                    variants.append(stripped)
                break
        return variants

    def fuzzy_match(
        self,
        rank: str,
        fragment: str,
        province: str | None = None,
        city: str | None = None,
        min_ratio: float = 0.80,
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

        if rank == "city" and province is None and len(fragment) < 3:
            return None

        fragment_pinyin = self._to_pinyin(fragment)

        # Pre-filter candidates by pinyin prefix match (issue #6)
        # Only do expensive SequenceMatcher on candidates whose pinyin shares
        # a common prefix with the fragment pinyin.
        pinyin_candidates: set[str] = set()
        if fragment_pinyin:
            for key, records in self.pinyin_index_by_rank.get(rank, {}).items():
                if key and (key.startswith(fragment_pinyin[:2]) or fragment_pinyin.startswith(key[:2])):
                    for rec in records:
                        pinyin_candidates.add(rec.adcode)
        # If pinyin pre-filter found nothing or too few, fall back to all candidates
        if len(pinyin_candidates) >= 3:
            filtered = [c for c in candidates if c.adcode in pinyin_candidates]
            if filtered:
                candidates = filtered

        best_record = None
        best_score = 0.0
        second_best = 0.0

        for candidate in candidates:
            candidate_variants = self.fuzzy_variants_by_key.get((rank, candidate.adcode), [])
            if not candidate_variants:
                continue
            score = 0.0
            for candidate_name, candidate_pinyin in candidate_variants:
                char_score = SequenceMatcher(None, fragment, candidate_name).ratio()
                pinyin_score = SequenceMatcher(None, fragment_pinyin, candidate_pinyin).ratio()
                variant_score = 0.58 * char_score + 0.42 * pinyin_score
                if len(fragment) == len(candidate_name):
                    variant_score += 0.04
                if fragment[-1] == candidate_name[-1]:
                    variant_score += 0.04
                if fragment_pinyin == candidate_pinyin:
                    variant_score += 0.06
                score = max(score, variant_score)
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
