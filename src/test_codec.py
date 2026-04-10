from services.recipe_instruction_codec import (
    build_instruction_model_from_steps,
    decode_instruction_text_to_steps,
    encode_instruction_model_to_text,
)


def main() -> None:
    raw_steps = [
        "  Prep ingredients  ",
        "",
        "Mix marinade",
        "Grill at 350 F",
    ]

    model = build_instruction_model_from_steps(raw_steps)
    print("MODEL:")
    print(model)
    print()

    encoded = encode_instruction_model_to_text(model)
    print("ENCODED:")
    print(encoded)
    print()

    decoded_steps = decode_instruction_text_to_steps(encoded)
    print("DECODED STEPS:")
    print(decoded_steps)


if __name__ == "__main__":
    main()