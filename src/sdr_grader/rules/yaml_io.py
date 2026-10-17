"""Bounded loading of rubric and suppression YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from yaml.composer import ComposerError

from sdr_grader.core.exceptions import RubricValidationError

MAX_YAML_DEPTH = 64
_MAX_REPR = 80


class _AliasError(ComposerError):
    pass


class _DepthError(ComposerError):
    pass


class _ConfigLoader(yaml.SafeLoader):
    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise _AliasError(None, None, "aliases are not supported", self.peek_event().start_mark)
        self._depth += 1
        try:
            if self._depth > MAX_YAML_DEPTH:
                raise _DepthError(
                    None,
                    None,
                    f"nesting exceeds {MAX_YAML_DEPTH} levels",
                    self.peek_event().start_mark,
                )
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


def load_config_yaml(path: Path) -> Any:
    """Load a config YAML file; every failure is a RubricValidationError."""
    name = path.name
    try:
        with path.open(encoding="utf-8") as handle:
            try:
                loaded = yaml.load(handle, Loader=_ConfigLoader)  # noqa: S506
            except UnicodeDecodeError:
                raise
            except ValueError as exc:
                raise RubricValidationError(f"{name}: invalid YAML scalar") from exc
            return {} if loaded is None else loaded
    except UnicodeDecodeError as exc:
        raise RubricValidationError(f"{name}: YAML must be UTF-8 encoded") from exc
    except _AliasError as exc:
        raise RubricValidationError(f"{name}: YAML aliases are not supported") from exc
    except (_DepthError, RecursionError) as exc:
        raise RubricValidationError(f"{name}: YAML nesting exceeds limits") from exc
    except yaml.YAMLError as exc:
        raise RubricValidationError(f"{name}: invalid YAML syntax") from exc
    except OSError as exc:
        raise RubricValidationError(f"{name}: could not read YAML") from exc


def describe_value(value: Any) -> str:
    """Payload-safe description: scalar repr (bounded) or the type name."""
    if value is None or isinstance(value, (str, int, float, bool)):
        text = repr(value)
        if len(text) > _MAX_REPR:
            return text[: _MAX_REPR - 3] + "..."
        return text
    return type(value).__name__
