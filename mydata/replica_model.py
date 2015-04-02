"""
data model for replicas
"""


class ReplicaModel(object):
    """
    At the time of writing, the Replica model has been removed from MyTardis
    and replaced with the DataFileObject model.  But MyTardis's API still
    returns JSON labeled as "replicas" within each DataFileResource.
    """

    def __init__(self, settings_model=None, replica_json=None):
        self.settings_model = settings_model

        self.id = None
        self.uri = None
        self.df_resource_uri = None
        self.verified = None
        self.last_verified_time = None
        self.created_time = None
        self.json = replica_json
        self.df_resource_uri = None

        if replica_json is not None:
            for key in replica_json:
                if hasattr(self, key):
                    self.__dict__[key] = replica_json[key]
            self.df_resource_uri = replica_json['datafile']

    def __str__(self):
        return "ReplicaModel " + (self.uri or '')

    def __unicode__(self):
        return "ReplicaModel " + (self.uri or '')

    def __repr__(self):
        return "ReplicaModel " + (self.uri or '')

    def get_resource_uri(self):
        """
        get resource uri from JSON representation
        """
        return self.json['resource_uri']
