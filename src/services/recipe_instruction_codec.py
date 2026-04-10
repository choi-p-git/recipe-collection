import re
from typing import Any


def normalize_instruction_step(step: str) -> str:
    """
    Normalize a single instruction step by:
    - trimming leading/trailing whitespace
    - collapsing repeated internal whitespace
    """
    return " ".join(step.split())


def build_instruction_model_from_steps(steps: list[str]) -> list[dict[str, Any]]:
    """
    Convert a raw ordered list of step strings into the neutral internal model.

    Current MVP model:
    [
        {"text": "Prep ingredients"},
        {"text": "Mix marinade"},
    ]
    """
    model: list[dict[str, Any]] = []

    for step in steps:
        normalized = normalize_instruction_step(step)
        if normalized:
            model.append({"text": normalized})

    return model


def flatten_instruction_model_to_steps(
    instruction_model: list[dict[str, Any]],
) -> list[str]:
    """
    Convert the neutral instruction model back into a simple ordered list of step strings.
    """
    steps: list[str] = []

    for entry in instruction_model:
        text = normalize_instruction_step(str(entry.get("text", "")))
        if text:
            steps.append(text)

    return steps


def encode_instruction_model_to_text(
    instruction_model: list[dict[str, Any]],
) -> str:
    """
    Encode the neutral instruction model into the current MVP plain-text storage format.

    Current format:
    1. Step one
    2. Step two
    """
    steps = flatten_instruction_model_to_steps(instruction_model)

    if not steps:
        raise ValueError("At least one non-empty instruction step is required.")

    return "\n".join(
        f"{index}. {step}"
        for index, step in enumerate(steps, start=1)
    )


def decode_text_to_instruction_model(instructions_text: str) -> list[dict[str, Any]]:
    """
    Decode the current MVP plain-text storage format back into the neutral instruction model.
    """
    if not instructions_text or not instructions_text.strip():
        return []

    numbered_pattern = re.compile(r"^\s*\d+\.\s+(.*)$")
    model: list[dict[str, Any]] = []

    for line in instructions_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        match = numbered_pattern.match(stripped)
        if match:
            text = normalize_instruction_step(match.group(1))
        else:
            text = normalize_instruction_step(stripped)

        if text:
            model.append({"text": text})

    return model


def encode_instruction_steps_to_text(steps: list[str]) -> str:
    """
    Convenience wrapper:
    raw step strings -> neutral model -> plain text
    """
    model = build_instruction_model_from_steps(steps)
    return encode_instruction_model_to_text(model)


def decode_instruction_text_to_steps(instructions_text: str) -> list[str]:
    """
    Convenience wrapper:
    plain text -> neutral model -> raw ordered step strings
    """
    model = decode_text_to_instruction_model(instructions_text)
    return flatten_instruction_model_to_steps(model)