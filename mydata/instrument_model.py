import requests
import json
import urllib

from logger.logger import logger
from facility_model import FacilityModel
from exceptions import Unauthorized
from mytardis import MyTardis


class InstrumentModel():

    def __init__(self, settingsModel=None, name=None,
                 instrumentJson=None):

        self.settingsModel = settingsModel
        self.id = None
        self.name = name
        self.json = instrumentJson
        self.facility = None

        if instrumentJson is not None:
            self.id = instrumentJson['id']
            if name is None:
                self.name = instrumentJson['name']
            self.facility = FacilityModel(
                facilityJson=instrumentJson['facility'])

    def __str__(self):
        return "InstrumentModel " + self.name + \
            " - " + self.facility.GetName()

    def __unicode__(self):
        return "InstrumentModel " + self.name + \
            " - " + self.facility.GetName()

    def __repr__(self):
        return "InstrumentModel " + self.name + \
            " - " + self.facility.GetName()

    def get_resource_uri(self):
        """
        get resource uri from JSON
        """
        return self.json['resource_uri']

    @staticmethod
    def CreateInstrument(settingsModel, facility, name):
        myt = MyTardis(settings=settingsModel)
        action = "instrument"
        data = {"facility": facility.GetResourceUri(),
                "name": name}
        instrument_json = myt.post(action=action, data=data)
        return InstrumentModel(settingsModel=settingsModel, name=name,
                               instrumentJson=instrument_json)

    @staticmethod
    def GetInstrument(settingsModel, facility, name):
        myt = MyTardis(settings=settingsModel)
        action = "instrument"
        query_dict = {"facility__id": str(facility.id),
                      "name": name}
        instruments_json = myt.get(action=action, query_dict=query_dict)
        num_instruments = \
            instruments_json['meta']['total_count']
        if num_instruments == 0:
            logger.warning("Instrument \"%s\" was not found in MyTardis"
                           % name)
            logger.debug(query_dict)
            logger.debug(response.text)
            return None
        else:
            logger.debug("Found instrument record for name \"%s\" "
                         "in facility \"%s\"" %
                         (name, facility.GetName()))
            instrument_json = instruments_json['objects'][0]
            return InstrumentModel(
                settingsModel=settingsModel, name=name,
                instrumentJson=instrument_json)

    @staticmethod
    def GetMyInstruments(settingsModel, userModel):
        myt = MyTardis(settings=settingsModel)
        instruments = []

        my_facilities = FacilityModel.GetMyFacilities(settingsModel, userModel)

        for facility in my_facilities:
            action = 'instrument'
            query_dict = {"facility__id": str(facility.id)}
            response = myt.get(action, query_dict)
            instruments_json = response.json()
            for instrument_json in instruments_json['objects']:
                instruments.append(InstrumentModel(
                    settingsModel=settingsModel,
                    instrumentJson=instrument_json))

        return instruments

    def Rename(self, name):
        myt = MyTardis(settings=self.settingsModel)
        logger.info("Renaming instrument \"%s\" to \"%s\"."
                    % (str(self), name))
        action = 'instrument/%d' % self.id
        data = {"name": name}
        myt.put(action=action, data=data)
