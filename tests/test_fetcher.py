import logging
from unittest.mock import patch, MagicMock

import pytest
import requests

from fetcher import WebFetcher


@pytest.fixture
def logger():
    return logging.getLogger("fetcher_test")


def _make_response(text, status_code=200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.apparent_encoding = None
    resp.encoding = "utf-8"
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_success(logger):
    fetcher = WebFetcher(logger)
    expected = "<html><body>ok</body></html>"
    with patch("requests.get", return_value=_make_response(expected)) as m:
        content, error = fetcher.fetch("https://example.com", 10)
    assert content == expected
    assert error is None
    m.assert_called_once()
    args, kwargs = m.call_args
    assert args[0] == "https://example.com"
    assert kwargs["timeout"] == 10
    assert "User-Agent" in kwargs["headers"]


def test_fetch_timeout(logger):
    fetcher = WebFetcher(logger)
    exc = requests.exceptions.Timeout("Request timed out")
    with patch("requests.get", side_effect=exc):
        content, error = fetcher.fetch("https://example.com", 10)
    assert content is None
    assert "timed out" in error


def test_fetch_http_error_status(logger):
    fetcher = WebFetcher(logger)
    resp = _make_response("Not Found", status_code=404)
    resp.raise_for_status = MagicMock()
    with patch("requests.get", return_value=resp):
        content, error = fetcher.fetch("https://example.com", 10)
    assert error is None
    assert content == "Not Found"


def test_fetch_network_unreachable(logger):
    fetcher = WebFetcher(logger)
    exc = requests.exceptions.ConnectionError("Network is unreachable")
    with patch("requests.get", side_effect=exc):
        content, error = fetcher.fetch("https://example.com", 10)
    assert content is None
    assert "Network is unreachable" in error


def test_fetch_ssl_error(logger):
    fetcher = WebFetcher(logger)
    exc = requests.exceptions.SSLError("SSL: CERTIFICATE_VERIFY_FAILED")
    with patch("requests.get", side_effect=exc):
        content, error = fetcher.fetch("https://example.com", 10)
    assert content is None
    assert "SSL" in error


def test_fetch_too_many_redirects(logger):
    fetcher = WebFetcher(logger)
    exc = requests.exceptions.TooManyRedirects("Exceeded 30 redirects")
    with patch("requests.get", side_effect=exc):
        content, error = fetcher.fetch("https://example.com", 10)
    assert content is None
    assert "redirects" in error
