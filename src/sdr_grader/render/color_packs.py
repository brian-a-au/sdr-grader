"""Immutable built-in semantic color packs for HTML rendering.

The registry is presentation-only: callers resolve one pack for one render
and serialize its reviewed literal values as CSS custom properties. Nothing in
this module mutates renderer state or enters the embedded report payload.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

REQUIRED_COLOR_ROLES = (
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

COLOR_PACK_CODES = ("default", "ADBE", "OMTR", "BLUE")

# This mapping and the two tuples above are deliberately literal declarations.
# The cross-repository parity check reads them with ast.literal_eval, so comparing
# a sibling checkout never imports or executes either repository's Python code.
_SOURCE_SWATCHES = {
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

# These pairs are the executable accessibility contract. Text pairs are for
# normal-size text (4.5:1); non-text pairs cover essential graphics (3:1).
TEXT_CONTRAST_PAIRS = (
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

NON_TEXT_CONTRAST_PAIRS = (
    ("border-strong", "surface-page"),
    ("border-strong", "surface-panel"),
    ("focus-ring", "surface-page"),
    ("accent-primary", "surface-page"),
    ("accent-secondary", "surface-page"),
    ("component-metric", "surface-panel"),
    ("component-dimension", "surface-panel"),
    ("component-derived-field", "surface-panel"),
    ("component-segment", "surface-panel"),
    ("component-calculated-metric", "surface-panel"),
    ("severity-critical", "surface-panel"),
    ("severity-high", "surface-panel"),
    ("severity-medium", "surface-panel"),
    ("severity-low", "surface-panel"),
    ("change-added", "surface-panel"),
    ("change-modified", "surface-panel"),
    ("change-removed", "surface-panel"),
    ("chart-primary", "surface-panel"),
    ("chart-secondary", "surface-panel"),
    ("chart-grid", "surface-panel"),
    ("chart-axis", "surface-panel"),
    ("print-border", "print-background"),
)

_NORMALIZED_HEX = re.compile(r"#[0-9A-F]{6}\Z")


class InvalidColorPackError(ValueError):
    """A requested color-pack identifier is not in the built-in catalog."""


@dataclass(frozen=True, slots=True)
class ColorPack:
    """One validated, deeply immutable color-pack definition."""

    code: str
    source_swatches: tuple[str, ...]
    roles: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("color-pack code must be a non-empty string")

        source_swatches = tuple(self.source_swatches)
        if not source_swatches:
            raise ValueError(f"color pack {self.code!r} must define source swatches")
        for color in source_swatches:
            _validate_hex(color, label=f"color pack {self.code!r} source swatch")

        roles = dict(self.roles)
        if tuple(roles) != REQUIRED_COLOR_ROLES:
            missing = [role for role in REQUIRED_COLOR_ROLES if role not in roles]
            extra = [role for role in roles if role not in REQUIRED_COLOR_ROLES]
            raise ValueError(
                f"color pack {self.code!r} must define roles in canonical order; "
                f"missing={missing!r}, extra={extra!r}"
            )
        for role, color in roles.items():
            _validate_hex(color, label=f"color pack {self.code!r} role {role!r}")

        object.__setattr__(self, "source_swatches", source_swatches)
        object.__setattr__(self, "roles", MappingProxyType(roles))


def _validate_hex(color: object, *, label: str) -> None:
    if not isinstance(color, str) or _NORMALIZED_HEX.fullmatch(color) is None:
        raise ValueError(f"{label} must be a normalized #RRGGBB value")


def _pack(
    code: str,
    source_swatches: tuple[str, ...],
    role_values: tuple[str, ...],
) -> ColorPack:
    return ColorPack(
        code=code,
        source_swatches=source_swatches,
        roles=dict(zip(REQUIRED_COLOR_ROLES, role_values, strict=True)),
    )


_DEFAULT = _pack(
    "default",
    _SOURCE_SWATCHES["default"],
    (
        "#FAFAF7",  # surface-page
        "#FFFFFF",  # surface-panel
        "#F5F3EB",  # surface-subtle
        "#ECE9E0",  # surface-emphasis
        "#1A1A1A",  # text-primary
        "#6B6B66",  # text-muted
        "#FFFFFF",  # text-inverse
        "#D8D6CF",  # border-default
        "#8A8A82",  # border-strong
        "#3A5E5E",  # focus-ring
        "#4A6F6F",  # accent-primary
        "#6A4F30",  # accent-secondary
        "#2A2A2A",  # component-metric
        "#4A6F6F",  # component-dimension
        "#5E6B78",  # component-derived-field
        "#8A6A4A",  # component-segment
        "#806A00",  # component-calculated-metric
        "#8C4A3F",  # severity-critical
        "#9C4F10",  # severity-high
        "#806A00",  # severity-medium
        "#3D6B4F",  # severity-low
        "#3D6B4F",  # change-added
        "#806A00",  # change-modified
        "#8C4A3F",  # change-removed
        "#1A1A1A",  # chart-primary
        "#4A6F6F",  # chart-secondary
        "#8A8A82",  # chart-grid
        "#6B6B66",  # chart-axis
        "#1A1A1A",  # print-foreground
        "#FFFFFF",  # print-background
        "#8A8A82",  # print-border
    ),
)

_ADBE = _pack(
    "ADBE",
    _SOURCE_SWATCHES["ADBE"],
    (
        "#FFFFFF",
        "#FFFFFF",
        "#FFF8F0",
        "#FFF1D6",
        "#1A1A1A",
        "#5F5A55",
        "#FFFFFF",
        "#CDC4BA",
        "#81766C",
        "#006A94",
        "#7C1320",
        "#006A94",
        "#B5121B",
        "#9C5700",
        "#7A6600",
        "#4E7000",
        "#006A94",
        "#B5121B",
        "#9C5700",
        "#7A6600",
        "#4E7000",
        "#4E7000",
        "#7A6600",
        "#B5121B",
        "#B5121B",
        "#006A94",
        "#81766C",
        "#5F5A55",
        "#1A1A1A",
        "#FFFFFF",
        "#81766C",
    ),
)

_OMTR = _pack(
    "OMTR",
    _SOURCE_SWATCHES["OMTR"],
    (
        "#FFFFFF",
        "#FFFFFF",
        "#F3F6EE",
        "#E5ECD9",
        "#000000",
        "#595959",
        "#FFFFFF",
        "#C6C6C6",
        "#707070",
        "#486A00",
        "#486A00",
        "#000000",
        "#486A00",
        "#595959",
        "#365000",
        "#707070",
        "#2E5D00",
        "#2A2A2A",
        "#4A4A4A",
        "#707070",
        "#365000",
        "#365000",
        "#595959",
        "#2A2A2A",
        "#486A00",
        "#595959",
        "#707070",
        "#4A4A4A",
        "#000000",
        "#FFFFFF",
        "#707070",
    ),
)

_BLUE = _pack(
    "BLUE",
    _SOURCE_SWATCHES["BLUE"],
    (
        "#FFFFFF",
        "#FFFFFF",
        "#F4F7FF",
        "#D0E2FF",
        "#161616",
        "#525252",
        "#FFFFFF",
        "#C6C6C6",
        "#6F6F6F",
        "#0F62FE",
        "#0043CE",
        "#0F62FE",
        "#001141",
        "#0043CE",
        "#0F62FE",
        "#315A9E",
        "#536E9A",
        "#001141",
        "#00266D",
        "#315A9E",
        "#536E9A",
        "#00266D",
        "#315A9E",
        "#001141",
        "#0043CE",
        "#0F62FE",
        "#6F6F6F",
        "#525252",
        "#161616",
        "#FFFFFF",
        "#6F6F6F",
    ),
)

COLOR_PACKS: Mapping[str, ColorPack] = MappingProxyType(
    {pack.code: pack for pack in (_DEFAULT, _ADBE, _OMTR, _BLUE)}
)


def resolve_color_pack(code: str) -> ColorPack:
    """Resolve one exact, case-sensitive built-in identifier without side effects."""
    if not isinstance(code, str) or code not in COLOR_PACKS:
        available = ", ".join(COLOR_PACK_CODES)
        raise InvalidColorPackError(
            f"unknown color pack {code!r}; available color packs: {available}"
        )
    return COLOR_PACKS[code]


def color_pack_contract_snapshot() -> dict[str, object]:
    """Return a copy-safe snapshot of the shared, source-only pack contract.

    Derived semantic role values are deliberately excluded: sibling parity is
    defined by the public catalog, reviewed source swatches, and role names.
    """
    return {
        "catalog": tuple(COLOR_PACK_CODES),
        "source_swatches": {code: tuple(_SOURCE_SWATCHES[code]) for code in COLOR_PACK_CODES},
        "required_roles": tuple(REQUIRED_COLOR_ROLES),
    }


def serialize_color_pack_css(pack: ColorPack) -> str:
    """Serialize a pack to a stable, self-contained CSS custom-property block."""
    declarations = [f"  --sdr-{role}: {pack.roles[role]};" for role in REQUIRED_COLOR_ROLES]
    return "\n".join((":root {", *declarations, "}", ""))


__all__ = [
    "COLOR_PACK_CODES",
    "COLOR_PACKS",
    "NON_TEXT_CONTRAST_PAIRS",
    "REQUIRED_COLOR_ROLES",
    "TEXT_CONTRAST_PAIRS",
    "ColorPack",
    "InvalidColorPackError",
    "color_pack_contract_snapshot",
    "resolve_color_pack",
    "serialize_color_pack_css",
]
