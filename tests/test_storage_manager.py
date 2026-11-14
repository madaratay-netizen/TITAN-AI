"""Storage / Workspace Manager tests — structure, exFAT-safe names, the reserve
gate, atomic writes, backup/restore, and availability detection.
"""
import pytest

from core.storage_manager.manager import (
    WorkspaceManager, WorkspaceUnavailable, InsufficientSpace,
    safe_filename, STANDARD_DIRS)


# -- filenames (exFAT / Windows safety) ------------------------------------- #
def test_safe_filename_strips_invalid():
    assert safe_filename('a<b>c:d"e/f\\g|h?i*j.txt') == "a_b_c_d_e_f_g_h_i_j.txt"


def test_safe_filename_trailing_dot_space():
    assert safe_filename("report. ") == "report"
    assert not safe_filename("x ").endswith(" ")


def test_safe_filename_reserved():
    assert safe_filename("CON").startswith("_")
    assert safe_filename("con.txt").startswith("_con")


def test_safe_filename_empty_default():
    assert safe_filename("") == "untitled"
    assert safe_filename("///") != ""


def test_safe_filename_length():
    assert len(safe_filename("x" * 500 + ".png")) <= 200


# -- structure -------------------------------------------------------------- #
def test_ensure_structure_creates_all(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    created = wm.ensure_structure()
    assert set(created) == set(STANDARD_DIRS)
    for d in STANDARD_DIRS:
        assert (tmp_path / "ws" / d).is_dir()
    # Idempotent: second call creates nothing.
    assert wm.ensure_structure() == []


# -- health ----------------------------------------------------------------- #
def test_health_ok(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    h = wm.health()
    assert h.exists and h.writable
    assert h.status in ("ok", "low_space")      # depends on the test disk
    assert len(h.subdirs) == len(STANDARD_DIRS)


def test_health_unavailable(tmp_path):
    wm = WorkspaceManager(tmp_path / "does_not_exist")
    h = wm.health()
    assert h.available is False and h.status == "unavailable"


# -- reserve gate ----------------------------------------------------------- #
def test_check_space_refuses_huge(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    # Ask for an absurd amount — must be refused against the reserve.
    res = wm.check_space(10 ** 15)  # ~1 PB
    assert res["ok"] is False and "reserve" in res["reason"]


def test_check_space_allows_small(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    assert wm.check_space(1024).get("ok") is True


# -- atomic write ----------------------------------------------------------- #
def test_safe_write_atomic(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    path = wm.safe_write("Images", "my pic.png", b"\x89PNG data")
    assert path.endswith("my pic.png")
    with open(path, "rb") as f:
        assert f.read() == b"\x89PNG data"
    # No leftover temp files.
    leftovers = list((tmp_path / "ws" / "Images").glob(".titan_tmp_*"))
    assert leftovers == []


def test_safe_write_unknown_category_goes_to_exports(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    path = wm.safe_write("NotACategory", "x.txt", b"hi")
    assert "Exports" in path


def test_safe_write_refused_when_unavailable(tmp_path):
    wm = WorkspaceManager(tmp_path / "missing")
    with pytest.raises(WorkspaceUnavailable):
        wm.safe_write("Images", "x.png", b"data")


# -- backup / restore ------------------------------------------------------- #
def test_backup_and_restore(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    (wm.root / "User_Settings" / "prefs.json").write_text('{"theme":"dark"}', encoding="utf-8")
    backup = wm.backup_settings()
    assert backup.endswith(".zip")
    # Remove the setting, then restore.
    (wm.root / "User_Settings" / "prefs.json").unlink()
    restored = wm.restore_settings(backup)
    assert any("prefs.json" in r for r in restored)
    assert (wm.root / "User_Settings" / "prefs.json").exists()


def test_restore_rejects_missing(tmp_path):
    wm = WorkspaceManager(tmp_path / "ws")
    wm.ensure_structure()
    with pytest.raises(Exception):
        wm.restore_settings(str(tmp_path / "nope.zip"))
