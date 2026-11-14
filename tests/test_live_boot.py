"""Live-boot partition planner tests — safe, pure-logic (no disk operations)."""
import pytest

from core.live_boot import partition_planner as pp

GB = 1_000_000_000


def test_plan_128gb_structure():
    plan = pp.compute_plan(128 * GB)
    labels = [p.label for p in plan.partitions]
    assert labels == ["TITAN_EFI", "TITAN_BOOT", "TITAN_SYSTEM",
                      "TITAN_MODELS", "TITAN_WORKSPACE"]
    ws = plan.partitions[-1]
    assert ws.fs == "exFAT" and ws.windows_visible is True
    assert ws.size_gib > 40            # ~52-54 GiB on a 128 GB disk


def test_plan_sizes_fit_disk():
    plan = pp.compute_plan(128 * GB)
    allocated = sum(p.size_gib for p in plan.partitions) + plan.reserve_gib
    assert allocated <= plan.usable_gib + 0.5
    assert plan.reserve_gib >= 2.0


def test_plan_scales_on_small_disk():
    plan = pp.compute_plan(64 * GB)
    assert plan.scaled is True
    ws = plan.partitions[-1]
    assert ws.size_gib >= pp.MIN_WORKSPACE_GIB


def test_plan_rejects_tiny_disk():
    with pytest.raises(ValueError):
        pp.compute_plan(8 * GB)


# -- target classification -------------------------------------------------- #
def test_classify_refuses_system_disk():
    v = pp.classify_target(128 * GB, bus="usb", is_system_disk=True)
    assert v.safe is False
    assert any("system disk" in r for r in v.reasons)


def test_classify_refuses_non_usb():
    v = pp.classify_target(128 * GB, bus="nvme")
    assert v.safe is False
    assert any("not USB" in r for r in v.reasons)


def test_classify_usb_external_is_safe_with_warnings():
    v = pp.classify_target(128 * GB, bus="usb", is_system_disk=False,
                           model="Realtek RTL9210B-CG")
    assert v.safe is True
    # Always warns about trusting serial.
    assert any("serial" in w for w in v.warnings)


def test_classify_warns_unexpected_size():
    v = pp.classify_target(500 * GB, bus="usb")
    assert any("expected 128 GB window" in w for w in v.warnings)


def test_render_table():
    out = pp.render_plan_table(pp.compute_plan(128 * GB))
    assert "TITAN_WORKSPACE" in out and "usable" in out
