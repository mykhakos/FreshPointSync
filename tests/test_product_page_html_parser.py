import bs4
import os
import pytest

from freshpointsync.product import Product
from freshpointsync.parser import ProductPageHTMLParser, normalize_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", ""),
        (None, ""),
        ("foo", "foo"),
        ("Foo", "foo"),
        ("FoO", "foo"),
        ("FOO", "foo"),
        ("   baR   ", "bar"),
        (12345, "12345"),
        (1.23, "1.23"),
        ("mě", "me"),
        ("Hovězí ", "hovezi"),
        ("  v   zakysané   smetaně  ", "v   zakysane   smetane"),
        ("Bramborová placka se salámem", "bramborova placka se salamem")
    ]
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


@pytest.fixture(scope='module')
def product_page_html_text():
    page_path = os.path.join(os.path.dirname(__file__), "product_page.html")
    with open(page_path, 'r', encoding='utf-8') as file:
        page_html_text = file.read()
    yield page_html_text


@pytest.fixture(scope='module')
def product_page_html_parser(product_page_html_text: str):
    yield ProductPageHTMLParser(product_page_html_text)


@pytest.mark.parametrize(
    "prod_name, prod_id, how_many_should_be_found",
    [
        (None, 0, 0),
        (None, 1, 0),
        ("", 0, 0),
        ("BIO Zahradní limonáda bezový květ & meduňka", 1420, 0),
        ("BIO Zahradní limonáda bezový květ & meduňka", 1419, 1),
        ("zahradni limonada bezovy kvet", None, 1),
        ("     zahradní limonada bezovy květ   ", None, 1),
        ("   zahradní    limonada    bezovy   květ   ", None, 0),
        (None, "1419", 1),
        (None, 1419, 1),
        (None, None, 291),
        ("", "", 0),
        (None, "", 0),
        ("", None, 291),
        ("San Pellegrino", None, 4),
        ("limonata", None, 1),
        ("limonada", None, 7),
        ("limonaaaada", None, 0),
    ]
)
def test_find_product_data(
    prod_name: str | None,
    prod_id: int | None,
    how_many_should_be_found: int,
    product_page_html_parser: ProductPageHTMLParser
):
    prod = product_page_html_parser._find_product_data(prod_name, prod_id)
    assert isinstance(prod, bs4.ResultSet)
    assert len(prod) == how_many_should_be_found
    assert all(isinstance(prod[i], bs4.Tag) for i in range(len(prod)))


@pytest.mark.parametrize(
    "prod_name_input, prod_name_output, prod_id_input, prod_id_output",
    [
        (
            "BIO Zahradní limonáda bezový květ & meduňka",
            "BIO Zahradní limonáda bezový květ & meduňka",
            1419,
            1419
        ),
        (
            "zahradni limonada bezovy kvet",
            "BIO Zahradní limonáda bezový květ & meduňka",
            None,
            1419
        ),
        (
            "     zahradní limonada bezovy květ   ",
            "BIO Zahradní limonáda bezový květ & meduňka",
            None,
            1419
        ),
        (
            "limonada",
            "BIO Zahradní limonáda bezový květ & meduňka",
            1419,
            1419
        ),
        (
            None,
            "BIO Zahradní limonáda bezový květ & meduňka",
            1419,
            1419
        ),
    ]
)
def test_find_product_valid(
    prod_name_input: str | None,
    prod_name_output: str | None,
    prod_id_input: int | None,
    prod_id_output: int | None,
    product_page_html_parser: ProductPageHTMLParser
):
    prod = product_page_html_parser.find_product(
        prod_name_input, prod_id_input
        )
    assert prod.name == prod_name_output
    assert prod.product_id == prod_id_output


@pytest.mark.parametrize(
    "prod_name, prod_id",
    [
        (None, None),
        ("", ""),
        (None, ""),
        ("", None),
        (None, 0),
        (None, 1),
        ("", 0),
        ("BIO Zahradní limonáda bezový květ & meduňka", 1420),
        ("   zahradní    limonada    bezovy   květ   ", None),
        ("San Pellegrino", None),
        ("limonada", None),
    ]
)
def test_find_product_invalid(
    prod_name: str | None,
    prod_id: int | None,
    product_page_html_parser: ProductPageHTMLParser
):
    with pytest.raises(ValueError):
        product_page_html_parser.find_product(prod_name, prod_id)


@pytest.mark.parametrize(
    "product",
    [
        Product(
            name="BIO Zahradní limonáda bezový květ & meduňka",
            product_id=1419,
            category="Nápoje",
            is_vegetarian=False,
            is_gluten_free=False,
            quantity=5,
            price_full=36.9,
            price_curr=36.9,
            pic_url=(
                r"https://images.weserv.nl/?url=http://freshpoint.freshserver."
                r"cz/backend/web/media/photo/c1de63aa281738f23f7f1f9995f8082c4"
                r"120f296a3da572ba069799b9345f26a.jpg"
            )
        ),
        Product(
            name="Vepřový guláš, brambory",
            product_id=806,
            category="Hlavní jídla",
            is_vegetarian=False,
            is_gluten_free=False,
            quantity=1,
            price_full=87.9,
            price_curr=87.9,
            pic_url=(
                r"https://images.weserv.nl/?url=http://freshpoint.freshserver."
                r"cz/backend/web/media/photo/3403a6acd54920a62760088b066bfcd41"
                r"2a2fd95a6951a44959713e310272fe0.jpg"
            )
        ),
        Product(
            name="Batátové chilli, basmati rýže",
            product_id=1335,
            category="Hlavní jídla",
            is_vegetarian=True,
            is_gluten_free=False,
            quantity=0,
            price_full=119.9,
            price_curr=119.9,
            pic_url=(
                r"https://images.weserv.nl/?url=http://freshpoint.freshserver."
                r"cz/backend/web/media/photo/30c3f0ab92e3ed6987009fa22a5a577d1"
                r"bf6356ce6f0e7e77ba4cdf77af52833.jpg"
            )
        ),
        Product(
            name=(
                "Vepřové výpečky s kysaným zelím a variací knedlíků "
                "(karlovarský a bramborový)"
                ),
            product_id=990,
            category="Hlavní jídla",
            is_vegetarian=False,
            is_gluten_free=False,
            quantity=0,
            price_full=119.9,
            price_curr=101.9,
            pic_url=(
                r"https://images.weserv.nl/?url=http://freshpoint.freshserver."
                r"cz/backend/web/media/photo/6c7f54623accbe53d485a70d83d96959f"
                r"505696760820add8d66dc3b07cb01c4.jpeg"
            )
        )
    ]
)
def test_parse_product_data(
    product: Product, product_page_html_parser: ProductPageHTMLParser
):
    parsed = product_page_html_parser.find_product(id=product.product_id)
    assert parsed.product_id == product.product_id
    assert parsed.name == product.name
    assert parsed.category == product.category
    assert parsed.is_vegetarian == product.is_vegetarian
    assert parsed.is_gluten_free == product.is_gluten_free
    assert parsed.price_full == product.price_full
    assert parsed.price_curr == product.price_curr
    assert parsed.pic_url == product.pic_url
    assert parsed.timestamp != product.timestamp
