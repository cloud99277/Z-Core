from __future__ import annotations

from importlib import resources


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_prompt_template(name: str) -> str:
    template_name = name if name.endswith(".md") else f"{name}.md"
    return resources.files("zcore.prompts").joinpath(template_name).read_text(encoding="utf-8")


def render_prompt_template(name: str, **values: str) -> str:
    template = load_prompt_template(name)
    return template.format_map(_SafeFormatDict({key: str(value) for key, value in values.items()}))
