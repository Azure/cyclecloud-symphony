import os
import calendar
from util import JsonStore, init_logging


class RequestTrackingDb:
    
    def __init__(self, config, cluster_name, clock):
        self.config = config
        self.cluster_name = cluster_name
        self.clock = clock
        # initialize in constructor so that cyclecloud_provider can initialize this
        # with the proper log_level. In tests, this will use the default.
        self.logger = init_logging()

        default_dir = os.getenv('HF_WORKDIR', '/var/tmp')
        self.db_dir = config.get('symphony.hostfactory.db_path', default_dir)
        self.requests_db = JsonStore('azurecc_requests.json', self.db_dir)


    def reset(self):
        self.requests_db.clear()

    def add_request(self, request_set):
        with self.requests_db as db:
            request_id = request_set['requestId']
            db[request_id] = { 'requestId': request_id,
                               'timestamp': calendar.timegm(self.clock()),
                               'sets': [request_set] }
    
    def get_requests(self):
        pending_requests = self.requests_db.read()
        return pending_requests

    def get_request(self, request_id):
        pending_requests = self.get_requests()
        if request_id in pending_requests:
            return pending_requests[request_id]
        return None

    def remove_request(self, request_id):
        with self.requests_db as pending_requests:
            pending_requests.pop(request_id)

    def remove_requests(self, request_ids):
        with self.requests_db as pending_requests:
            for request_id in request_ids:
                pending_requests.pop(request_id)

    def request_completed(self, request_status):
        request_id = request_status["requestId"]
        request_envelope = self.get_request(request_id)
        if request_envelope:
            self.remove_request(request_id)   