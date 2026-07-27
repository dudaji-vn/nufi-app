def test_guardrails_package_is_importable():
    import guardrails

    assert guardrails.__doc__ is not None
