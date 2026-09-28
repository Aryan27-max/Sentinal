import os
from pathlib import Path

from app.parser import parse_line
from app.tailer import Tailer

LINE = (
    "2026-09-28T15:21:04.123Z level=ERROR service=payment-service latency_ms=5012 "
    'msg="DB timeout host=db-2"'
)


def test_appends_and_partial_line(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"")
    tailer = Tailer(log)
    with open(log, "ab") as f:
        f.write(b"one\ntw")
    assert tailer.read_new_lines() == ["one"]
    with open(log, "ab") as f:
        f.write(b"o\nthree\n")
    assert tailer.read_new_lines() == ["two", "three"]


def test_starts_at_end_unless_from_start(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"old\n")
    assert Tailer(log).read_new_lines() == []
    assert Tailer(log, from_start=True).read_new_lines() == ["old"]


def test_truncation_resets_offset(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"")
    tailer = Tailer(log)
    log.write_bytes(b"aaaaaaaaaa\n")
    assert tailer.read_new_lines() == ["aaaaaaaaaa"]
    log.write_bytes(b"b\n")  # truncate and rewrite, shorter than the offset
    assert tailer.read_new_lines() == ["b"]


def test_rotation_reads_new_file_from_start(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_bytes(b"")
    tailer = Tailer(log)
    log.write_bytes(b"before rotation, a long line\n")
    assert tailer.read_new_lines() == ["before rotation, a long line"]
    os.rename(log, tmp_path / "app.log.1")  # works on Windows because no handle is held
    log.write_bytes(b"new file line\n")
    assert tailer.read_new_lines() == ["new file line"]


def test_parser_valid_line() -> None:
    ev = parse_line(LINE)
    assert ev is not None
    assert (ev.level, ev.service, ev.latency_ms) == ("ERROR", "payment-service", 5012.0)
    assert ev.msg == "DB timeout host=db-2"
    assert ev.is_error


def test_parser_rejects_garbage() -> None:
    for bad in ["", "garbage", "not-a-date level=INFO service=x", "2026-09-28T15:21:04Z msg=hi"]:
        assert parse_line(bad) is None
