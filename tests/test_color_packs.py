"""Executable contract for the built-in semantic color packs."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError

import pytest

from sdr_grader.render.color_packs import (
    COLOR_PACK_CODES,
    COLOR_PACKS,
    NON_TEXT_CONTRAST_PAIRS,
    REQUIRED_COLOR_ROLES,
    TEXT_CONTRAST_PAIRS,
    ColorPack,
    InvalidColorPackError,
    color_pack_contract_snapshot,
    resolve_color_pack,
    serialize_color_pack_css,
)

EXPECTED_ROLES = (
    "surface-page",
    "surface-panel",
    "surface-subtle",
    "surface-emphasis",
    "text-primary",
    "text-muted",
    "text-inverse",
    "border-default",
    "border-strong",
    "focus-ring",
    "accent-primary",
    "accent-secondary",
    "component-metric",
    "component-dimension",
    "component-derived-field",
    "component-segment",
    "component-calculated-metric",
    "severity-critical",
    "severity-high",
    "severity-medium",
    "severity-low",
    "change-added",
    "change-modified",
    "change-removed",
    "chart-primary",
    "chart-secondary",
    "chart-grid",
    "chart-axis",
    "print-foreground",
    "print-background",
    "print-border",
)

EXPECTED_SOURCE_SWATCHES = {
    "default": (
        "#FAFAF7",
        "#FFFFFF",
        "#F5F3EB",
        "#ECE9E0",
        "#1A1A1A",
        "#6B6B66",
        "#C8C4B8",
        "#D8D6CF",
        "#8A8A82",
        "#4A6F6F",
        "#5E6B78",
        "#8A6A4A",
        "#B8651A",
        "#3D6B4F",
        "#8C4A3F",
    ),
    "ADBE": (
        "#ED2224",
        "#FBB034",
        "#FFDD00",
        "#C1D82F",
        "#00A4E4",
        "#8A7967",
        "#6A737B",
    ),
    "OMTR": ("#70A100", "#707070", "#000000", "#FFFFFF"),
    "BLUE": (
        "#001141",
        "#0043CE",
        "#0F62FE",
        "#78A9FF",
        "#D0E2FF",
        "#161616",
        "#FFFFFF",
    ),
}

EXPECTED_CONTRACT_SNAPSHOT = {
    "catalog": ("default", "ADBE", "OMTR", "BLUE"),
    "source_swatches": EXPECTED_SOURCE_SWATCHES,
    "required_roles": EXPECTED_ROLES,
    "text_contrast_pairs": TEXT_CONTRAST_PAIRS,
    "non_text_contrast_pairs": NON_TEXT_CONTRAST_PAIRS,
}


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _failing_contrast_pairs(roles, pairs, minimum):
    return [
        (foreground, background)
        for foreground, background in pairs
        if _contrast_ratio(roles[foreground], roles[background]) < minimum
    ]


def test_catalog_has_exact_public_identifiers_in_order():
    assert COLOR_PACK_CODES == ("default", "ADBE", "OMTR", "BLUE")
    assert tuple(COLOR_PACKS) == COLOR_PACK_CODES


def test_every_pack_defines_the_complete_shared_role_contract():
    assert REQUIRED_COLOR_ROLES == EXPECTED_ROLES
    for pack in COLOR_PACKS.values():
        assert tuple(pack.roles) == REQUIRED_COLOR_ROLES


def test_brand_source_swatches_are_exact_and_ordered():
    for code, expected in EXPECTED_SOURCE_SWATCHES.items():
        assert COLOR_PACKS[code].source_swatches == expected


def test_contract_snapshot_is_exact_json_compatible_public_metadata():
    snapshot = color_pack_contract_snapshot()

    assert snapshot == EXPECTED_CONTRACT_SNAPSHOT
    assert tuple(snapshot) == (
        "catalog",
        "source_swatches",
        "required_roles",
        "text_contrast_pairs",
        "non_text_contrast_pairs",
    )


def test_contract_snapshot_returns_fresh_copy_safe_nested_values():
    first = color_pack_contract_snapshot()
    second = color_pack_contract_snapshot()

    first["catalog"] = ("custom",)
    first["source_swatches"]["default"] = ("#000000",)
    first["required_roles"] = ()
    first["text_contrast_pairs"] = ()

    assert second == EXPECTED_CONTRACT_SNAPSHOT
    assert color_pack_contract_snapshot() == EXPECTED_CONTRACT_SNAPSHOT


def test_contrast_pair_contract_covers_status_text_and_control_boundaries():
    assert TEXT_CONTRAST_PAIRS == (
        ("text-primary", "surface-page"),
        ("text-primary", "surface-panel"),
        ("text-primary", "surface-emphasis"),
        ("text-muted", "surface-page"),
        ("text-muted", "surface-panel"),
        ("text-inverse", "accent-primary"),
        ("text-inverse", "accent-secondary"),
        ("severity-critical", "surface-panel"),
        ("severity-high", "surface-panel"),
        ("severity-medium", "surface-panel"),
        ("severity-low", "surface-panel"),
        ("print-foreground", "print-background"),
    )
    assert NON_TEXT_CONTRAST_PAIRS[:3] == (
        ("border-strong", "surface-page"),
        ("border-strong", "surface-panel"),
        ("focus-ring", "surface-page"),
    )


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_declared_text_pairs_meet_wcag_normal_text_contrast(code):
    roles = COLOR_PACKS[code].roles
    assert TEXT_CONTRAST_PAIRS
    assert _failing_contrast_pairs(roles, TEXT_CONTRAST_PAIRS, 4.5) == [], code


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_declared_non_text_pairs_meet_wcag_graphics_contrast(code):
    roles = COLOR_PACKS[code].roles
    assert NON_TEXT_CONTRAST_PAIRS
    assert _failing_contrast_pairs(roles, NON_TEXT_CONTRAST_PAIRS, 3.0) == [], code


def test_contrast_gate_detects_a_mutated_control_boundary():
    roles = dict(COLOR_PACKS["default"].roles)
    roles["border-strong"] = roles["border-default"]

    assert ("border-strong", "surface-panel") in _failing_contrast_pairs(
        roles, NON_TEXT_CONTRAST_PAIRS, 3.0
    )


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_brand_accents_are_distinct_from_status_roles(code):
    roles = COLOR_PACKS[code].roles
    status_roles = tuple(
        role for role in REQUIRED_COLOR_ROLES if role.startswith(("severity-", "change-"))
    )

    for accent_role in ("accent-primary", "accent-secondary"):
        collisions = [
            status_role for status_role in status_roles if roles[accent_role] == roles[status_role]
        ]
        assert not collisions, (code, accent_role, collisions)


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_css_serialization_is_stable_and_uses_only_contract_names_and_hexes(code):
    pack = resolve_color_pack(code)
    first = serialize_color_pack_css(pack)
    second = serialize_color_pack_css(pack)

    assert first == second
    assert first.startswith(":root {\n")
    assert first.endswith("\n}\n")
    declarations = re.findall(r"^  --sdr-([a-z0-9-]+): (#[0-9A-F]{6});$", first, re.MULTILINE)
    assert tuple(name for name, _value in declarations) == REQUIRED_COLOR_ROLES
    assert dict(declarations) == dict(pack.roles)
    assert len(first.splitlines()) == len(REQUIRED_COLOR_ROLES) + 2


@pytest.mark.parametrize("code", ["adbe", "blue", "Default", "", "unknown", None])
def test_resolver_rejects_unknown_and_case_mismatched_codes_with_catalog(code):
    with pytest.raises(
        InvalidColorPackError,
        match=r"available color packs: default, ADBE, OMTR, BLUE",
    ):
        resolve_color_pack(code)


@pytest.mark.parametrize("code", COLOR_PACK_CODES)
def test_resolver_returns_canonical_pack_without_creating_partial_state(code):
    assert resolve_color_pack(code) is COLOR_PACKS[code]


def test_registry_and_nested_pack_values_are_immutable():
    pack = COLOR_PACKS["ADBE"]

    with pytest.raises(TypeError):
        COLOR_PACKS["custom"] = pack
    with pytest.raises(TypeError):
        pack.roles["accent-primary"] = "#000000"
    with pytest.raises(FrozenInstanceError):
        pack.code = "custom"


def test_pack_construction_copies_mutable_inputs_before_freezing_them():
    roles = dict(COLOR_PACKS["default"].roles)
    source_swatches = list(COLOR_PACKS["default"].source_swatches)

    pack = ColorPack("custom", source_swatches, roles)
    roles["surface-page"] = "#000000"
    source_swatches[0] = "#000000"

    assert pack.roles["surface-page"] == "#FAFAF7"
    assert pack.source_swatches[0] == "#FAFAF7"


@pytest.mark.parametrize("code", ["", None])
def test_pack_construction_rejects_invalid_codes(code):
    with pytest.raises(ValueError, match="code must be a non-empty string"):
        ColorPack(code, ("#FFFFFF",), COLOR_PACKS["default"].roles)


def test_pack_construction_rejects_empty_or_non_normalized_source_swatches():
    roles = COLOR_PACKS["default"].roles

    with pytest.raises(ValueError, match="must define source swatches"):
        ColorPack("custom", (), roles)
    with pytest.raises(ValueError, match="normalized #RRGGBB"):
        ColorPack("custom", ("#ffffff",), roles)
    with pytest.raises(ValueError, match="normalized #RRGGBB"):
        ColorPack("custom", (None,), roles)


def test_pack_construction_rejects_missing_extra_or_misordered_roles():
    roles = dict(COLOR_PACKS["default"].roles)
    roles.pop("print-border")
    roles["extra-role"] = "#FFFFFF"

    with pytest.raises(ValueError, match=r"missing=\['print-border'\].*extra=\['extra-role'\]"):
        ColorPack("custom", ("#FFFFFF",), roles)

    reversed_roles = dict(reversed(COLOR_PACKS["default"].roles.items()))
    with pytest.raises(ValueError, match="canonical order"):
        ColorPack("custom", ("#FFFFFF",), reversed_roles)


def test_pack_construction_rejects_non_normalized_role_values():
    roles = dict(COLOR_PACKS["default"].roles)
    roles["surface-page"] = "#fafaf7"
    with pytest.raises(ValueError, match="normalized #RRGGBB"):
        ColorPack("custom", ("#FFFFFF",), roles)
