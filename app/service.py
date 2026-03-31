from __future__ import annotations

import contextlib
import io
import re
from difflib import SequenceMatcher

import cpca
import pandas as pd

from .admin_index import AdminIndex, AdminRecord
from .road_poi_fallback import RoadPOIFallbackIndex, RoadPOIMatch
from .town_index import TownIndex, TownMatch


with contextlib.redirect_stdout(io.StringIO()):
    import jionlp as jio


PROJECT_NAME = "Address Engine"
NAME_PATTERNS = (
    re.compile(r"(?:收件人|联系人|收货人|姓名|名字)[:：]?\s*([\u4e00-\u9fff]{2,4})"),
    re.compile(r"寄给([\u4e00-\u9fff]{2,4})"),
)
NAME_SEGMENT_PATTERNS = (
    re.compile(r"(?:收件人|联系人|收货人|姓名|名字)[:：]?\s*[\u4e00-\u9fff]{2,4}"),
    re.compile(r"寄给[\u4e00-\u9fff]{2,4}"),
)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[-\s]?)?((?:1[3-9]\d{9})|(?:0\d{2,3}-?\d{7,8}))(?!\d)"
)
HONORIFIC_SUFFIXES = ("先生", "女士", "小姐", "太太")
PHONE_ADJACENT_NAME_PATTERN = re.compile(
    rf"(?:^|[\s,，;；/])([\u4e00-\u9fff]{{2,4}}|[\u4e00-\u9fff]{{1,4}}(?:{'|'.join(HONORIFIC_SUFFIXES)}))\s*"
    rf"(?=(?:\+?86[-\s]?)?(?:1[3-9]\d{{9}}|0\d{{2,3}}-?\d{{7,8}}))"
)
COUNTY_TOKEN_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,8}(?:区|县|旗|市))")
LEADING_SEPARATORS = " ，,：:;；/"
ADDRESS_HINT_CHARS = "省市区县旗乡镇街道路巷村社区苑号栋单元室园厦"
LEADING_NAME_PATTERN = re.compile(r"^\s*([\u4e00-\u9fff]{2,4})(?:[\s,，;；/]+)(.+)$")
COMMON_SINGLE_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史"
    "唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟"
    "平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项"
    "祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田"
    "樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左"
    "石崔吉龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富"
    "巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武"
    "符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池"
    "乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通"
    "边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾"
    "终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾"
    "敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖"
    "益桓公仉督岳帅缑亢况郈有琴归海晋楚闫法汝鄢涂钦岳帅"
)
COMPOUND_SURNAMES = {
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫", "万俟", "闻人", "夏侯", "诸葛",
    "尉迟", "公羊", "赫连", "澹台", "皇甫", "宗政", "濮阳", "公冶", "太叔", "申屠", "公孙", "慕容",
    "仲孙", "钟离", "长孙", "宇文", "司徒", "鲜于", "司空", "闾丘", "子车", "亓官", "司寇", "巫马",
    "公西", "颛孙", "壤驷", "公良", "漆雕", "乐正", "宰父", "谷梁", "拓跋", "夹谷", "轩辕", "令狐",
    "段干", "百里", "呼延", "东郭", "南门", "羊舌", "微生", "公户", "公玉", "公仪", "梁丘", "公仲",
    "公上", "公门", "公山", "公坚", "左丘", "公伯", "西门", "公祖", "第五", "公乘", "贯丘", "公皙",
    "南荣", "东里", "东宫", "仲长", "子书", "子桑", "即墨", "达奚", "褚师",
}
HEURISTIC_NAME_BLACKLIST = {
    "客服", "售后", "麻烦", "烦请", "请问", "您好", "你好", "谢谢", "感谢", "测试", "匿名", "默认",
    "本人", "自己", "地址", "电话", "手机", "收货", "发货", "快递", "物流", "门卫", "前台", "仓库",
    "王者", "荣耀", "家人", "朋友", "客户", "用户", "老板", "经理", "老师", "师傅", "同学",
}


class AddressExtractionService:
    def __init__(self, enable_road_poi_fallback: bool = False) -> None:
        self.admin_index = AdminIndex()
        self.town_index = TownIndex()
        self.enable_road_poi_fallback = enable_road_poi_fallback
        self.road_poi_index = RoadPOIFallbackIndex()

    def parse_text(self, text: str) -> dict:
        normalized_text = self._normalize_text(text)
        phones = self._extract_phones(normalized_text)
        name = self._extract_name(normalized_text)
        address_text, inferred_name = self._prepare_address_text(normalized_text, name)
        if name is None:
            name = inferred_name
        address = self._parse_address(address_text, raw_text=normalized_text)
        return {
            "project": PROJECT_NAME,
            "text": normalized_text,
            "person": {
                "name": name,
                "source": "rule" if name and inferred_name != name else ("heuristic" if name else "rule"),
            },
            "phones": phones,
            "address": address,
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _extract_name(self, text: str) -> str | None:
        for pattern in NAME_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return self._extract_phone_adjacent_name(text)

    def _extract_phone_adjacent_name(self, text: str) -> str | None:
        matches = list(PHONE_ADJACENT_NAME_PATTERN.finditer(text))
        for match in reversed(matches):
            candidate = match.group(1).strip()
            if self._looks_like_phone_adjacent_name(candidate, text):
                return candidate
        return None

    def _extract_phones(self, text: str) -> list[dict]:
        phones = []
        seen = set()
        for match in PHONE_PATTERN.finditer(text):
            raw_number = match.group(1)
            number = raw_number.replace(" ", "")
            if number in seen:
                continue
            seen.add(number)
            location = jio.phone_location(number)
            phones.append(
                {
                    "number": number,
                    "type": location.get("type"),
                    "province": location.get("province"),
                    "city": location.get("city"),
                }
            )
        return phones

    def _prepare_address_text(self, text: str, extracted_name: str | None) -> tuple[str, str | None]:
        cleaned = self._strip_extracted_name_segment(text, extracted_name)
        cleaned = PHONE_PATTERN.sub(" ", cleaned)
        for pattern in NAME_SEGMENT_PATTERNS:
            cleaned = pattern.sub(" ", cleaned)
        cleaned = self._strip_extracted_name_segment(cleaned, extracted_name)

        inferred_name = None
        if extracted_name is None:
            inferred_name, cleaned = self._strip_leading_name_token(cleaned, original_text=text)

        cleaned = re.sub(r"\s+", " ", cleaned).strip(LEADING_SEPARATORS + " ")
        return cleaned or text, inferred_name

    def _strip_leading_name_token(self, text: str, original_text: str | None = None) -> tuple[str | None, str]:
        match = LEADING_NAME_PATTERN.match(text)
        if not match:
            return None, text

        candidate = match.group(1).strip()
        remainder = match.group(2).strip()
        if not self._looks_like_unlabeled_name(candidate, original_text or text):
            return None, text

        mentions = self.admin_index.find_exact_mentions(remainder)
        has_address_context = any(mentions[rank] for rank in ("province", "city", "county"))
        if not has_address_context:
            parsed = jio.parse_location(remainder, town_village=True)
            has_address_context = any(parsed.get(field) for field in ("province", "city", "county"))
        if not has_address_context:
            return None, text
        return candidate, remainder

    @staticmethod
    def _strip_extracted_name_segment(text: str, extracted_name: str | None) -> str:
        if not extracted_name:
            return text

        escaped_name = re.escape(extracted_name)
        text = re.sub(
            rf"{escaped_name}\s*(?=(?:\+?86[-\s]?)?(?:1[3-9]\d{{9}}|0\d{{2,3}}-?\d{{7,8}}))",
            " ",
            text,
            count=1,
        )
        return re.sub(
            rf"(^|[\s,，;；/]){escaped_name}(?=$|[\s,，;；/])",
            r"\1",
            text,
            count=1,
        )

    def _looks_like_unlabeled_name(self, candidate: str, full_text: str) -> bool:
        if not (2 <= len(candidate) <= 4):
            return False
        if candidate in HEURISTIC_NAME_BLACKLIST:
            return False
        if any(char in ADDRESS_HINT_CHARS for char in candidate):
            return False
        if self.admin_index.records_by_name.get(candidate):
            return False
        if candidate in COMPOUND_SURNAMES:
            return False

        has_phone = bool(PHONE_PATTERN.search(full_text))
        if len(candidate) == 2:
            return candidate[0] in COMMON_SINGLE_SURNAMES and has_phone

        if len(candidate) == 3:
            if candidate[:2] in COMPOUND_SURNAMES:
                return True
            return candidate[0] in COMMON_SINGLE_SURNAMES

        return candidate[:2] in COMPOUND_SURNAMES

    def _looks_like_phone_adjacent_name(self, candidate: str, full_text: str) -> bool:
        for suffix in HONORIFIC_SUFFIXES:
            if candidate.endswith(suffix):
                base_name = candidate[: -len(suffix)]
                if not base_name or base_name in HEURISTIC_NAME_BLACKLIST:
                    return False
                if any(char in ADDRESS_HINT_CHARS for char in base_name):
                    return False
                if self.admin_index.records_by_name.get(base_name):
                    return False
                return self._looks_like_human_name_core(base_name)
        return self._looks_like_unlabeled_name(candidate, full_text)

    @staticmethod
    def _looks_like_human_name_core(candidate: str) -> bool:
        if not (1 <= len(candidate) <= 4):
            return False
        if len(candidate) == 1:
            return candidate in COMMON_SINGLE_SURNAMES
        if len(candidate) == 2:
            if candidate in COMPOUND_SURNAMES:
                return True
            return candidate[0] in COMMON_SINGLE_SURNAMES
        if len(candidate) == 3:
            if candidate[:2] in COMPOUND_SURNAMES:
                return True
            return candidate[0] in COMMON_SINGLE_SURNAMES
        return candidate[:2] in COMPOUND_SURNAMES

    def _parse_address(self, text: str, raw_text: str | None = None) -> dict:
        raw_text = raw_text or text
        jio_result = jio.parse_location(text, town_village=True)
        cpca_result = self._parse_cpca(text)
        exact_mentions = self.admin_index.find_exact_mentions(text)

        jio_path = self.admin_index.match_path(
            province=jio_result.get("province"),
            city=jio_result.get("city"),
            county=jio_result.get("county"),
        )
        cpca_path = self.admin_index.match_path(
            province=cpca_result.get("province"),
            city=cpca_result.get("city"),
            county=cpca_result.get("county"),
        )

        selected: AdminRecord | None = None
        source = "none"
        warnings: list[str] = []
        corrections: list[dict] = []
        alternatives: list[dict] = []
        needs_review = False
        auto_corrected = False
        strip_tokens = []
        road_poi_match: RoadPOIMatch | None = None
        town_match: TownMatch | None = None

        exact_provinces = sorted({record.province for record in exact_mentions["province"]})
        exact_cities = sorted({record.city for record in exact_mentions["city"] if record.city})
        exact_counties = sorted({record.county for record in exact_mentions["county"] if record.county})

        if len(exact_counties) == 1:
            county_name = exact_counties[0]
            county_candidates = self.admin_index.county_candidates(county_name)
            if len(county_candidates) == 1:
                selected = county_candidates[0]
                source = "exact_county"
            else:
                selected = self._disambiguate_county(
                    county_candidates,
                    exact_cities,
                    exact_provinces,
                    jio_path,
                    cpca_path,
                )
                if selected is not None:
                    source = "exact_county_disambiguated"
                else:
                    needs_review = True
                    warnings.append(f"区县 `{county_name}` 存在重名，缺少足够上下文，未自动补全省市。")
                    alternatives = [candidate.to_path() for candidate in county_candidates]
        elif len(exact_counties) > 1:
            needs_review = True
            warnings.append("文本中包含多个区县名称，存在地址歧义。")
            if jio_path is not None and jio_path.county in exact_counties:
                selected = jio_path
                source = "jionlp_multi_county"

        if selected is None and not alternatives:
            if len(exact_cities) == 1:
                city_name = exact_cities[0]
                city_candidates = self.admin_index.city_candidates(city_name)
                if len(city_candidates) == 1:
                    selected = city_candidates[0]
                    source = "exact_city"
                else:
                    selected = self._disambiguate_city(city_candidates, exact_provinces, jio_path, cpca_path)
                    if selected is not None:
                        source = "exact_city_disambiguated"

        if selected is None and not alternatives:
            if jio_path is not None and cpca_path is not None and self._paths_agree(jio_path, cpca_path):
                selected = self._deeper_path(jio_path, cpca_path)
                source = "jionlp_cpca_consensus"
            elif jio_path is not None:
                selected = jio_path
                source = "jionlp"
            elif cpca_path is not None:
                selected = cpca_path
                source = "cpca"

        if selected is not None:
            field_corrections = self._build_conflict_corrections(selected, exact_provinces, exact_cities)
            if field_corrections:
                corrections.extend(field_corrections)
                auto_corrected = True
                if any(item["field"] == "city" for item in field_corrections):
                    needs_review = True

        fuzzy_token = None
        if selected is not None and selected.city and selected.county is None:
            fuzzy_token, fuzzy_record = self._try_fuzzy_county(text, jio_result, selected)
            if fuzzy_record is not None:
                selected = fuzzy_record
                auto_corrected = True
                corrections.append(
                    {
                        "field": "county",
                        "from": fuzzy_token,
                        "to": fuzzy_record.county,
                        "reason": "fuzzy_county_under_city",
                    }
                )
                source = "fuzzy_county"
                strip_tokens.append(fuzzy_token)

        if self.enable_road_poi_fallback and (selected is None or selected.county is None):
            road_poi_match = self._try_road_poi_fallback(
                text,
                selected,
                jio_result,
                cpca_result,
                exact_provinces,
                exact_cities,
            )
            if road_poi_match is not None:
                fallback_selected = self.admin_index.match_path(
                    province=road_poi_match.province,
                    city=road_poi_match.city,
                    county=road_poi_match.county,
                )
                if fallback_selected is not None:
                    previous_selected = selected
                    selected = fallback_selected
                    source = f"{road_poi_match.kind}_fallback"
                    auto_corrected = True
                    needs_review = False
                    alternatives = []
                    warnings = [item for item in warnings if "当前结果仅由 CPCA 支撑" not in item]
                    corrections.extend(
                        self._build_road_poi_corrections(previous_selected, fallback_selected, road_poi_match)
                    )

        if selected is not None and selected.county is not None and jio_result.get("town") is None:
            town_match = self._try_town_fallback(
                selected,
                jio_result.get("detail") or cpca_result.get("detail") or text,
            )
            if town_match is not None:
                auto_corrected = True
                if town_match.matched_text:
                    strip_tokens.append(town_match.matched_text)
                corrections.append(
                    {
                        "field": "town",
                        "from": None,
                        "to": town_match.record.name,
                        "reason": f"town_fallback:{town_match.method}",
                    }
                )

        if selected is not None and town_match is None and jio_result.get("town") is None:
            road_poi_correction = self._try_road_poi_conflict_correction(
                text,
                selected,
                jio_result,
                cpca_result,
                exact_provinces,
                exact_cities,
            )
            if road_poi_correction is not None:
                road_match, corrected_selected = road_poi_correction
                previous_selected = selected
                selected = corrected_selected
                road_poi_match = road_match
                source = f"{road_match.kind}_conflict_correction"
                auto_corrected = True
                needs_review = True
                corrections.extend(
                    self._build_road_poi_corrections(previous_selected, corrected_selected, road_match)
                )

        if selected is None and alternatives:
            county_name = exact_counties[0] if len(exact_counties) == 1 else None
            detail = self._clean_detail(jio_result.get("detail") or cpca_result.get("detail"), county_name)
            confidence = "low"
            return {
                "raw": raw_text,
                "parsed_text": text,
                "province": None,
                "city": None,
                "county": county_name,
                "town": jio_result.get("town"),
                "detail": detail,
                "standardized": self._format_address(None, None, county_name, jio_result.get("town"), detail),
                "confidence": confidence,
                "resolved_by": source,
                "auto_corrected": auto_corrected,
                "needs_review": True,
                "warnings": warnings,
                "corrections": corrections,
                "alternatives": alternatives,
            }

        if selected is not None and source == "cpca":
            needs_review = True
            warnings.append("当前结果仅由 CPCA 支撑，建议结合业务字段或人工复核。")

        province = selected.province if selected else None
        city = selected.city if selected else None
        county = selected.county if selected else None
        town = (
            road_poi_match.town
            if road_poi_match and road_poi_match.town
            else (town_match.record.name if town_match else jio_result.get("town"))
        )
        detail = self._clean_detail(
            jio_result.get("detail") or cpca_result.get("detail"),
            province,
            city,
            county,
            town,
            *strip_tokens,
        )
        detail = self._trim_county_suffix_artifact(text, county, detail)
        confidence = self._estimate_confidence(selected, source, needs_review)

        return {
            "raw": raw_text,
            "parsed_text": text,
            "province": province,
            "city": city,
            "county": county or jio_result.get("county"),
            "town": town,
            "detail": detail,
            "standardized": self._format_address(province, city, county or jio_result.get("county"), town, detail),
            "confidence": confidence,
            "resolved_by": source,
            "auto_corrected": auto_corrected,
            "needs_review": needs_review,
            "warnings": warnings,
            "corrections": corrections,
            "alternatives": alternatives,
        }

    @staticmethod
    def _paths_agree(left: AdminRecord, right: AdminRecord) -> bool:
        return (
            left.province == right.province
            and left.city == right.city
            and (left.county == right.county or left.county is None or right.county is None)
        )

    @staticmethod
    def _deeper_path(left: AdminRecord, right: AdminRecord) -> AdminRecord:
        left_depth = sum(1 for item in (left.province, left.city, left.county) if item)
        right_depth = sum(1 for item in (right.province, right.city, right.county) if item)
        return left if left_depth >= right_depth else right

    def _disambiguate_county(
        self,
        candidates: list[AdminRecord],
        exact_cities: list[str],
        exact_provinces: list[str],
        jio_path: AdminRecord | None,
        cpca_path: AdminRecord | None,
    ) -> AdminRecord | None:
        if exact_cities:
            matched = [candidate for candidate in candidates if candidate.city in exact_cities]
            if len(matched) == 1:
                return matched[0]
        if exact_provinces:
            matched = [candidate for candidate in candidates if candidate.province in exact_provinces]
            if len(matched) == 1:
                return matched[0]
        if jio_path is not None and (jio_path.city or jio_path.province):
            matched = [candidate for candidate in candidates if candidate.city == jio_path.city]
            if len(matched) == 1:
                return matched[0]
        return None

    def _disambiguate_city(
        self,
        candidates: list[AdminRecord],
        exact_provinces: list[str],
        jio_path: AdminRecord | None,
        cpca_path: AdminRecord | None,
    ) -> AdminRecord | None:
        if exact_provinces:
            matched = [candidate for candidate in candidates if candidate.province in exact_provinces]
            if len(matched) == 1:
                return matched[0]
        if jio_path is not None:
            matched = [candidate for candidate in candidates if candidate.province == jio_path.province]
            if len(matched) == 1:
                return matched[0]
        if cpca_path is not None:
            matched = [candidate for candidate in candidates if candidate.province == cpca_path.province]
            if len(matched) == 1:
                return matched[0]
        return None

    def _try_fuzzy_county(
        self,
        text: str,
        jio_result: dict,
        selected: AdminRecord,
    ) -> tuple[str | None, AdminRecord | None]:
        candidate_source = jio_result.get("detail") or text
        seen = set()
        for token in COUNTY_TOKEN_PATTERN.findall(candidate_source):
            if token in seen:
                continue
            seen.add(token)
            if token == selected.city:
                continue
            fuzzy_record = self.admin_index.fuzzy_match(
                "county",
                token,
                province=selected.province,
                city=selected.city,
            )
            if fuzzy_record is not None:
                return token, fuzzy_record
        return None, None

    def _try_road_poi_fallback(
        self,
        text: str,
        selected: AdminRecord | None,
        jio_result: dict,
        cpca_result: dict,
        exact_provinces: list[str],
        exact_cities: list[str],
    ) -> RoadPOIMatch | None:
        province_hint = selected.province if selected else None
        city_hint = selected.city if selected else None

        if province_hint is None:
            province_hint = jio_result.get("province") or cpca_result.get("province")
        if province_hint is None and len(exact_provinces) == 1:
            province_hint = exact_provinces[0]

        if city_hint is None:
            city_hint = jio_result.get("city") or cpca_result.get("city")
        if city_hint is None and len(exact_cities) == 1:
            city_hint = exact_cities[0]

        candidate_sources = [
            jio_result.get("detail") or "",
            cpca_result.get("detail") or "",
            text,
        ]
        for candidate_text in candidate_sources:
            if not candidate_text:
                continue
            match = self.road_poi_index.match(candidate_text, province=province_hint, city=city_hint)
            if match is not None:
                return match
        return None

    def _try_road_poi_conflict_correction(
        self,
        text: str,
        selected: AdminRecord,
        jio_result: dict,
        cpca_result: dict,
        exact_provinces: list[str],
        exact_cities: list[str],
    ) -> tuple[RoadPOIMatch, AdminRecord] | None:
        if selected.province is None or selected.city is None or selected.county is None:
            return None

        match = self._try_road_poi_fallback(
            text,
            selected,
            jio_result,
            cpca_result,
            exact_provinces,
            exact_cities,
        )
        if match is None:
            return None
        if match.province != selected.province or match.city != selected.city:
            return None
        if match.county == selected.county:
            return None

        corrected = self.admin_index.match_path(
            province=match.province,
            city=match.city,
            county=match.county,
        )
        if corrected is None:
            return None
        return match, corrected

    def _try_town_fallback(self, selected: AdminRecord, detail: str | None) -> TownMatch | None:
        return self.town_index.match(
            province=selected.province,
            city=selected.city,
            county=selected.county,
            detail=detail,
        )

    @staticmethod
    def _build_road_poi_corrections(
        previous_selected: AdminRecord | None,
        selected: AdminRecord,
        match: RoadPOIMatch,
    ) -> list[dict]:
        corrections = []
        previous_province = previous_selected.province if previous_selected else None
        previous_city = previous_selected.city if previous_selected else None
        previous_county = previous_selected.county if previous_selected else None

        if previous_province != selected.province:
            corrections.append(
                {
                    "field": "province",
                    "from": previous_province,
                    "to": selected.province,
                    "reason": f"{match.kind}_fallback:{match.keyword}",
                }
            )
        if previous_city != selected.city:
            corrections.append(
                {
                    "field": "city",
                    "from": previous_city,
                    "to": selected.city,
                    "reason": f"{match.kind}_fallback:{match.keyword}",
                }
            )
        if previous_county != selected.county:
            corrections.append(
                {
                    "field": "county",
                    "from": previous_county,
                    "to": selected.county,
                    "reason": f"{match.kind}_fallback:{match.keyword}",
                }
            )
        return corrections

    @staticmethod
    def _build_conflict_corrections(
        selected: AdminRecord,
        exact_provinces: list[str],
        exact_cities: list[str],
    ) -> list[dict]:
        corrections = []
        conflicting_provinces = [name for name in exact_provinces if name != selected.province]
        if len(exact_provinces) == 1 and selected.province not in exact_provinces:
            corrections.append(
                {
                    "field": "province",
                    "from": exact_provinces[0],
                    "to": selected.province,
                    "reason": "deeper_admin_match",
                }
            )
        elif conflicting_provinces:
            corrections.append(
                {
                    "field": "province",
                    "from": " / ".join(conflicting_provinces),
                    "to": selected.province,
                    "reason": "conflicting_prefix_removed",
                }
            )

        conflicting_cities = [name for name in exact_cities if name != selected.city]
        if len(exact_cities) == 1 and selected.city not in exact_cities:
            corrections.append(
                {
                    "field": "city",
                    "from": exact_cities[0],
                    "to": selected.city,
                    "reason": "deeper_admin_match",
                }
            )
        elif conflicting_cities:
            corrections.append(
                {
                    "field": "city",
                    "from": " / ".join(conflicting_cities),
                    "to": selected.city,
                    "reason": "conflicting_prefix_removed",
                }
            )
        return corrections

    @staticmethod
    def _clean_detail(detail: str | None, *prefixes: str | None) -> str | None:
        if not detail:
            return detail
        cleaned = detail.strip()
        for prefix in prefixes:
            if prefix and cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(LEADING_SEPARATORS)
        return cleaned.strip() or None

    @staticmethod
    def _trim_county_suffix_artifact(
        text: str,
        county: str | None,
        detail: str | None,
    ) -> str | None:
        if not county or not detail or len(county) < 2:
            return detail
        leading_char = detail[0]
        if not re.match(r"^[\u4e00-\u9fff]$", leading_char):
            return detail
        typo_token = county[:-1] + leading_char
        if typo_token == county:
            return detail
        if typo_token not in text:
            return detail
        if SequenceMatcher(None, typo_token, county).ratio() < 0.66:
            return detail
        return detail[1:].lstrip(LEADING_SEPARATORS) or None

    @staticmethod
    def _estimate_confidence(
        selected: AdminRecord | None,
        source: str,
        needs_review: bool,
    ) -> str:
        if selected is None:
            return "low"
        depth = sum(1 for item in (selected.province, selected.city, selected.county) if item)
        if needs_review:
            return "medium" if depth >= 2 else "low"
        if depth >= 3 and source != "cpca":
            return "high"
        if depth >= 2:
            return "medium"
        return "low"

    @staticmethod
    def _format_address(
        province: str | None,
        city: str | None,
        county: str | None,
        town: str | None,
        detail: str | None,
    ) -> str | None:
        parts = []
        if province:
            parts.append(province)
        if city and city != province:
            parts.append(city)
        if county:
            parts.append(county)
        if town:
            parts.append(town)
        if detail:
            parts.append(detail)
        return "".join(parts) or None

    @staticmethod
    def _parse_cpca(text: str) -> dict:
        row = cpca.transform([text], pos_sensitive=True).iloc[0]
        province = None if pd.isna(row["省"]) else row["省"]
        city = None if pd.isna(row["市"]) else row["市"]
        county = None if pd.isna(row["区"]) else row["区"]
        if province in {"北京市", "上海市", "天津市", "重庆市"} and city in {"市辖区", "县"}:
            city = province
        if city in {"省直辖县级行政区划", "自治区直辖县级行政区划"}:
            city = province
        return {
            "province": province,
            "city": city,
            "county": county,
            "detail": None if pd.isna(row["地址"]) else row["地址"],
            "adcode": None if pd.isna(row["adcode"]) else str(row["adcode"]),
            "province_pos": int(row["省_pos"]),
            "city_pos": int(row["市_pos"]),
            "county_pos": int(row["区_pos"]),
        }
