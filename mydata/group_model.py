import requests
import urllib

from logger.logger import logger
from exceptions import DoesNotExist


class GroupModel():

    def __init__(self, settings_model=None, name=None, group_json=None):
        self.settings_model = settings_model
        self.id = None
        self.name = name
        self.groupJson = group_json

        if group_json is not None:
            self.id = group_json['id']
            if name is None:
                self.name = group_json['name']

        self.shortName = name
        if settings_model is not None:
            l = len(settings_model.GetGroupPrefix())
            self.shortName = self.name[l:]

    def __str__(self):
        return "GroupModel " + (self.name or '')

    def __unicode__(self):
        return "GroupModel " + (self.name or '')

    def __repr__(self):
        return "GroupModel " + (self.name or '')

    @staticmethod
    def get_group_by_name(settings_model, name):
        mytardis_url = settings_model.GetMyTardisUrl()
        mytardis_username = settings_model.GetUsername()
        mytardis_apikey = settings_model.GetApiKey()

        url = mytardis_url + "/api/v1/group/?format=json&name=" + \
            urllib.quote(name)
        headers = {'Authorization': 'ApiKey ' + mytardis_username + ":" +
                   mytardis_apikey}
        response = requests.get(url=url, headers=headers)
        if response.status_code != 200:
            logger.debug("Failed to look up group record for name \"" +
                         name + "\".")
            logger.debug(response.text)
            raise Exception(response.text)
        groups_json = response.json()
        num_groups = groups_json['meta']['total_count']

        if num_groups == 0:
            raise DoesNotExist(
                message="Group \"%s\" was not found in MyTardis" % name,
                url=url, response=response)
        else:
            logger.debug("Found group record for name '" + name + "'.")
            return GroupModel(settings_model=settings_model, name=name,
                              group_json=groups_json['objects'][0])
