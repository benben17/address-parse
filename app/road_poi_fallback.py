from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoadPOIMatch:
    kind: str
    keyword: str
    province: str
    city: str | None
    county: str | None
    town: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "keyword": self.keyword,
            "province": self.province,
            "city": self.city,
            "county": self.county,
            "town": self.town,
        }


ROAD_POI_ENTRIES = (
    RoadPOIMatch(kind="road", keyword="虹漕路", province="上海市", city="上海市", county="徐汇区"),
    RoadPOIMatch(kind="road", keyword="漕溪北路", province="上海市", city="上海市", county="徐汇区"),
    RoadPOIMatch(kind="road", keyword="酒仙桥东路", province="北京市", city="北京市", county="朝阳区"),
    RoadPOIMatch(kind="road", keyword="体育西路", province="广东省", city="广州市", county="天河区"),
    RoadPOIMatch(kind="road", keyword="科苑路", province="广东省", city="深圳市", county="南山区"),
    RoadPOIMatch(kind="poi", keyword="望京SOHO", province="北京市", city="北京市", county="朝阳区"),
    RoadPOIMatch(kind="town", keyword="徐泾镇", province="上海市", city="上海市", county="青浦区", town="徐泾镇"),
)


class RoadPOIFallbackIndex:
    def __init__(self) -> None:
        self.entries = ROAD_POI_ENTRIES

    def match(
        self,
        text: str,
        province: str | None = None,
        city: str | None = None,
    ) -> RoadPOIMatch | None:
        candidates = []
        for entry in self.entries:
            if entry.keyword not in text:
                continue
            if province and entry.province != province:
                continue
            if city and entry.city and entry.city != city:
                continue
            candidates.append(entry)

        if not candidates:
            return None

        max_len = max(len(entry.keyword) for entry in candidates)
        top_candidates = [entry for entry in candidates if len(entry.keyword) == max_len]
        unique_paths = {
            (entry.province, entry.city, entry.county, entry.town): entry for entry in top_candidates
        }
        if len(unique_paths) != 1:
            return None
        return next(iter(unique_paths.values()))
