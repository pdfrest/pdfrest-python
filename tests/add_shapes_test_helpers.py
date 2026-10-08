"""Shared, single-field contract cases for mocked and live shape tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

import pytest

from pdfrest.types import PdfContentStructureType


def make_shape(shape_type: str, **overrides: object) -> dict[str, object]:
    if shape_type == "line":
        shape: dict[str, object] = {
            "type": "line",
            "page": 1,
            "x1": 72,
            "y1": 576,
            "x2": 540,
            "y2": 576,
            "stroke_color": (26, 72, 112),
            "stroke_width": 1.5,
        }
    else:
        shape = {
            "type": "rectangle",
            "page": 1,
            "x": 54,
            "y": 540,
            "width": 504,
            "height": 108,
            "fill_color": (0, 0, 0, 12),
            "opacity": 0.75,
        }
    shape.update(overrides)
    return shape


def server_shape(shape: dict[str, object]) -> dict[str, object]:
    """Independent expected wire object; do not derive it from the SDK model."""
    wire = dict(shape)
    for field in ("stroke_color", "fill_color"):
        color = wire.pop(field, None)
        if isinstance(color, tuple):
            color_space = "rgb" if len(color) == 3 else "cmyk"
            wire[f"{field}_{color_space}"] = ",".join(str(channel) for channel in color)
    return wire


@dataclass(frozen=True)
class ShapeBoundaryCase:
    shape: dict[str, object]
    field: str
    constraint: str = ""

    @property
    def local_match(self) -> str:
        return rf"(?s){self.field}.*{self.constraint}"

    @property
    def server_match(self) -> str:
        # Legacy server messages call both fill/stroke channels color_rgb/cmyk.
        field = "color" if self.field.endswith("color") else self.field
        return rf"(?i){field}"


def _numeric_cases(valid: bool) -> list[object]:
    cases = []
    for shape_type, coordinates, dimensions in (
        ("line", ("x1", "y1", "x2", "y2"), ()),
        ("rectangle", ("x", "y"), ("width", "height")),
    ):
        fields = {
            **dict.fromkeys(
                coordinates, ((0, 0.01), (-0.01,), "greater than or equal to 0")
            ),
            **dict.fromkeys(
                (*dimensions, "stroke_width"), ((0.01,), (0, -0.01), "greater than 0")
            ),
            "page": ((1, 2, "all"), (0,), "greater than or equal to 1"),
            "opacity": ((0, 0.01, 0.99, 1), (-0.01, 1.01), ""),
        }
        for field, (accepted, rejected, constraint) in fields.items():
            for value in accepted if valid else rejected:
                bound = constraint
                if field == "opacity":
                    assert isinstance(value, (int, float))
                    bound = (
                        "greater than or equal to 0"
                        if value < 0
                        else "less than or equal to 1"
                    )
                cases.append(
                    pytest.param(
                        ShapeBoundaryCase(
                            make_shape(shape_type, **{field: value}), field, bound
                        ),
                        id=f"{shape_type}-{field}-{value}",
                    )
                )
        for field in (
            ("stroke_color",)
            if shape_type == "line"
            else ("stroke_color", "fill_color")
        ):
            for count, maximum in ((3, 255), (4, 100)):
                for channel in range(count):
                    for value in (
                        (0, 1, maximum - 1, maximum) if valid else (-1, maximum + 1)
                    ):
                        color = tuple(
                            value if index == channel else 0 for index in range(count)
                        )
                        constraint = (
                            "greater than or equal to 0"
                            if value < 0
                            else f"less than or equal to {maximum}"
                        )
                        cases.append(
                            pytest.param(
                                ShapeBoundaryCase(
                                    make_shape(shape_type, **{field: color}),
                                    field,
                                    constraint,
                                ),
                                id=f"{shape_type}-{field}-{count}-channel-{channel}-{value}",
                            )
                        )
    return cases


VALID_BOUNDARY_CASES = _numeric_cases(valid=True)
INVALID_BOUNDARY_CASES = _numeric_cases(valid=False)

VALID_SHAPE_CASES = [
    *VALID_BOUNDARY_CASES,
    *[
        pytest.param(
            ShapeBoundaryCase(
                make_shape(shape_type, tag_structure_type=value), "tag_structure_type"
            ),
            id=f"{shape_type}-structure-{value}",
        )
        for shape_type in ("line", "rectangle")
        for value in get_args(PdfContentStructureType)
    ],
]
INVALID_SHAPE_CASES = [
    *INVALID_BOUNDARY_CASES,
    *[
        pytest.param(
            ShapeBoundaryCase(
                make_shape(
                    shape_type, tag_structure_type="DefinitelyNotAStructureType"
                ),
                "tag_structure_type",
                "Input should be",
            ),
            id=f"{shape_type}-invalid-structure-type",
        )
        for shape_type in ("line", "rectangle")
    ],
]
