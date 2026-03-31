from app.service import AddressExtractionService


service = AddressExtractionService()


def test_extracts_structured_contact_info() -> None:
    result = service.parse_text("收件人张三，电话13800138000，地址广东省深圳市南山区科技园科苑路15号")
    assert result["person"]["name"] == "张三"
    assert result["person"]["source"] == "rule"
    assert result["phones"][0]["number"] == "13800138000"
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "深圳市"
    assert result["address"]["county"] == "南山区"
    assert result["address"]["detail"] == "科技园科苑路15号"
    assert result["address"]["auto_corrected"] is False
    assert result["address"]["needs_review"] is False
    assert "evidence" not in result["address"]


def test_corrects_wrong_province_by_city_and_county() -> None:
    result = service.parse_text("浙江省广州市天河区体育西路101号")
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "广州市"
    assert result["address"]["county"] == "天河区"
    assert result["address"]["auto_corrected"] is True
    assert any(item["field"] == "province" for item in result["address"]["corrections"])


def test_corrects_wrong_city_by_unique_county_but_marks_review() -> None:
    result = service.parse_text("广东省深圳市天河区体育西路101号")
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "广州市"
    assert result["address"]["county"] == "天河区"
    assert result["address"]["auto_corrected"] is True
    assert result["address"]["needs_review"] is True
    assert any(item["field"] == "city" for item in result["address"]["corrections"])


def test_fuzzy_corrects_county_typo_under_city_context() -> None:
    result = service.parse_text("广东省广州市天和区体育西路101号")
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "广州市"
    assert result["address"]["county"] == "天河区"
    assert result["address"]["detail"] == "体育西路101号"
    assert result["address"]["auto_corrected"] is True
    assert any(item["field"] == "county" for item in result["address"]["corrections"])


def test_normalizes_direct_admin_city() -> None:
    result = service.parse_text("上海市徐汇区虹漕路461号58号楼5楼")
    assert result["address"]["province"] == "上海市"
    assert result["address"]["city"] == "上海市"
    assert result["address"]["county"] == "徐汇区"
    assert result["address"]["standardized"] == "上海市徐汇区虹漕路461号58号楼5楼"


def test_keeps_ambiguous_county_without_guessing() -> None:
    result = service.parse_text("鼓楼区中央路1号")
    assert result["address"]["province"] is None
    assert result["address"]["city"] is None
    assert result["address"]["county"] == "鼓楼区"
    assert result["address"]["needs_review"] is True
    assert len(result["address"]["alternatives"]) >= 2


def test_corrects_wrong_prefix_before_beijing_address() -> None:
    result = service.parse_text("上海市北京市朝阳区望京SOHO")
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["auto_corrected"] is True


def test_corrects_wrong_province_when_only_city_is_valid() -> None:
    result = service.parse_text("浙江省广州市体育西路101号")
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "广州市"
    assert result["address"]["county"] is None
    assert result["address"]["detail"] == "体育西路101号"
    assert result["address"]["standardized"] == "广东省广州市体育西路101号"


def test_removes_residual_typo_after_jionlp_county_correction() -> None:
    result = service.parse_text("北京市朝阳曲望京SOHO")
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["detail"] == "望京SOHO"
    assert result["address"]["standardized"] == "北京市朝阳区望京SOHO"


def test_strips_phone_before_address_parsing() -> None:
    result = service.parse_text("张三 13800138000 上海市徐汇区虹漕路461号58号楼5楼")
    assert result["phones"][0]["number"] == "13800138000"
    assert result["address"]["province"] == "上海市"
    assert result["address"]["city"] == "上海市"
    assert result["address"]["county"] == "徐汇区"
    assert result["address"]["detail"] == "虹漕路461号58号楼5楼"
    assert "13800138000" not in result["address"]["parsed_text"]


def test_suppresses_leading_name_that_collides_with_place_abbreviation() -> None:
    result = service.parse_text("南宫雪 河南省 和田地区和田市xx小区 13311111111")
    assert result["person"]["name"] == "南宫雪"
    assert result["person"]["source"] == "heuristic"
    assert result["address"]["province"] == "新疆维吾尔自治区"
    assert result["address"]["city"] == "和田地区"
    assert result["address"]["county"] == "和田市"
    assert result["address"]["detail"] == "xx小区"
    assert result["address"]["auto_corrected"] is True
    assert "南宫雪" not in result["address"]["parsed_text"]
    assert "13311111111" not in result["address"]["parsed_text"]


def test_does_not_treat_business_words_as_unlabeled_person_names() -> None:
    for text in (
        "客服 上海市徐汇区虹漕路461号58号楼5楼 13800138000",
        "售后 广东省广州市天河区体育西路101号 13800138000",
        "麻烦 上海市徐汇区漕溪北路398号 13800138000",
    ):
        result = service.parse_text(text)
        assert result["person"]["name"] is None


def test_does_not_treat_four_char_common_word_as_name() -> None:
    result = service.parse_text("王者荣耀 上海市徐汇区虹漕路461号58号楼5楼 13800138000")
    assert result["person"]["name"] is None


def test_keeps_two_char_person_name_when_phone_exists() -> None:
    result = service.parse_text("张三 上海市徐汇区虹漕路461号58号楼5楼 13800138000")
    assert result["person"]["name"] == "张三"
    assert result["person"]["source"] == "heuristic"


def test_keeps_compound_surname_person_name() -> None:
    result = service.parse_text("欧阳娜娜 上海市徐汇区虹漕路461号58号楼5楼 13800138000")
    assert result["person"]["name"] == "欧阳娜娜"
    assert result["person"]["source"] == "heuristic"


def test_fills_missing_county_by_local_road_fallback() -> None:
    fallback_service = AddressExtractionService(enable_road_poi_fallback=True)
    result = fallback_service.parse_text("上海市虹漕路461号58号楼5楼")
    assert result["address"]["province"] == "上海市"
    assert result["address"]["city"] == "上海市"
    assert result["address"]["county"] == "徐汇区"
    assert result["address"]["detail"] == "虹漕路461号58号楼5楼"
    assert result["address"]["standardized"] == "上海市徐汇区虹漕路461号58号楼5楼"
    assert result["address"]["resolved_by"] == "road_fallback"
    assert result["address"]["auto_corrected"] is True
    assert result["address"]["needs_review"] is False


def test_keeps_incomplete_road_fragment_unresolved() -> None:
    result = service.parse_text("上海市漕路461号58号楼5楼")
    assert result["address"]["province"] == "上海市"
    assert result["address"]["county"] is None
    assert result["address"]["needs_review"] is True


def test_does_not_duplicate_town_in_standardized_address() -> None:
    result = service.parse_text("上海市青浦区徐泾镇虹漕路461号58号楼5楼")
    assert result["address"]["province"] == "上海市"
    assert result["address"]["city"] == "上海市"
    assert result["address"]["county"] == "青浦区"
    assert result["address"]["town"] == "徐泾镇"
    assert result["address"]["detail"] == "虹漕路461号58号楼5楼"
    assert result["address"]["standardized"] == "上海市青浦区徐泾镇虹漕路461号58号楼5楼"


def test_optional_road_fallback_can_fill_city_and_county() -> None:
    fallback_service = AddressExtractionService(enable_road_poi_fallback=True)
    result = fallback_service.parse_text("浙江省广州市体育西路101号")
    assert result["address"]["province"] == "广东省"
    assert result["address"]["city"] == "广州市"
    assert result["address"]["county"] == "天河区"
    assert result["address"]["resolved_by"] == "road_fallback"


def test_infers_town_from_alias_under_county_context() -> None:
    result = service.parse_text("上海市青浦区徐泾虹漕路461号58号楼5楼")
    assert result["address"]["province"] == "上海市"
    assert result["address"]["city"] == "上海市"
    assert result["address"]["county"] == "青浦区"
    assert result["address"]["town"] == "徐泾镇"
    assert result["address"]["detail"] == "虹漕路461号58号楼5楼"
    assert result["address"]["standardized"] == "上海市青浦区徐泾镇虹漕路461号58号楼5楼"
    assert any(item["field"] == "town" for item in result["address"]["corrections"])


def test_infers_street_from_alias_when_followed_by_road_cue() -> None:
    result = service.parse_text("重庆市忠县忠州大桥路1号")
    assert result["address"]["province"] == "重庆市"
    assert result["address"]["city"] == "重庆市"
    assert result["address"]["county"] == "忠县"
    assert result["address"]["town"] == "忠州街道"
    assert result["address"]["detail"] == "大桥路1号"
    assert result["address"]["standardized"] == "重庆市忠县忠州街道大桥路1号"


def test_does_not_infer_street_from_business_area_name_only() -> None:
    result = service.parse_text("北京市朝阳区望京SOHO T3")
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["town"] is None
    assert result["address"]["standardized"] == "北京市朝阳区望京SOHO T3"


def test_extracts_honorific_name_before_phone_and_removes_it_from_address() -> None:
    result = service.parse_text("北京市朝阳区酒仙桥东路1号m3c大厦A座1101室 王先生13511112222")
    assert result["person"]["name"] == "王先生"
    assert result["person"]["source"] == "rule"
    assert result["phones"][0]["number"] == "13511112222"
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["town"] is None
    assert result["address"]["detail"] == "酒仙桥东路1号m3c大厦A座1101室"
    assert result["address"]["standardized"] == "北京市朝阳区酒仙桥东路1号m3c大厦A座1101室"


def test_corrects_wrong_county_by_high_confidence_road_keyword() -> None:
    result = service.parse_text("北京市海淀区酒仙桥东路1号m3c大厦A座1101室 王先生13511112222")
    assert result["person"]["name"] == "王先生"
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["town"] is None
    assert result["address"]["detail"] == "酒仙桥东路1号m3c大厦A座1101室"
    assert result["address"]["standardized"] == "北京市朝阳区酒仙桥东路1号m3c大厦A座1101室"
    assert result["address"]["auto_corrected"] is True
    assert result["address"]["needs_review"] is True
    assert result["address"]["resolved_by"] == "road_conflict_correction"
    assert any(item["field"] == "county" and item["to"] == "朝阳区" for item in result["address"]["corrections"])


def test_does_not_split_road_name_into_town_alias() -> None:
    result = service.parse_text("北京市朝阳区酒仙桥东路1号")
    assert result["address"]["province"] == "北京市"
    assert result["address"]["city"] == "北京市"
    assert result["address"]["county"] == "朝阳区"
    assert result["address"]["town"] is None
    assert result["address"]["detail"] == "酒仙桥东路1号"
    assert result["address"]["standardized"] == "北京市朝阳区酒仙桥东路1号"
