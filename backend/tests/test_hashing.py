from foundation import hash_password, verify_password


def test_hash_password_returns_different_string_than_input() -> None:
    plain = "correct horse battery staple"
    hashed = hash_password(plain)
    assert hashed != plain


def test_hash_password_produces_different_hash_each_time() -> None:
    plain = "correct horse battery staple"
    first_hash = hash_password(plain)
    second_hash = hash_password(plain)
    assert first_hash != second_hash


def test_verify_password_succeeds_with_correct_password() -> None:
    plain = "correct horse battery staple"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_fails_with_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_password_fails_with_empty_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("", hashed) is False
