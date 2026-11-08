"""Calendário e resultados de ligas locais, usando somente a biblioteca padrão."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata


class LeagueError(ValueError):
    """Falha esperada, identificável por um código estável e sem dados de entrada."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_MESSAGES = {
    "INVALID_LEAGUE": "Liga ou parâmetros inválidos.",
    "INVALID_JSON": "Documento JSON inválido.",
    "INVALID_CSV": "Documento CSV inválido.",
    "UNKNOWN_MATCH": "Jogo não encontrado.",
    "RESULT_EXISTS": "O jogo já possui outro resultado.",
    "INVALID_SCORE": "Placar inválido.",
    "INVALID_ROUND": "Rodada inválida.",
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
_CSV_SCORE = re.compile(r"[0-9]{1,3}\Z")
_TABLE_FIELDS = (
    "id", "name", "played", "won", "drawn", "lost", "goals_for",
    "goals_against", "goal_difference", "points", "rank",
)
_JSON_LIMIT = 2 * 1024 * 1024
_CSV_LIMIT = 128 * 1024


def _fail(code: str) -> None:
    raise LeagueError(code, _MESSAGES[code])


def _fields(value: object, expected: tuple[str, ...], code: str = "INVALID_LEAGUE") -> None:
    if type(value) is not dict:
        _fail(code)
    if any(type(key) is not str for key in value) or set(value) != set(expected):
        _fail(code)


def _name(value: object, limit: int) -> str:
    if type(value) is not str or not 1 <= len(value) <= limit:
        _fail("INVALID_LEAGUE")
    if value != value.strip() or any(unicodedata.category(char).startswith("C") for char in value):
        _fail("INVALID_LEAGUE")
    return value


def _participants(value: object) -> list[dict]:
    if type(value) is not list or not 2 <= len(value) <= 32:
        _fail("INVALID_LEAGUE")
    result = []
    seen = set()
    for participant in value:
        _fields(participant, ("id", "name"))
        identifier = participant["id"]
        if type(identifier) is not str or _ID.fullmatch(identifier) is None or identifier in seen:
            _fail("INVALID_LEAGUE")
        seen.add(identifier)
        result.append({"id": identifier, "name": _name(participant["name"], 80)})
    return result


def _scoring(value: object) -> dict:
    _fields(value, ("win", "draw", "loss"))
    if any(type(value[key]) is not int or not 0 <= value[key] <= 1000 for key in ("win", "draw", "loss")):
        _fail("INVALID_LEAGUE")
    if not value["win"] > value["draw"] >= value["loss"]:
        _fail("INVALID_LEAGUE")
    return {key: value[key] for key in ("win", "draw", "loss")}


def _flag(value: object) -> bool:
    if type(value) is not bool:
        _fail("INVALID_LEAGUE")
    return value


def _score(home: object, away: object, code: str) -> dict:
    if any(type(value) is not int or not 0 <= value <= 999 for value in (home, away)):
        _fail(code)
    return {"home": home, "away": away}


def _calendar(participants: list[dict], double_round: bool) -> list[dict]:
    identifiers = [participant["id"] for participant in participants]
    if len(identifiers) % 2:
        identifiers.append(None)
    rounds = []
    size = len(identifiers)
    for index in range(size - 1):
        matches = []
        bye = None
        number = index + 1
        for position in range(size // 2):
            first, second = identifiers[position], identifiers[size - 1 - position]
            if first is None or second is None:
                bye = second if first is None else first
                continue
            home, away = (first, second) if (index + position) % 2 == 0 else (second, first)
            matches.append({
                "id": f"r{number:03d}-m{len(matches) + 1:03d}",
                "home": home, "away": away, "score": None,
            })
        rounds.append({"number": number, "matches": matches, "bye": bye})
        identifiers = [identifiers[0], identifiers[-1], *identifiers[1:-1]]
    if double_round:
        first_rounds = list(rounds)
        for original in first_rounds:
            number = len(rounds) + 1
            matches = [
                {"id": f"r{number:03d}-m{position:03d}", "home": match["away"],
                 "away": match["home"], "score": None}
                for position, match in enumerate(original["matches"], 1)
            ]
            rounds.append({"number": number, "matches": matches, "bye": original["bye"]})
    return rounds


def create_league(name, participants, *, double_round=False, scoring=None):
    """Cria uma liga e seu calendário circle method na ordem dos participantes."""
    clean_name = _name(name, 120)
    clean_participants = _participants(participants)
    clean_double = _flag(double_round)
    clean_scoring = _scoring({"win": 3, "draw": 1, "loss": 0} if scoring is None else scoring)
    return {
        "schema_version": 1, "name": clean_name, "participants": clean_participants,
        "double_round": clean_double, "scoring": clean_scoring,
        "rounds": _calendar(clean_participants, clean_double),
    }


def validate_league(doc):
    """Valida o modelo inteiro e devolve uma cópia em ordem canônica."""
    _fields(doc, ("schema_version", "name", "participants", "double_round", "scoring", "rounds"))
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        _fail("INVALID_LEAGUE")
    result = create_league(doc["name"], doc["participants"], double_round=doc["double_round"], scoring=_scoring(doc["scoring"]))
    actual_rounds = doc["rounds"]
    if type(actual_rounds) is not list or len(actual_rounds) != len(result["rounds"]):
        _fail("INVALID_LEAGUE")
    for actual_round, expected_round in zip(actual_rounds, result["rounds"]):
        _fields(actual_round, ("number", "matches", "bye"))
        if type(actual_round["number"]) is not int or actual_round["number"] != expected_round["number"]:
            _fail("INVALID_LEAGUE")
        bye = actual_round["bye"]
        if (bye is not None and type(bye) is not str) or bye != expected_round["bye"]:
            _fail("INVALID_LEAGUE")
        actual_matches = actual_round["matches"]
        if type(actual_matches) is not list or len(actual_matches) != len(expected_round["matches"]):
            _fail("INVALID_LEAGUE")
        for actual, expected in zip(actual_matches, expected_round["matches"]):
            _fields(actual, ("id", "home", "away", "score"))
            for key in ("id", "home", "away"):
                if type(actual[key]) is not str or actual[key] != expected[key]:
                    _fail("INVALID_LEAGUE")
            if actual["score"] is not None:
                _fields(actual["score"], ("home", "away"))
                expected["score"] = _score(actual["score"]["home"], actual["score"]["away"], "INVALID_LEAGUE")
    return result


def _matches(doc):
    for round_ in doc["rounds"]:
        yield from round_["matches"]


def _find_match(doc, match_id):
    if type(match_id) is not str:
        _fail("UNKNOWN_MATCH")
    for match in _matches(doc):
        if match["id"] == match_id:
            return match
    _fail("UNKNOWN_MATCH")


def set_result(doc, match_id, home_score, away_score, *, replace=False):
    """Registra um placar; trocar um resultado existente requer replace=True."""
    clean = validate_league(doc)
    _flag(replace)
    score = _score(home_score, away_score, "INVALID_SCORE")
    match = _find_match(clean, match_id)
    if match["score"] is not None and match["score"] != score and not replace:
        _fail("RESULT_EXISTS")
    match["score"] = score
    return clean


def clear_result(doc, match_id):
    """Remove o placar do jogo, inclusive quando ele já está pendente."""
    clean = validate_league(doc)
    _find_match(clean, match_id)["score"] = None
    return clean


def standings(doc):
    """Calcula a tabela parcial com classificação competitiva (1, 1, 3)."""
    clean = validate_league(doc)
    rows = {
        participant["id"]: {
            "id": participant["id"], "name": participant["name"], "played": 0,
            "won": 0, "drawn": 0, "lost": 0, "goals_for": 0,
            "goals_against": 0, "goal_difference": 0, "points": 0, "rank": 0,
        }
        for participant in clean["participants"]
    }
    scoring = clean["scoring"]
    for match in _matches(clean):
        score = match["score"]
        if score is None:
            continue
        home, away = rows[match["home"]], rows[match["away"]]
        for row, goals_for, goals_against in (
            (home, score["home"], score["away"]), (away, score["away"], score["home"]),
        ):
            row["played"] += 1
            row["goals_for"] += goals_for
            row["goals_against"] += goals_against
            row["goal_difference"] += goals_for - goals_against
            outcome = "won" if goals_for > goals_against else "lost" if goals_for < goals_against else "drawn"
            row[outcome] += 1
            row["points"] += scoring[{"won": "win", "drawn": "draw", "lost": "loss"}[outcome]]
    ordered = sorted(rows.values(), key=lambda row: (
        -row["points"], -row["goal_difference"], -row["goals_for"], -row["won"], row["id"],
    ))
    previous = None
    rank = 0
    for position, row in enumerate(ordered, 1):
        metrics = tuple(row[key] for key in ("points", "goal_difference", "goals_for", "won"))
        if metrics != previous:
            rank = position
        row["rank"] = rank
        previous = metrics
    return ordered


def progress(doc):
    """Conta partidas registradas e pendentes, sem contar as folgas."""
    clean = validate_league(doc)
    matches = list(_matches(clean))
    played = sum(match["score"] is not None for match in matches)
    return {
        "participants": len(clean["participants"]), "rounds": len(clean["rounds"]),
        "total_matches": len(matches), "played_matches": played,
        "pending_matches": len(matches) - played, "complete": played == len(matches),
    }


def fixtures(doc, round_number=None):
    """Lista jogos em ordem de calendário; placares pendentes são None."""
    clean = validate_league(doc)
    if round_number is not None and (type(round_number) is not int or not 1 <= round_number <= len(clean["rounds"])):
        _fail("INVALID_ROUND")
    names = {participant["id"]: participant["name"] for participant in clean["participants"]}
    rows = []
    for round_ in clean["rounds"]:
        if round_number is not None and round_["number"] != round_number:
            continue
        for match in round_["matches"]:
            score = match["score"]
            rows.append({
                "round": round_["number"], "match_id": match["id"],
                "home_id": match["home"], "home_name": names[match["home"]],
                "away_id": match["away"], "away_name": names[match["away"]],
                "home_score": None if score is None else score["home"],
                "away_score": None if score is None else score["away"],
            })
    return rows


def _transport(text, limit, code):
    if type(text) is not str or len(text) > limit:
        _fail(code)
    try:
        if len(text.encode("utf-8", errors="strict")) > limit:
            _fail(code)
    except UnicodeError:
        _fail(code)


def _json_depth(text):
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 12:
                _fail("INVALID_JSON")
        elif char in "]}":
            depth -= 1


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("INVALID_JSON")
        result[key] = value
    return result


def _json_constant(value):
    _fail("INVALID_JSON")


def loads_league(text):
    """Lê texto JSON estrito, com limites de tamanho e profundidade."""
    _transport(text, _JSON_LIMIT, "INVALID_JSON")
    if text.startswith("\ufeff"):
        _fail("INVALID_JSON")
    _json_depth(text)
    try:
        value = json.loads(text, object_pairs_hook=_json_object, parse_constant=_json_constant)
    except (ValueError, RecursionError):
        _fail("INVALID_JSON")
    return validate_league(value)


def dumps_league(doc):
    """Serializa a cópia canônica como JSON Unicode, indentado, com LF final."""
    clean = validate_league(doc)
    text = json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if loads_league(text) != clean:
        _fail("INVALID_JSON")
    return text


def _csv_rows(text):
    _transport(text, _CSV_LIMIT, "INVALID_CSV")
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        return list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (csv.Error, UnicodeError):
        _fail("INVALID_CSV")


def import_results_csv(doc, text, *, replace=False):
    """Importa resultados de uma só vez; nenhuma falha altera a liga recebida."""
    clean = validate_league(doc)
    _flag(replace)
    rows = _csv_rows(text)
    if not rows or rows[0] != ["match_id", "home_score", "away_score"] or len(rows) - 1 > 1000:
        _fail("INVALID_CSV")
    matches = {match["id"]: match for match in _matches(clean)}
    seen = set()
    changes = []
    for row in rows[1:]:
        if len(row) != 3:
            _fail("INVALID_CSV")
        match_id, home, away = row
        if match_id in seen:
            _fail("INVALID_CSV")
        seen.add(match_id)
        if match_id not in matches:
            _fail("UNKNOWN_MATCH")
        if home == "" and away == "":
            continue
        if _CSV_SCORE.fullmatch(home) is None or _CSV_SCORE.fullmatch(away) is None:
            _fail("INVALID_CSV")
        score = {"home": int(home), "away": int(away)}
        match = matches[match_id]
        if match["score"] is not None and match["score"] != score and not replace:
            _fail("RESULT_EXISTS")
        changes.append((match, score))
    if not changes:
        _fail("INVALID_CSV")
    for match, score in changes:
        match["score"] = score
    return clean


def _csv_output(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


def results_csv(doc):
    """Exporta todos jogos, deixando ambos placares vazios quando pendentes."""
    clean = validate_league(doc)
    rows = []
    for match in _matches(clean):
        score = match["score"]
        rows.append((match["id"], "" if score is None else score["home"], "" if score is None else score["away"]))
    return _csv_output(("match_id", "home_score", "away_score"), rows)


def _spreadsheet_string(value):
    if type(value) is str and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def standings_csv(doc):
    """Exporta a tabela com prefixo apóstrofo em strings sensíveis a planilhas."""
    return _csv_output(_TABLE_FIELDS, (
        [_spreadsheet_string(row[key]) for key in _TABLE_FIELDS] for row in standings(doc)
    ))
