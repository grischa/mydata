import requests
import json
import urllib

from logger.logger import logger
from group_model import GroupModel
from mytardis import MyTardis


class FacilityModel():

    def __init__(self, settings_model=None, name=None,
                 facility_json=None):

        self.settings_model = settings_model
        self.id = None
        self.name = name
        self.json = facility_json
        self.manager_group = None

        if facility_json is not None:
            self.id = facility_json['id']
            if name is None:
                self.name = facility_json['name']
            self.manager_group = \
                GroupModel(group_json=facility_json['manager_group'])

    def __str__(self):
        return "FacilityModel " + self.name

    def __unicode__(self):
        return "FacilityModel " + self.name

    def __repr__(self):
        return "FacilityModel " + self.name

    def get_resource_uri(self):
        return self.json['resource_uri']

    @staticmethod
    def get_facility(settingsModel, name):
        myt = MyTardis(settings=settingsModel)
        facilitiesJson = myt.get('facility', {'name': name})
        numFacilitiesFound = facilitiesJson['meta']['total_count']

        if numFacilitiesFound == 0:
            logger.warning("Facility \"%s\" was not found in MyTardis" % name)
            return None
        else:
            logger.debug("Found facility record for name '" + name + "'.")
            return FacilityModel(
                settingsModel=settingsModel, name=name,
                facilityJson=facilitiesJson['objects'][0])

    @staticmethod
    def GetMyFacilities(settingsModel, userModel):
        myTardisUrl = settingsModel.GetMyTardisUrl()
        myTardisUsername = settingsModel.GetUsername()
        myTardisApiKey = settingsModel.GetApiKey()

        facilities = []

        groups = userModel.GetGroups()

        for group in groups:
            url = myTardisUrl + "/api/v1/facility/?format=json" + \
                "&manager_group__id=" + str(group.GetId())
            headers = {'Authorization': 'ApiKey ' + myTardisUsername + ":" +
                       myTardisApiKey}
            session = requests.Session()
            response = session.get(url=url, headers=headers)
            if response.status_code != 200:
                message = response.text
                response.close()
                session.close()
                raise Exception(message)
            response.close()
            session.close()
            facilitiesJson = response.json()
            for facilityJson in facilitiesJson['objects']:
                facilities.append(FacilityModel(
                    settingsModel=settingsModel,
                    facilityJson=facilityJson))

        return facilities
