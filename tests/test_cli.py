"""Public integration tests for local CLI workflows and file integrity."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from liga_local import create_league, dumps_league
from liga_local.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="liga-local-public-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.participants = self.directory / "participantes.csv"
        self.participants.write_text(
            "id,name\na,Aurora\nb,Brisa\nc,Cedro\nd,Duna\n", encoding="utf-8"
        )
        self.league = self.directory / "liga.json"
        entry = os.environ.get("LIGA_LOCAL_CLI")
        self.command = [entry] if entry else [sys.executable, "-m", "liga_local"]

    def run_cli(self, *arguments, expected=0):
        result = subprocess.run(
            [*self.command, *map(str, arguments)],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
            cwd=self.directory,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if expected == 0:
            self.assertEqual(result.stderr, "")
        else:
            self.assertEqual(result.stdout, "")
        return result

    def create(self, *options):
        result = self.run_cli(
            "criar", "--nome", "Copa Fictícia", "--participantes", self.participants,
            "--saida", self.league, *options,
        )
        self.assertEqual(result.stdout, "")
        return json.loads(self.league.read_text(encoding="utf-8"))

    def test_create_reports_and_module_entrypoint(self):
        doc = self.create()
        self.assertEqual(len(doc["rounds"]), 3)
        checked = self.run_cli("verificar", self.league)
        self.assertEqual(json.loads(checked.stdout)["pending_matches"], 6)
        self.assertTrue(checked.stdout.endswith("\n"))
        table = self.run_cli("tabela", self.league)
        self.assertIn("Parcial", table.stdout)
        self.assertIn("Aurora", table.stdout)
        games = self.run_cli("jogos", self.league, "--rodada", "1", "--formato", "json")
        self.assertEqual(len(json.loads(games.stdout)), 2)
        module = subprocess.run(
            [sys.executable, "-m", "liga_local", "verificar", str(self.league)],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        self.assertEqual(module.returncode, 0, module.stderr)
        self.assertEqual(module.stdout, checked.stdout)

    def test_result_conflict_replace_clear_preserve_input(self):
        self.create()
        original = self.league.read_bytes()
        result_path = self.directory / "resultado.json"
        self.run_cli("resultado", self.league, "--jogo", "r001-m001", "--casa", "2",
                     "--fora", "0", "--saida", result_path)
        self.assertEqual(self.league.read_bytes(), original)
        failed = self.directory / "recusada.json"
        error = self.run_cli("resultado", result_path, "--jogo", "r001-m001", "--casa", "0",
                             "--fora", "0", "--saida", failed, expected=2)
        self.assertIn("RESULT_EXISTS", error.stderr)
        self.assertFalse(failed.exists())
        replaced = self.directory / "substituida.json"
        self.run_cli("resultado", result_path, "--jogo", "r001-m001", "--casa", "0",
                     "--fora", "0", "--substituir", "--saida", replaced)
        cleared = self.directory / "limpa.json"
        self.run_cli("limpar-resultado", replaced, "--jogo", "r001-m001", "--saida", cleared)
        checked = json.loads(self.run_cli("verificar", cleared).stdout)
        self.assertEqual(checked["played_matches"], 0)

    def test_csv_import_is_integral_and_model_is_reimportable(self):
        self.create()
        source = self.league.read_bytes()
        imported = self.directory / "resultados.csv"
        imported.write_text(
            "match_id,home_score,away_score\nr001-m001,2,0\nr001-m002,1,\n", encoding="utf-8"
        )
        destination = self.directory / "atualizada.json"
        result = self.run_cli("importar-resultados", self.league, imported, "--saida", destination, expected=2)
        self.assertIn("INVALID_CSV", result.stderr)
        self.assertFalse(destination.exists())
        self.assertEqual(self.league.read_bytes(), source)
        imported.write_text(
            "match_id,home_score,away_score\nr001-m001,2,0\nr001-m002,,\n", encoding="utf-8"
        )
        self.run_cli("importar-resultados", self.league, imported, "--saida", destination)
        template = self.directory / "modelo.csv"
        self.run_cli("modelo-resultados", destination, "--saida", template)
        repeat = self.directory / "reimportada.json"
        self.run_cli("importar-resultados", destination, template, "--saida", repeat)
        self.assertEqual(destination.read_bytes(), repeat.read_bytes())

    def test_named_output_never_overwrites_files_directories_or_symlinks(self):
        self.create()
        original = self.league.read_bytes()
        victim = self.directory / "existente.txt"
        victim.write_bytes(b"preservar\x00bytes")
        output_directory = self.directory / "diretorio"
        output_directory.mkdir()
        link = self.directory / "link"
        link.symlink_to(victim)
        dangling = self.directory / "link-sem-alvo"
        dangling.symlink_to(self.directory / "ausente")
        for destination in (victim, output_directory, link, dangling, self.league):
            with self.subTest(destination=destination.name):
                result = self.run_cli("tabela", self.league, "--saida", destination, expected=2)
                self.assertIn("OUTPUT_EXISTS", result.stderr)
        self.assertEqual(victim.read_bytes(), b"preservar\x00bytes")
        self.assertEqual(self.league.read_bytes(), original)
        self.assertTrue(link.is_symlink())
        self.assertTrue(dangling.is_symlink())
        self.assertEqual(list(output_directory.iterdir()), [])
        self.assertFalse(any(p.name.startswith(".liga-local-") for p in self.directory.iterdir()))

    def test_final_input_symlink_fifo_and_directory_are_rejected_without_wait(self):
        self.create()
        link = self.directory / "entrada-link"
        link.symlink_to(self.league)
        fifo = self.directory / "entrada-fifo"
        os.mkfifo(fifo)
        for source in (link, fifo, self.directory):
            with self.subTest(source=source.name):
                result = self.run_cli("verificar", source, expected=2)
                self.assertIn("IO_ERROR", result.stderr)

    def test_explicit_parent_symlink_is_accepted(self):
        self.create()
        parent = self.directory / "alias"
        parent.symlink_to(self.directory, target_is_directory=True)
        checked = self.run_cli("verificar", parent / self.league.name)
        self.assertEqual(json.loads(checked.stdout)["total_matches"], 6)
        self.run_cli("tabela", self.league, "--saida", parent / "tabela.txt")
        self.assertTrue((self.directory / "tabela.txt").is_file())

    def test_participants_structure_bom_and_model_validation(self):
        self.participants.write_bytes(b"\xef\xbb\xbfid,name\na,Aurora\nb,Brisa\n")
        self.create()
        for index, content in enumerate((
            "name,id\nAurora,a\nBrisa,b\n",
            "id,name\na,Aurora,extra\nb,Brisa\n",
            "id,name\na,Aurora\n\nb,Brisa\n",
        )):
            self.participants.write_text(content, encoding="utf-8")
            destination = self.directory / f"invalida-{index}.json"
            result = self.run_cli("criar", "--nome", "Copa", "--participantes", self.participants,
                                  "--saida", destination, expected=2)
            self.assertIn("INVALID_CSV", result.stderr)
            self.assertFalse(destination.exists())
        self.participants.write_text("id,name\na,Aurora\na,Brisa\n", encoding="utf-8")
        result = self.run_cli("criar", "--nome", "Copa", "--participantes", self.participants,
                              "--saida", self.directory / "duplicados.json", expected=2)
        self.assertIn("INVALID_LEAGUE", result.stderr)

    def test_csv_reports_quote_formula_strings_and_keep_numbers(self):
        doc = create_league("Copa", [{"id": "a", "name": "=SUM(1,2)"}, {"id": "b", "name": "Brisa"}])
        self.league.write_text(dumps_league(doc), encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(self.run_cli("tabela", self.league, "--formato", "csv").stdout)))
        self.assertEqual(rows[0]["name"], "'=SUM(1,2)")
        self.assertEqual(rows[0]["points"], "0")
        games = self.run_cli("jogos", self.league, "--formato", "csv").stdout
        game_rows = list(csv.DictReader(io.StringIO(games)))
        self.assertEqual(game_rows[0]["home_name"], "'=SUM(1,2)")
        self.assertEqual(game_rows[0]["home_score"], "")
        self.assertEqual(game_rows[0]["away_score"], "")
        self.assertTrue(games.endswith("\n"))

    def test_text_distinguishes_bye_pending_and_nil_draw(self):
        doc = create_league("Copa", [
            {"id": "a", "name": "Aurora"}, {"id": "b", "name": "Brisa"},
            {"id": "c", "name": "Cedro"},
        ])
        self.league.write_text(dumps_league(doc), encoding="utf-8")
        text = self.run_cli("jogos", self.league).stdout
        self.assertIn("Folga:", text)
        self.assertIn("pendente", text)
        result_path = self.directory / "empate.json"
        self.run_cli("resultado", self.league, "--jogo", "r001-m001", "--casa", "0",
                     "--fora", "0", "--saida", result_path)
        text = self.run_cli("jogos", result_path).stdout
        self.assertIn("0 a 0", text)
        self.assertIn("pendente", text)
        self.assertIn("Parcial", text)

    def test_input_limits_encoding_and_argument_errors_are_short(self):
        self.create()
        secret = "segredo-que-nao-deve-aparecer"
        self.league.write_text('{"' + secret + '": 1}', encoding="utf-8")
        result = self.run_cli("verificar", self.league, expected=2)
        self.assertNotIn(secret, result.stderr)
        self.league.write_bytes(b"\xff")
        self.assertIn("INVALID_JSON", self.run_cli("verificar", self.league, expected=2).stderr)
        self.league.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        self.assertIn("INVALID_JSON", self.run_cli("verificar", self.league, expected=2).stderr)
        self.participants.write_bytes(b" " * (128 * 1024 + 1))
        result = self.run_cli("criar", "--nome", "Copa", "--participantes", self.participants,
                              "--saida", self.directory / "grande.json", expected=2)
        self.assertIn("INVALID_CSV", result.stderr)
        result = self.run_cli(secret, expected=2)
        self.assertNotIn(secret, result.stderr)

    def test_invalid_score_round_and_unknown_match_codes(self):
        self.create()
        for score in ("-1", "1.5", "1000", "９", "9" * 5000):
            result = self.run_cli("resultado", self.league, "--jogo", "r001-m001", "--casa=" + score,
                                  "--fora", "0", "--saida", self.directory / "erro.json", expected=2)
            self.assertIn("INVALID_SCORE", result.stderr)
        for round_number in ("0", "4", "-1", "1.5"):
            self.assertIn("INVALID_ROUND", self.run_cli("jogos", self.league,
                          "--rodada=" + round_number, expected=2).stderr)
        result = self.run_cli("limpar-resultado", self.league, "--jogo", "desconhecido",
                              "--saida", self.directory / "erro.json", expected=2)
        self.assertIn("UNKNOWN_MATCH", result.stderr)

    def test_publication_failures_cleanup_own_temporary_and_preserve_others(self):
        self.create()
        unrelated = self.directory / ".liga-local-alheio.tmp"
        unrelated.write_bytes(b"outro processo")
        destination = self.directory / "falha.txt"
        for operation in ("os.link", "os.fsync"):
            with self.subTest(operation=operation), patch("liga_local.cli." + operation, side_effect=OSError), \
                    redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                result = main(["tabela", str(self.league), "--saida", str(destination)])
            self.assertEqual(result, 2)
            self.assertIn("IO_ERROR", stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")
            self.assertFalse(destination.exists())
            self.assertEqual(unrelated.read_bytes(), b"outro processo")
            self.assertEqual(sorted(p.name for p in self.directory.glob(".liga-local-*")), [unrelated.name])

    def test_broken_stdout_pipe_exits_two_without_shutdown_traceback(self):
        self.create()
        read_descriptor, write_descriptor = os.pipe()
        os.close(read_descriptor)
        try:
            result = subprocess.run(
                [*self.command, "verificar", str(self.league)],
                stdout=write_descriptor, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", timeout=5,
            )
        finally:
            os.close(write_descriptor)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("IO_ERROR", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("BrokenPipeError", result.stderr)


if __name__ == "__main__":
    unittest.main()
