"""Testes públicos do contrato, com exemplos fictícios e propriedades globais."""

import copy
import csv
import io
import json
import unittest
from collections import Counter
from itertools import combinations

from liga_local import (
    LeagueError, clear_result, create_league, dumps_league, fixtures,
    import_results_csv, loads_league, progress, results_csv, set_result,
    standings, standings_csv, validate_league,
)


def league(count=4, **kwargs):
    return create_league("Liga da Praça", [
        {"id": chr(97 + index) if count <= 26 else f"p{index:02d}", "name": f"Equipe {index + 1}"}
        for index in range(count)
    ], **kwargs)


def record_pair(doc, first, second, first_score, second_score):
    """Registra um confronto pelo par de IDs, sem depender da orientação gerada."""
    game = next(game for game in fixtures(doc) if {game["home_id"], game["away_id"]} == {first, second})
    scores = (first_score, second_score) if game["home_id"] == first else (second_score, first_score)
    return set_result(doc, game["match_id"], *scores)


class EngineTests(unittest.TestCase):
    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(LeagueError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertIsInstance(caught.exception, ValueError)
        return str(caught.exception)

    def test_circle_four_participants_exact_calendar(self):
        doc = league()
        self.assertEqual([
            [(match["id"], match["home"], match["away"]) for match in round_["matches"]]
            for round_ in doc["rounds"]
        ], [
            [("r001-m001", "a", "d"), ("r001-m002", "c", "b")],
            [("r002-m001", "c", "a"), ("r002-m002", "d", "b")],
            [("r003-m001", "a", "b"), ("r003-m002", "d", "c")],
        ])
        self.assertEqual([round_["bye"] for round_ in doc["rounds"]], [None, None, None])

    def test_circle_odd_has_no_fictitious_game(self):
        doc = league(3)
        self.assertEqual([
            (round_["number"], round_["bye"], [(game["home"], game["away"]) for game in round_["matches"]])
            for round_ in doc["rounds"]
        ], [(1, "a", [("c", "b")]), (2, "b", [("c", "a")]), (3, "c", [("a", "b")])])
        self.assertEqual([row["match_id"] for row in fixtures(doc)], ["r001-m001", "r002-m001", "r003-m001"])

    def test_all_sizes_cover_pairs_and_return_leg(self):
        for count in range(2, 33):
            for double in (False, True):
                with self.subTest(participants=count, double=double):
                    doc = league(count, double_round=double)
                    ids = [item["id"] for item in doc["participants"]]
                    multiplier = 2 if double else 1
                    turn_rounds = count if count % 2 else count - 1
                    self.assertEqual(len(doc["rounds"]), turn_rounds * multiplier)
                    pairs = Counter()
                    byes = Counter()
                    game_ids = set()
                    for number, round_ in enumerate(doc["rounds"], 1):
                        self.assertEqual(round_["number"], number)
                        used = []
                        for position, game in enumerate(round_["matches"], 1):
                            self.assertEqual(game["id"], f"r{number:03d}-m{position:03d}")
                            self.assertNotIn(game["id"], game_ids)
                            game_ids.add(game["id"])
                            self.assertIsNone(game["score"])
                            used.extend((game["home"], game["away"]))
                            pairs[tuple(sorted((game["home"], game["away"])))] += 1
                        if round_["bye"] is not None:
                            used.append(round_["bye"])
                            byes[round_["bye"]] += 1
                        self.assertCountEqual(used, ids)
                        self.assertEqual(len(set(used)), count)
                    self.assertEqual(pairs, Counter({tuple(sorted(pair)): multiplier for pair in combinations(ids, 2)}))
                    self.assertEqual(byes, Counter({identifier: multiplier for identifier in ids}) if count % 2 else Counter())
                    if double:
                        for first, second in zip(doc["rounds"][:turn_rounds], doc["rounds"][turn_rounds:]):
                            self.assertEqual(first["bye"], second["bye"])
                            for home, away in zip(first["matches"], second["matches"]):
                                self.assertEqual((home["home"], home["away"]), (away["away"], away["home"]))

    def test_unicode_duplicate_names_and_boundary_values(self):
        people = [{"id": "A", "name": "São José ⚽"}, {"id": "a", "name": "São José ⚽"}]
        doc = create_league("L" * 120, people)
        self.assertEqual(doc["participants"], people)
        self.assertEqual(doc["scoring"], {"win": 3, "draw": 1, "loss": 0})
        long_id = "Z" + "_-9" * 13
        self.assertEqual(len(long_id), 40)
        self.assertEqual(create_league("Á", [{"id": long_id, "name": "é" * 80}, people[0]])["participants"][0]["id"], long_id)

    def test_participants_require_exact_types_unique_valid_ids(self):
        class SubList(list):
            pass
        class SubDict(dict):
            pass
        class SubString(str):
            pass
        valid = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        invalid = [None, (), [], valid[:1], valid * 17, SubList(valid), [SubDict(valid[0]), valid[1]]]
        for value in invalid:
            with self.subTest(value=repr(value)[:50]):
                self.assert_code("INVALID_LEAGUE", create_league, "Liga", value)
        for identifier in ("", "_a", "-a", "á", "a b", "a\n", "a" * 41, 1, True, SubString("a")):
            self.assert_code("INVALID_LEAGUE", create_league, "Liga", [{"id": identifier, "name": "A"}, valid[1]])
        for people in ([valid[0], valid[0]], [{"id": "a", "name": "A", "extra": 1}, valid[1]], [{"id": "a"}, valid[1]]):
            self.assert_code("INVALID_LEAGUE", create_league, "Liga", people)

    def test_names_reject_borders_and_unicode_category_c(self):
        invalid = ("", " ", " A", "A ", "\u2003A", "A\u00a0", "A\nB", "A\x00B", "A\u202eB", "A\ue000B", "A\ud800B", "A\u0378B")
        for name in invalid:
            self.assert_code("INVALID_LEAGUE", create_league, name, league(2)["participants"])
            self.assert_code("INVALID_LEAGUE", create_league, "Liga", [{"id": "a", "name": name}, {"id": "b", "name": "B"}])
        self.assert_code("INVALID_LEAGUE", create_league, "L" * 121, league(2)["participants"])
        self.assert_code("INVALID_LEAGUE", create_league, "Liga", [{"id": "a", "name": "A" * 81}, {"id": "b", "name": "B"}])

    def test_scoring_rules_and_exact_flags(self):
        self.assertEqual(league(2, scoring={"win": 1000, "draw": 0, "loss": 0})["scoring"], {"win": 1000, "draw": 0, "loss": 0})
        for scoring in ({}, {"win": 1, "draw": 1, "loss": 0}, {"win": 3, "draw": 0, "loss": 1},
                        {"win": 1001, "draw": 1, "loss": 0}, {"win": 3, "draw": 1, "loss": -1},
                        {"win": 3.0, "draw": 1, "loss": 0}, {"win": 3, "draw": True, "loss": 0},
                        {"win": 3, "draw": 1, "loss": 0, "extra": 0}):
            self.assert_code("INVALID_LEAGUE", league, 2, scoring=scoring)
        for flag in (0, 1, None, "true", []):
            self.assert_code("INVALID_LEAGUE", league, 2, double_round=flag)
            self.assert_code("INVALID_LEAGUE", set_result, league(2), "r001-m001", 0, 0, replace=flag)
            self.assert_code("INVALID_LEAGUE", import_results_csv, league(2), "match_id,home_score,away_score\nr001-m001,0,0\n", replace=flag)
        doc = league(2)
        doc["scoring"] = None
        self.assert_code("INVALID_LEAGUE", validate_league, doc)

    def test_schema_fields_and_builtin_types_are_exact(self):
        class SubDict(dict):
            pass
        class SubInt(int):
            pass
        original = league(2)
        self.assert_code("INVALID_LEAGUE", validate_league, SubDict(original))
        for value in (True, 1.0, SubInt(1), 2, None):
            doc = copy.deepcopy(original)
            doc["schema_version"] = value
            self.assert_code("INVALID_LEAGUE", validate_league, doc)
        locations = ((), ("participants", 0), ("scoring",), ("rounds", 0), ("rounds", 0, "matches", 0))
        for path in locations:
            doc = copy.deepcopy(original)
            target = doc
            for key in path:
                target = target[key]
            target["unrecognized"] = 1
            self.assert_code("INVALID_LEAGUE", validate_league, doc)
            del target["unrecognized"]
            del target[next(iter(target))]
            self.assert_code("INVALID_LEAGUE", validate_league, doc)

    def test_calendar_tampering_and_reordering_are_rejected(self):
        original = league(5, double_round=True)
        for mutation in (
            lambda doc: doc["rounds"].reverse(),
            lambda doc: doc["rounds"][0]["matches"].reverse(),
            lambda doc: doc["rounds"][0].update(number=True),
            lambda doc: doc["rounds"][0].update(bye="b"),
            lambda doc: doc["rounds"][0]["matches"][0].update(id="r001-m099"),
            lambda doc: doc["rounds"][0]["matches"][0].update(home="a"),
            lambda doc: doc["participants"].reverse(),
            lambda doc: doc["rounds"].pop(),
        ):
            doc = copy.deepcopy(original)
            mutation(doc)
            self.assert_code("INVALID_LEAGUE", validate_league, doc)

    def test_invalid_scores_have_operation_or_model_error(self):
        for score in (True, False, -1, 1000, 0.0, float("nan"), float("inf"), "0", None, [], {}):
            self.assert_code("INVALID_SCORE", set_result, league(2), "r001-m001", score, 0)
            self.assert_code("INVALID_SCORE", set_result, league(2), "r001-m001", 0, score)
            doc = league(2)
            doc["rounds"][0]["matches"][0]["score"] = {"home": score, "away": 0}
            self.assert_code("INVALID_LEAGUE", validate_league, doc)
        for score in ({}, {"home": 0}, {"home": 0, "away": 0, "extra": 0}, [0, 0]):
            doc = league(2)
            doc["rounds"][0]["matches"][0]["score"] = score
            self.assert_code("INVALID_LEAGUE", validate_league, doc)
        self.assertEqual(fixtures(set_result(league(2), "r001-m001", 999, 0))[0]["home_score"], 999)

    def test_record_clear_replace_and_out_of_order(self):
        original = league()
        result = set_result(original, "r003-m002", 0, 0)
        self.assertEqual(progress(original)["played_matches"], 0)
        self.assertEqual(progress(result)["played_matches"], 1)
        self.assertEqual(set_result(result, "r003-m002", 0, 0), result)
        self.assert_code("RESULT_EXISTS", set_result, result, "r003-m002", 1, 0)
        replaced = set_result(result, "r003-m002", 1, 0, replace=True)
        self.assertEqual(fixtures(replaced, 3)[1]["home_score"], 1)
        cleared = clear_result(replaced, "r003-m002")
        self.assertEqual(cleared, original)
        self.assertEqual(clear_result(cleared, "r003-m002"), original)

    def test_unknown_match_and_errors_do_not_echo_input(self):
        secret = "unknown-sensitive-value"
        for function, args in ((set_result, (secret, 0, 0)), (clear_result, (secret,)), (set_result, (True, 0, 0))):
            self.assertNotIn(secret, self.assert_code("UNKNOWN_MATCH", function, league(2), *args))
        self.assertNotIn(secret, self.assert_code("INVALID_LEAGUE", create_league, secret + "\n", league(2)["participants"]))

    def test_mutable_outputs_never_alias_inputs_or_each_other(self):
        original = set_result(league(3), "r001-m001", 1, 2)
        snapshot = copy.deepcopy(original)
        outputs = [validate_league(original), clear_result(original, "r002-m001"),
                   set_result(original, "r001-m001", 1, 2), loads_league(dumps_league(original)),
                   import_results_csv(original, results_csv(original))]
        for output in outputs:
            output["participants"][0]["name"] = "Changed"
            output["scoring"]["win"] = 500
            output["rounds"][0]["matches"][0]["score"]["home"] = 500
        self.assertEqual(original, snapshot)
        participant_input = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        scoring_input = {"win": 5, "draw": 2, "loss": 1}
        doc = create_league("Liga", participant_input, scoring=scoring_input)
        participant_input[0]["name"] = "Changed"
        scoring_input["win"] = 100
        self.assertEqual(doc["participants"][0]["name"], "A")
        self.assertEqual(doc["scoring"]["win"], 5)
        table = standings(original)
        table[0]["name"] = "Changed"
        schedule = fixtures(original)
        schedule[0]["home_name"] = "Changed"
        self.assertEqual(original, snapshot)

    def test_standings_independent_complete_arithmetic_fixture(self):
        doc = league()
        for identifier, home, away in (
            ("r001-m001", 2, 0), ("r001-m002", 1, 1), ("r002-m001", 0, 3),
            ("r002-m002", 4, 2), ("r003-m001", 0, 1), ("r003-m002", 2, 2),
        ):
            doc = set_result(doc, identifier, home, away)
        # A: 2 vitórias, 1 derrota, 5 gols a favor e 1 contra = 6 pontos.
        # D: vitória 4–2, empate 2–2, derrota 0–2 = 4 pontos e saldo zero.
        expected = [
            ["a", "Equipe 1", 3, 2, 0, 1, 5, 1, 4, 6, 1],
            ["d", "Equipe 4", 3, 1, 1, 1, 6, 6, 0, 4, 2],
            ["b", "Equipe 2", 3, 1, 1, 1, 4, 5, -1, 4, 3],
            ["c", "Equipe 3", 3, 0, 2, 1, 3, 6, -3, 2, 4],
        ]
        self.assertEqual([list(row.values()) for row in standings(doc)], expected)
        self.assertEqual(progress(doc), {"participants": 4, "rounds": 3, "total_matches": 6, "played_matches": 6, "pending_matches": 0, "complete": True})

    def test_competition_rank_uses_metrics_not_display_id(self):
        people = [{"id": identifier, "name": "Mesmo nome"} for identifier in ("b", "A", "a", "C")]
        doc = create_league("Liga", people)
        self.assertEqual([(row["id"], row["rank"]) for row in standings(doc)], [("A", 1), ("C", 1), ("a", 1), ("b", 1)])
        for game in fixtures(doc, 1):
            doc = set_result(doc, game["match_id"], 1, 0)
        self.assertEqual([(row["id"], row["rank"]) for row in standings(doc)], [("a", 1), ("b", 1), ("A", 3), ("C", 3)])

    def test_goals_for_then_wins_break_otherwise_equal_metrics(self):
        doc = record_pair(league(), "a", "c", 2, 1)
        doc = record_pair(doc, "b", "d", 1, 0)
        self.assertEqual([row["id"] for row in standings(doc)][:2], ["a", "b"])
        doc = league(scoring={"win": 2, "draw": 1, "loss": 0})
        for first, second, home, away in (("a", "c", 1, 0), ("a", "d", 0, 1), ("b", "c", 0, 0), ("b", "d", 1, 1)):
            doc = record_pair(doc, first, second, home, away)
        table = standings(doc)
        self.assertEqual([row["id"] for row in table], ["d", "a", "b", "c"])
        self.assertEqual([(row["points"], row["goal_difference"], row["goals_for"], row["won"]) for row in table[1:3]], [(2, 0, 1, 1), (2, 0, 1, 0)])

    def test_pending_is_not_draw_and_bye_gives_no_points(self):
        doc = league(3, scoring={"win": 5, "draw": 2, "loss": 1})
        self.assertEqual(sum(row["played"] for row in standings(doc)), 0)
        self.assertEqual(sum(row["points"] for row in standings(doc)), 0)
        doc = set_result(doc, "r001-m001", 0, 0)
        rows = {row["id"]: row for row in standings(doc)}
        self.assertEqual((rows["a"]["played"], rows["a"]["points"]), (0, 0))
        self.assertEqual((rows["b"]["drawn"], rows["b"]["points"]), (1, 2))
        self.assertEqual(progress(doc), {"participants": 3, "rounds": 3, "total_matches": 3, "played_matches": 1, "pending_matches": 2, "complete": False})

    def test_fixtures_filter_fields_names_and_round_validation(self):
        doc = set_result(league(), "r002-m001", 0, 0)
        self.assertEqual(fixtures(doc, 2), [
            {"round": 2, "match_id": "r002-m001", "home_id": "c", "home_name": "Equipe 3", "away_id": "a", "away_name": "Equipe 1", "home_score": 0, "away_score": 0},
            {"round": 2, "match_id": "r002-m002", "home_id": "d", "home_name": "Equipe 4", "away_id": "b", "away_name": "Equipe 2", "home_score": None, "away_score": None},
        ])
        for value in (True, False, 0, -1, 4, 1.0, "1", [], {}):
            self.assert_code("INVALID_ROUND", fixtures, doc, value)

    def test_json_is_canonical_unicode_and_accepts_field_reordering(self):
        original = set_result(league(3), "r001-m001", 0, 1)
        reordered = {key: original[key] for key in reversed(original)}
        text = dumps_league(reordered)
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\r", text)
        self.assertIn("Praça", text)
        self.assertNotIn("\\u00e7", text)
        self.assertEqual(text, json.dumps(original, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        self.assertEqual(loads_league(text), original)
        self.assertEqual(list(validate_league(reordered)), list(original))

    def test_json_rejects_duplicates_at_any_depth_and_limits_depth(self):
        for text in ('{"name":"A","name":"B"}', '{"extra":{"x":1,"x":2}}', '{"name":"A","na\\u006de":"B"}'):
            self.assert_code("INVALID_JSON", loads_league, text)
        self.assert_code("INVALID_LEAGUE", loads_league, "[" * 12 + "0" + "]" * 12)
        self.assert_code("INVALID_JSON", loads_league, "[" * 13 + "0" + "]" * 13)
        self.assert_code("INVALID_JSON", loads_league, "[" * 2000 + "0" + "]" * 2000)
        doc = create_league('Aspas " e colchetes [{}] \\', league(2)["participants"])
        self.assertEqual(loads_league(dumps_league(doc)), doc)

    def test_json_transport_parsing_numbers_and_byte_limit(self):
        for text in (b"{}", None, "\ufeff{}", "", "{", "{} trailing", "{\"x\": NaN}", "{\"x\": Infinity}", "\ud800"):
            self.assert_code("INVALID_JSON", loads_league, text)
        for replacement in ("1.0", "true", "null"):
            text = dumps_league(league(2)).replace('"schema_version": 1', '"schema_version": ' + replacement)
            self.assert_code("INVALID_LEAGUE", loads_league, text)
        base = dumps_league(league(2))
        padded = base + " " * (2 * 1024 * 1024 - len(base.encode("utf-8")))
        self.assertEqual(loads_league(padded), league(2))
        self.assert_code("INVALID_JSON", loads_league, padded + " ")
        self.assert_code("INVALID_JSON", loads_league, "é" * (1024 * 1024 + 1))

    def test_results_csv_canonical_export_and_bom_import(self):
        doc = set_result(league(3), "r002-m001", 0, 12)
        expected = "match_id,home_score,away_score\nr001-m001,,\nr002-m001,0,12\nr003-m001,,\n"
        self.assertEqual(results_csv(doc), expected)
        self.assertEqual(import_results_csv(league(3), "\ufeff" + expected), doc)
        self.assertEqual(import_results_csv(doc, expected.replace("\n", "\r\n")), doc)

    def test_results_csv_partial_idempotent_replace_and_all_or_none(self):
        original = set_result(league(), "r001-m001", 2, 1)
        text = "match_id,home_score,away_score\nr001-m001,2,1\nr003-m002,0,0\n"
        imported = import_results_csv(original, text)
        self.assertEqual(progress(imported)["played_matches"], 2)
        self.assertEqual(import_results_csv(imported, results_csv(imported)), imported)
        snapshot = copy.deepcopy(original)
        conflict = "match_id,home_score,away_score\nr003-m002,3,2\nr001-m001,1,1\n"
        self.assert_code("RESULT_EXISTS", import_results_csv, original, conflict)
        self.assertEqual(original, snapshot)
        replaced = import_results_csv(original, conflict, replace=True)
        self.assertEqual(progress(replaced)["played_matches"], 2)
        self.assertEqual(fixtures(replaced, 1)[0]["home_score"], 1)

    def test_csv_structure_unknown_and_duplicate_even_when_blank(self):
        header = "match_id,home_score,away_score\n"
        for text in ("", "id,home_score,away_score\nr001-m001,1,0\n", header, header + "\n",
                     header + "r001-m001,1,0,extra\n", header + "r001-m001,1\n",
                     header + '"r001-m001,1,0\n', header + "r001-m001,,\n",
                     header + "r001-m001,,\nr001-m001,1,0\n",
                     header + "r001-m001,1,0\nr001-m001,,\n"):
            self.assert_code("INVALID_CSV", import_results_csv, league(2), text)
        for row in ("unknown,1,0\n", "unknown,,\n", ",1,0\n"):
            self.assert_code("UNKNOWN_MATCH", import_results_csv, league(2), header + row)
        self.assertEqual(progress(import_results_csv(league(2), header + '"r001-m001","001","000"\n'))["played_matches"], 1)

    def test_csv_scores_require_two_ascii_unsigned_fields(self):
        header = "match_id,home_score,away_score\n"
        for score in ("", "-1", "+1", " 1", "1 ", "1.0", "1e1", "1000", "１２", "١", "NaN", "=1", "1\t"):
            for row in (f"r001-m001,{score},0\n", f"r001-m001,0,{score}\n"):
                self.assert_code("INVALID_CSV", import_results_csv, league(2), header + row)
        doc = import_results_csv(league(2), header + "r001-m001,999,000\n")
        self.assertEqual((fixtures(doc)[0]["home_score"], fixtures(doc)[0]["away_score"]), (999, 0))

    def test_csv_transport_size_line_limits_and_strict_quoting(self):
        header = "match_id,home_score,away_score\n"
        for text in (None, b"", "\ud800", "é" * (64 * 1024 + 1), "x" * (128 * 1024 + 1),
                     header + "r001-m001,0,0\n" * 1001,
                     header + '"r001-m001"garbage,0,0\n'):
            self.assert_code("INVALID_CSV", import_results_csv, league(2), text)
        self.assert_code("INVALID_CSV", import_results_csv, league(2), "\ufeff\ufeff" + header + "r001-m001,0,0\n")

    def test_standings_csv_preserves_numbers_and_prefixes_formula_strings(self):
        doc = create_league("Liga", [{"id": identifier, "name": name} for identifier, name in (
            ("a", "=SUM(1,2)"), ("b", "+Equipe"), ("c", "-Equipe"), ("d", "@Equipe"),
        )])
        doc = record_pair(doc, "a", "b", 0, 2)
        output = standings_csv(doc)
        self.assertTrue(output.endswith("\n"))
        self.assertNotIn("\r", output)
        rows = list(csv.DictReader(io.StringIO(output)))
        self.assertEqual(list(rows[0]), ["id", "name", "played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_difference", "points", "rank"])
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["a"]["name"], "'=SUM(1,2)")
        self.assertEqual(by_id["b"]["name"], "'+Equipe")
        self.assertEqual(by_id["c"]["name"], "'-Equipe")
        self.assertEqual(by_id["d"]["name"], "'@Equipe")
        self.assertEqual(by_id["a"]["goal_difference"], "-2")
        self.assertEqual(by_id["a"]["points"], "0")


if __name__ == "__main__":
    unittest.main()
