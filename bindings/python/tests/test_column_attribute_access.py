import keyword

import pytest

from gaspatchio_core import ActuarialFrame, ColumnProxy


@pytest.fixture
def simple_af() -> ActuarialFrame:
    return ActuarialFrame(
        {
            "a": [1, 2, 3],
            "b": [4, 5, 6],
            "count": [0, 0, 0],  # potential conflict with method name
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],  # accessor name
            "unicodé": [1, 2, 3],  # unicode identifier
            "not-an-identifier": [1, 2, 3],
            "_private": [1, 2, 3],
        }
    )


def test_attribute_access_basic(simple_af: ActuarialFrame):
    # Valid identifier column should be accessible
    assert isinstance(simple_af.a, ColumnProxy)
    assert simple_af.a.name == "a"
    # Same proxy semantics as bracket
    assert isinstance(simple_af["a"], ColumnProxy)


def test_attribute_access_equals_bracket(simple_af: ActuarialFrame):
    attr_proxy = simple_af.a
    bracket_proxy = simple_af["a"]
    # Both are ColumnProxy, names equal
    assert isinstance(attr_proxy, ColumnProxy)
    assert isinstance(bracket_proxy, ColumnProxy)
    assert attr_proxy.name == bracket_proxy.name == "a"


def test_attribute_assignment_creates_column(simple_af: ActuarialFrame):
    # assignment with expression
    simple_af.c = simple_af.a + 1
    assert "c" in simple_af.columns
    out = simple_af.collect()
    assert out["c"].to_list() == [2, 3, 4]

    # assignment with scalar
    simple_af.d = 10
    out2 = simple_af.collect()
    assert out2["d"].to_list() == [10, 10, 10]


@pytest.mark.parametrize(
    "bad", ["not-an-identifier", "has space", "123abc", "x-y", "a:b"]
)
def test_invalid_identifier_rejected(simple_af: ActuarialFrame, bad: str):
    with pytest.raises(
        AttributeError,
        match=r"not a valid attribute name|use af\['" + bad.replace("[", "\\[") + "'",
    ):
        # getattr path
        getattr(simple_af, bad)

    with pytest.raises(
        AttributeError,
        match=r"not a valid attribute name; use af\['"
        + bad.replace("[", "\\[")
        + r"'\]",
    ):
        # setattr path
        setattr(simple_af, bad, 1)


@pytest.mark.parametrize("kw", ["class", "for", "if", "return"])  # sample keywords
def test_keyword_identifier_rejected(simple_af: ActuarialFrame, kw: str):
    assert keyword.iskeyword(kw)
    with pytest.raises(
        AttributeError, match=r"Python keyword; use af\['" + kw + r"'\] instead"
    ):
        getattr(simple_af, kw)
    with pytest.raises(
        AttributeError, match=r"not a valid attribute name; use af\['" + kw + r"'\] = "
    ):
        setattr(simple_af, kw, 1)


@pytest.mark.parametrize("name", ["_private", "__dunder__"])
def test_underscore_names_rejected(simple_af: ActuarialFrame, name: str):
    with pytest.raises(
        AttributeError,
        match=r"not available via attribute access; use af\['" + name + r"'\]",
    ):
        getattr(simple_af, name)
    with pytest.raises(
        AttributeError,
        match=r"not a valid attribute name; use af\['" + name + r"'\] = ",
    ):
        setattr(simple_af, name, 1)


def test_method_conflict_rejected_but_bracket_works(simple_af: ActuarialFrame):
    # "count" is a method on frame; attribute should raise conflict
    with pytest.raises(
        AttributeError, match="conflicts with existing method/attribute"
    ):
        _ = simple_af.count
    # bracket still returns column
    proxy = simple_af["count"]
    assert isinstance(proxy, ColumnProxy)


def test_accessor_precedence(simple_af: ActuarialFrame):
    # date accessor should take precedence
    accessor = simple_af.date
    # Accessor object should not be ColumnProxy
    assert not isinstance(accessor, ColumnProxy)
    # And still able to access column via bracket
    assert isinstance(simple_af["date"], ColumnProxy)


def test_nonexistent_attribute_has_helpful_error():
    af = ActuarialFrame({"x": [1]})
    with pytest.raises(
        AttributeError,
        match=r"object has no attribute 'y'. If 'y' is a column name, use af\['y'\] instead",
    ):
        _ = af.y


def test_dir_includes_eligible_columns_and_accessors(simple_af: ActuarialFrame):
    names = dir(simple_af)
    # Eligible identifiers present
    assert "a" in names and "b" in names and "unicodé" in names
    # Non-identifiers and underscores excluded
    assert "not-an-identifier" not in names
    assert "_private" not in names
    # Accessors included
    assert "date" in names and "excel" in names and "finance" in names


def test_unicode_identifier_access(simple_af: ActuarialFrame):
    # unicode that is identifier should work
    proxy = simple_af.unicodé
    assert isinstance(proxy, ColumnProxy)
