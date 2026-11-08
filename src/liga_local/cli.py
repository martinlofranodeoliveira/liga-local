"""Interface local de arquivos para o motor puro de campeonatos."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Sequence

from . import (
    LeagueError,
    clear_result,
    create_league,
    dumps_league,
    fixtures,
    import_results_csv,
    loads_league,
    progress,
    results_csv,
    set_result,
    standings,
    standings_csv,
)

_JSON_LIMIT = 2 * 1024 * 1024
_CSV_LIMIT = 128 * 1024
_FIXTURE_KEYS = (
    "round", "match_id", "home_id", "home_name", "away_id", "away_name",
    "home_score", "away_score",
)
_INTEGER = re.compile(r"[0-9]+", re.ASCII)


class _CLIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's normal errors may include user supplied paths or values.
        raise _CLIError("INVALID_LEAGUE", "Argumentos inválidos; consulte --help.")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="liga-local",
        description="Organize campeonatos de pontos corridos com arquivos locais.",
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("criar", help="Criar liga a partir de CSV id,name.")
    create.add_argument("--nome", required=True, metavar="NOME")
    create.add_argument("--participantes", required=True, metavar="CSV")
    create.add_argument("--saida", required=True, metavar="ARQUIVO")
    create.add_argument("--turno-returno", action="store_true")
    create.add_argument("--pontos-vitoria", default="3", metavar="N")
    create.add_argument("--pontos-empate", default="1", metavar="N")
    create.add_argument("--pontos-derrota", default="0", metavar="N")

    for command, help_text in (
        ("tabela", "Exibir classificação parcial ou concluída."),
        ("jogos", "Exibir jogos e folgas do calendário."),
    ):
        report = commands.add_parser(command, help=help_text)
        report.add_argument("liga", metavar="LIGA_JSON")
        report.add_argument("--formato", choices=("texto", "csv", "json"), default="texto")
        report.add_argument("--saida", metavar="ARQUIVO")
        if command == "jogos":
            report.add_argument("--rodada", metavar="N")

    template = commands.add_parser("modelo-resultados", help="Exportar CSV de resultados.")
    template.add_argument("liga", metavar="LIGA_JSON")
    template.add_argument("--saida", metavar="ARQUIVO")

    result = commands.add_parser("resultado", help="Registrar um resultado.")
    result.add_argument("liga", metavar="LIGA_JSON")
    result.add_argument("--jogo", required=True, metavar="ID")
    result.add_argument("--casa", required=True, metavar="N")
    result.add_argument("--fora", required=True, metavar="N")
    result.add_argument("--saida", required=True, metavar="ARQUIVO")
    result.add_argument("--substituir", action="store_true")

    imported = commands.add_parser("importar-resultados", help="Importar resultados de um CSV.")
    imported.add_argument("liga", metavar="LIGA_JSON")
    imported.add_argument("resultados", metavar="RESULTADOS_CSV")
    imported.add_argument("--saida", required=True, metavar="ARQUIVO")
    imported.add_argument("--substituir", action="store_true")

    cleared = commands.add_parser("limpar-resultado", help="Remover explicitamente um placar.")
    cleared.add_argument("liga", metavar="LIGA_JSON")
    cleared.add_argument("--jogo", required=True, metavar="ID")
    cleared.add_argument("--saida", required=True, metavar="ARQUIVO")

    checked = commands.add_parser("verificar", help="Validar liga e emitir progresso em JSON.")
    checked.add_argument("liga", metavar="LIGA_JSON")
    return parser


def _integer(text: str, code: str, maximum: int) -> int:
    # Bound length before int(): very long input must also be a controlled error.
    if len(text) > 10 or _INTEGER.fullmatch(text) is None:
        raise _CLIError(code, "Número inteiro fora do formato permitido.")
    value = int(text)
    if value > maximum:
        raise _CLIError(code, "Número inteiro fora do intervalo permitido.")
    return value


def _read_utf8(path: str, limit: int, transport_code: str) -> str:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise _CLIError("IO_ERROR", "Leitura segura não disponível neste sistema.")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _CLIError("IO_ERROR", "A entrada deve ser um arquivo regular.")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except (OSError, ValueError):
        raise _CLIError("IO_ERROR", "Não foi possível ler o arquivo de entrada.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > limit:
        raise _CLIError(transport_code, "Arquivo de entrada excede o limite permitido.")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise _CLIError(transport_code, "Arquivo de entrada deve usar UTF-8 válido.") from None


def _participants(text: str) -> list[dict[str, str]]:
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != ["id", "name"]:
            raise _CLIError("INVALID_CSV", "Cabeçalho de participantes inválido.")
        participants = []
        for row in reader:
            if len(row) != 2 or len(participants) >= 32:
                raise _CLIError("INVALID_CSV", "Estrutura de participantes inválida.")
            participants.append({"id": row[0], "name": row[1]})
        return participants
    except csv.Error:
        raise _CLIError("INVALID_CSV", "CSV de participantes inválido.") from None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _spreadsheet_cell(value: object) -> object:
    if type(value) is str and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _fixtures_csv(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_FIXTURE_KEYS)
    for row in rows:
        writer.writerow([_spreadsheet_cell(row[key]) for key in _FIXTURE_KEYS])
    return output.getvalue()


def _status(doc: dict) -> str:
    return "Concluída" if progress(doc)["complete"] else "Parcial"


def _standings_text(doc: dict, rows: list[dict]) -> str:
    lines = [f"Liga: {doc['name']}", f"Tabela {_status(doc)}", "", "Pos | Participante (ID) | J | V | E | D | GP | GC | SG | Pts"]
    for row in rows:
        label = f"{row['name']} ({row['id']})"
        values = [row["rank"], label, *[row[key] for key in (
            "played", "won", "drawn", "lost", "goals_for", "goals_against",
            "goal_difference", "points",
        )]]
        lines.append(" | ".join(str(value) for value in values))
    return "\n".join(lines) + "\n"


def _fixtures_text(doc: dict, rows: list[dict], round_number: int | None) -> str:
    names = {participant["id"]: participant["name"] for participant in doc["participants"]}
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["round"], []).append(row)
    lines = [f"Liga: {doc['name']}", f"Jogos — {_status(doc)}"]
    for round_doc in doc["rounds"]:
        number = round_doc["number"]
        if round_number is not None and number != round_number:
            continue
        lines.extend(("", f"Rodada {number}"))
        for row in grouped.get(number, []):
            score = "pendente" if row["home_score"] is None else f"{row['home_score']} a {row['away_score']}"
            lines.append(
                f"{row['match_id']}: {row['home_name']} ({row['home_id']}) x "
                f"{row['away_name']} ({row['away_id']}): {score}"
            )
        bye = round_doc["bye"]
        if bye is not None:
            lines.append(f"Folga: {names[bye]} ({bye})")
    return "\n".join(lines) + "\n"


def _publish(path: str, content: str) -> None:
    """Publish a complete private temporary file with a no-overwrite hard link."""
    data = content.encode("utf-8")
    temporary = None
    descriptor = None
    try:
        if os.path.lexists(path):
            raise _CLIError("OUTPUT_EXISTS", "O destino já existe.")
        parent = os.path.dirname(path) or "."
        descriptor, temporary = tempfile.mkstemp(prefix=".liga-local-", suffix=".tmp", dir=parent)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            raise _CLIError("OUTPUT_EXISTS", "O destino já existe.") from None
    except OSError:
        raise _CLIError("IO_ERROR", "Não foi possível publicar a saída com segurança.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                raise _CLIError("IO_ERROR", "Não foi possível remover o temporário de saída.") from None


def _execute(args: argparse.Namespace) -> str:
    if args.command == "criar":
        participants = _participants(_read_utf8(args.participantes, _CSV_LIMIT, "INVALID_CSV"))
        scoring = {
            "win": _integer(args.pontos_vitoria, "INVALID_LEAGUE", 1000),
            "draw": _integer(args.pontos_empate, "INVALID_LEAGUE", 1000),
            "loss": _integer(args.pontos_derrota, "INVALID_LEAGUE", 1000),
        }
        return dumps_league(create_league(args.nome, participants, double_round=args.turno_returno, scoring=scoring))

    doc = loads_league(_read_utf8(args.liga, _JSON_LIMIT, "INVALID_JSON"))
    if args.command == "verificar":
        return _json(progress(doc))
    if args.command == "resultado":
        home = _integer(args.casa, "INVALID_SCORE", 999)
        away = _integer(args.fora, "INVALID_SCORE", 999)
        return dumps_league(set_result(doc, args.jogo, home, away, replace=args.substituir))
    if args.command == "limpar-resultado":
        return dumps_league(clear_result(doc, args.jogo))
    if args.command == "importar-resultados":
        imported = _read_utf8(args.resultados, _CSV_LIMIT, "INVALID_CSV")
        return dumps_league(import_results_csv(doc, imported, replace=args.substituir))
    if args.command == "modelo-resultados":
        return results_csv(doc)
    if args.command == "tabela":
        if args.formato == "csv":
            return standings_csv(doc)
        rows = standings(doc)
        return _json(rows) if args.formato == "json" else _standings_text(doc, rows)
    round_number = None if args.rodada is None else _integer(args.rodada, "INVALID_ROUND", 1000)
    rows = fixtures(doc, round_number=round_number)
    if args.formato == "csv":
        return _fixtures_csv(rows)
    if args.formato == "json":
        return _json(rows)
    return _fixtures_text(doc, rows, round_number)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; errors contain stable codes and never echo input data."""
    try:
        args = _parser().parse_args(argv)
        output = _execute(args)
        if getattr(args, "saida", None) is not None:
            _publish(args.saida, output)
        else:
            sys.stdout.write(output)
            sys.stdout.flush()
        return 0
    except (_CLIError, LeagueError) as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # The buffered stream is flushed again during interpreter shutdown.
        # Redirect its descriptor so that shutdown cannot turn exit 2 into 120.
        descriptor = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(descriptor, sys.stdout.fileno())
        finally:
            os.close(descriptor)
        print("IO_ERROR: Não foi possível concluir a operação de entrada ou saída.", file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print("IO_ERROR: Não foi possível concluir a operação de entrada ou saída.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
