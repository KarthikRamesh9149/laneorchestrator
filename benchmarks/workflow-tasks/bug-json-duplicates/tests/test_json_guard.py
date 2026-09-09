import unittest

from json_guard import DuplicateJSONKeyError, parse_json_object


class JsonGuardTests(unittest.TestCase):
    def test_preserves_nested_json_values(self):
        self.assertEqual(
            parse_json_object('{"name":"lane","items":[1,true,null],"meta":{"ok":false}}'),
            {"name": "lane", "items": [1, True, None], "meta": {"ok": False}},
        )

    def test_rejects_duplicate_top_level_key(self):
        with self.assertRaises(DuplicateJSONKeyError):
            parse_json_object('{"model":"terra","model":"sol"}')

    def test_rejects_duplicate_nested_key(self):
        with self.assertRaises(DuplicateJSONKeyError):
            parse_json_object('{"outer":{"effort":"low","effort":"high"}}')

    def test_decoded_key_identity_controls_duplicates(self):
        with self.assertRaises(DuplicateJSONKeyError):
            parse_json_object('{"name":1,"n\\u0061me":2}')

    def test_rejects_non_object_and_malformed_input(self):
        for value in ('[]', 'null', '"text"', '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_json_object(value)
        with self.assertRaises(ValueError):
            parse_json_object('{')


if __name__ == "__main__":
    unittest.main()
