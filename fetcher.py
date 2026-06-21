import requests


class WebFetcher:
    def __init__(self, logger):
        self.logger = logger
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch(self, url, timeout):
        try:
            response = requests.get(url, headers=self.headers, timeout=timeout)
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text, None
        except requests.RequestException as e:
            return None, str(e)
