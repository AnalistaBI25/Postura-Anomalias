import pandas as pd

from granjas_anomalias.utils import clean_key, parse_sap_number


def test_clean_key_removes_excel_decimal():
    assert clean_key(12000000001.0) == "12000000001"


def test_parse_sap_trailing_negative():
    assert parse_sap_number("320-") == -320.0
