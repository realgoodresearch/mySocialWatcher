import unittest

import requests

from mysocialwatcher.crawler.utils import safe_http_error_message


class CrawlerErrorRedactionTests(unittest.TestCase):
    def test_response_body_is_never_in_error_message(self):
        secret = "never-echo-this-token"
        response = requests.Response()
        response.status_code = 422
        response._content = ('{"input":{"token":"' + secret + '"}}').encode()

        message = safe_http_error_message(ValueError("invalid response"), response)

        self.assertIn("HTTP STATUS: 422", message)
        self.assertNotIn(secret, message)
        self.assertNotIn(response.text, message)


if __name__ == "__main__":
    unittest.main()
