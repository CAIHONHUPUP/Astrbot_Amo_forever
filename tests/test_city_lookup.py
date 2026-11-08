from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amo_city_index import resolve_city, search_city  # noqa: E402


class ResolveCityTests(unittest.TestCase):
    def test_dongguan_variants(self) -> None:
        for text in ("东莞", "东莞市", "广东东莞", "广东省东莞市", "东莞南城", " 东莞 "):
            hit = resolve_city(text)
            self.assertIsNotNone(hit, text)
            self.assertEqual(hit["id"], "101281601", text)
            self.assertEqual(hit["name"], "东莞", text)

    def test_municipality_and_district(self) -> None:
        self.assertEqual(resolve_city("北京")["id"], "101010100")
        # 写「北京朝阳」「朝阳区」都落到北京朝阳区
        self.assertEqual(resolve_city("北京朝阳")["id"], "101010300")
        self.assertEqual(resolve_city("朝阳区")["id"], "101010300")
        # 只写「朝阳」按地级市朝阳市算，不自动猜北京
        chao = resolve_city("朝阳")
        self.assertEqual(chao["city"], "朝阳市")

    def test_city_and_district(self) -> None:
        nanshan = resolve_city("深圳南山")
        self.assertEqual(nanshan["id"], "101280604")
        self.assertEqual(nanshan["city"], "深圳市")

    def test_ambiguous_short_name_is_flagged(self) -> None:
        hit = resolve_city("鼓楼区")  # 开封/南京/徐州/福州 四个
        self.assertEqual(hit["ambiguous"], 4)
        self.assertTrue(any("南京" in c for c in hit["candidates"]))
        self.assertIn("南京鼓楼", hit["note"])

    def test_ambiguous_district_has_candidates(self) -> None:
        hit = resolve_city("南山区")  # 鹤岗 / 深圳
        self.assertEqual(hit["ambiguous"], 2)
        self.assertIn("广东省·深圳市", hit["candidates"])

    def test_disambiguated_has_no_warning(self) -> None:
        self.assertFalse(resolve_city("深圳南山").get("ambiguous"))
        self.assertFalse(resolve_city("东莞").get("ambiguous"))

    def test_numeric_id_passthrough(self) -> None:
        hit = resolve_city("101281601")
        self.assertEqual(hit["id"], "101281601")
        self.assertTrue(hit["ok"])

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(resolve_city("不存在的城市xyz"))
        self.assertIsNone(resolve_city(""))
        self.assertIsNone(resolve_city(None))


class SearchCityTests(unittest.TestCase):
    def test_search_hit(self) -> None:
        rows = search_city("东莞", 5)
        self.assertTrue(rows)
        self.assertTrue(any(row["id"] == "101281601" for row in rows))

    def test_ambiguous_name_lists_city_level_first(self) -> None:
        rows = search_city("朝阳", 3)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["city"], "朝阳市")  # 地级市排在区县前面

    def test_limit(self) -> None:
        rows = search_city("朝阳", 2)
        self.assertLessEqual(len(rows), 2)

    def test_empty_query(self) -> None:
        self.assertEqual(search_city("", 5), [])


if __name__ == "__main__":
    unittest.main()
