from src.services.recipe_instruction_codec import (
    build_instruction_model_from_steps,
    decode_instruction_text_to_steps,
    decode_text_to_instruction_model,
    encode_instruction_model_to_text,
    encode_instruction_steps_to_text,
    flatten_instruction_model_to_steps,
    normalize_instruction_step,
)


def test_normalize_instruction_step_trims_and_collapses_spaces():
    assert normalize_instruction_step("  Grill   chicken   ") == "Grill chicken"


def test_build_instruction_model_from_steps_ignores_empty_steps():
    result = build_instruction_model_from_steps(
        ["Prep ingredients", "   ", "", "Grill chicken"]
    )

    assert result == [
        {"text": "Prep ingredients"},
        {"text": "Grill chicken"},
    ]


def test_flatten_instruction_model_to_steps_returns_ordered_text():
    model = [
        {"text": "Prep ingredients"},
        {"text": "Mix marinade"},
        {"text": "Grill chicken"},
    ]

    result = flatten_instruction_model_to_steps(model)

    assert result == [
        "Prep ingredients",
        "Mix marinade",
        "Grill chicken",
    ]


def test_encode_instruction_model_to_text_numbers_steps_in_order():
    model = [
        {"text": "Prep ingredients"},
        {"text": "Mix marinade"},
        {"text": "Grill chicken"},
    ]

    result = encode_instruction_model_to_text(model)

    assert result == (
        "1. Prep ingredients\n"
        "2. Mix marinade\n"
        "3. Grill chicken"
    )


def test_encode_instruction_model_to_text_raises_if_empty():
    try:
        encode_instruction_model_to_text([])
        assert False, "Expected ValueError for empty instruction model"
    except ValueError as exc:
        assert str(exc) == "At least one non-empty instruction step is required."


def test_decode_text_to_instruction_model_returns_ordered_model():
    instructions_text = (
        "1. Prep ingredients\n"
        "2. Mix marinade\n"
        "3. Grill chicken"
    )

    result = decode_text_to_instruction_model(instructions_text)

    assert result == [
        {"text": "Prep ingredients"},
        {"text": "Mix marinade"},
        {"text": "Grill chicken"},
    ]


def test_encode_instruction_steps_to_text_works_from_raw_steps():
    result = encode_instruction_steps_to_text(
        ["Prep ingredients", "   ", "Grill chicken"]
    )

    assert result == (
        "1. Prep ingredients\n"
        "2. Grill chicken"
    )


def test_decode_instruction_text_to_steps_returns_simple_steps():
    instructions_text = (
        "1. Prep ingredients\n"
        "2. Mix marinade\n"
        "3. Grill chicken"
    )

    result = decode_instruction_text_to_steps(instructions_text)

    assert result == [
        "Prep ingredients",
        "Mix marinade",
        "Grill chicken",
    ]