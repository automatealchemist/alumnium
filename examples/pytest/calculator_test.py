from alumnium import Model
from pytest import mark, raises


@mark.xfail(Model.load() == Model.AWS_ANTHROPIC, reason="Bedrock version of Haiku is subpar")
def test_addition(al, driver):
    driver.get("https://seleniumbase.io/apps/calculator")
    al.do("1 + 1 =")
    al.check("calculator result is 2")
    with raises(AssertionError):
        al.check("calculator result is 3")
