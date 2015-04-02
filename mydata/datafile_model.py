"""
data model for DataFiles
"""
import requests
import urllib

from logger.Logger import logger
from replica_model import ReplicaModel
from Exceptions import DoesNotExist
from Exceptions import MultipleObjectsReturned


class DataFileModel(object):
    """
    data model for datafiles
    """

    def __init__(self, settings_model, dataset, datafile_json):
        self.settings_model = settings_model
        self.json = datafile_json
        self.id = None
        self.filename = None
        self.directory = None
        self.size = None
        self.created_time = None
        self.modification_time = None
        self.mimetype = None
        self.md5sum = None
        self.sha512sum = None
        self.deleted = None
        self.deleted_time = None
        self.version = None
        self.replicas = []
        self.parameter_sets = []
        if datafile_json is not None:
            for key in datafile_json:
                if hasattr(self, key):
                    self.__dict__[key] = datafile_json[key]
            self.replicas = []
            for replica_json in datafile_json['replicas']:
                self.replicas.append(ReplicaModel(replica_json=replica_json))
        # This needs to go after self.__dict__[key] = datafile_json[key]
        # so we get the full dataset model, not just the API resource string:
        self.dataset = dataset

    def __str__(self):
        return "DataFileModel " + self.filename + \
            " - " + self.dataset.GetDescription()

    def __unicode__(self):
        return "DataFileModel " + self.filename + \
            " - " + self.dataset.GetDescription()

    def __repr__(self):
        return "DataFileModel " + self.filename + \
            " - " + self.dataset.GetDescription()

    def is_verified(self):
        """
        returns True if all replicas are verified
        """
        # Should we also check that it's not in a staging storage box?
        return all([replica.verified for replica in self.replicas])

    def get_resource_uri(self):
        """
        returns resource uri from JSON representation
        """
        return self.json['resource_uri']

    @staticmethod
    def get_datafile(settings_model, dataset, filename, directory):
        """
        returns a datafile object for a filename
        """
        mytardis_url = settings_model.GetMyTardisUrl()
        mytardis_username = settings_model.GetUsername()
        mytardis_apikey = settings_model.GetApiKey()
        url = mytardis_url + "/api/v1/dataset_file/?format=json" + \
            "&dataset__id=" + str(dataset.GetId()) + \
            "&filename=" + urllib.quote(filename) + \
            "&directory=" + urllib.quote(directory)
        headers = {"Authorization": "ApiKey %s:%s" % (mytardis_username,
                                                      mytardis_apikey)}
        response = requests.get(url=url, headers=headers)
        if response.status_code < 200 or response.status_code >= 300:
            logger.debug("Failed to look up datafile \"%s\" "
                         "in dataset \"%s\"."
                         % (filename, dataset.GetDescription()))
            logger.debug(response.text)
            return None
        datafiles_json = response.json()
        num_files = datafiles_json['meta']['total_count']
        if num_files == 0:
            raise DoesNotExist(
                message="Datafile \"%s\" was not found in MyTardis" % filename,
                url=url, response=response)
        elif num_files > 1:
            raise MultipleObjectsReturned(
                message="Multiple datafiles matching %s were found in MyTardis"
                % filename,
                url=url, response=response)
        else:
            return DataFileModel(
                settings_model=settings_model,
                dataset=dataset,
                datafile_json=datafiles_json['objects'][0])
