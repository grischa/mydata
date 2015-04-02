"""
helper class for communication with MyTardis
"""
import json
import requests
from urllib import urlencode, quote
from exceptions import Unauthorized
from logger.logger import logger


class MyTardis(object):
    """
    use this class to talk to MyTardis
    """

    def __init__(self, settings=None, api_version='v1'):
        if settings is None:
            raise Exception
        self.host = settings.GetMyTardisUrl()
        self.username = settings.GetUsername()
        self.api_key = settings.GetApiKey()
        self.api_version = api_version
        self.headers = {
            'Authorization': 'ApiKey %s:%s' % (self.username, self.api_key),
            'Accept': 'application/json',
        }

    def _build_url(self, action=None, query_dict=None):
        url = '%(host)s/api/%(version)s/%(action)s/?%(query_string)s' % {
            'host': self.host,
            'version': self.api_version,
            'action': action,
            'query_string': urlencode(query_dict or ''),
        }
        return url

    def get(self, action=None, query_dict=None):
        response = requests.get(url=self._build_url(action, query_dict),
                                headers=self.headers)
        if response.status_code >= 400:
            raise Exception(response.text)
        return response.json()

    def _post_put(self, method=None, action=None, data=None, query_dict=None):
        if method == 'post':
            method_call = requests.post
        elif method == 'put':
            method_call = requests.put
        else:
            raise Exception('bad request method "%s"' % method)

        self.headers["Content-Type"] = "application/json"
        url = self._build_url(action, query_dict)
        response = method_call(headers=self.headers,
                               url=url,
                               data=json.dumps(data))
        code = response.status_code
        if code >= 300:
            if code == 401:
                message = 'Could not create or change "%s"' % (action)
                message += "\n\n"
                message += "Please ask your MyTardis administrator to " \
                           'check the permissions of the "%s" ' \
                           "user account." % self.username
                raise Unauthorized(message)
            if code == 404:
                raise Exception("HTTP 404 (Not Found) received for: " + url)
            logger.error("Status code = " + str(code))
            logger.error("URL = " + url)
            raise Exception(response.text)
        return response.json()

    def post(self, action=None, data=None, query_dict=None):
        return self._post_put(method='post',
                              action=action, data=data, query_dict=query_dict)

    def put(self, action=None, data=None, query_dict=None):
        return self._post_put(method='put',
                              action=action, data=data, query_dict=query_dict)
