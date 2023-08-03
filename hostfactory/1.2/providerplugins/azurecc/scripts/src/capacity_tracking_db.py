import os
import calendar
from util import JsonStore, init_logging


class CapacityTrackingDb:
    
    def __init__(self, config, cluster_name, clock, limits_timeout=300):
        self.config = config
        self.cluster_name = cluster_name
        self.clock = clock
        self.limits_timeout = limits_timeout
        # initialize in constructor so that cyclecloud_provider can initialize this
        # with the proper log_level. In tests, this will use the default.
        self.logger = init_logging()

        default_dir = os.getenv('HF_WORKDIR', '/var/tmp')
        self.db_dir = config.get('symphony.hostfactory.db_path', default_dir)
        self.requests_db = JsonStore('azurecc_requests.json', self.db_dir)
        self.capacity_db = JsonStore('azurecc_capacity.json', self.db_dir)

    def reset(self):
        self.requests_db.clear()
        self.capacity_db.clear()

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

    def remove_limits(self, capacity_keys):
        with self.capacity_db as db:
            for k in capacity_keys:
                db.pop(k)

    def _capacity_key(self, nodearray_name, machine_type):
        return "%s_%s" % (nodearray_name, machine_type)

    def pause_capacity(self, nodearray_name, machine_type):
        with self.capacity_db as db:
            now = calendar.timegm(self.clock())
            key = self._capacity_key(nodearray_name, machine_type)
            db[key] = { 'nodearray': nodearray_name,
                        'machine_type': machine_type,
                        'max_count': 0,              # we used to provide max_count set to 0 so left for backwards compatibility
                        'start_time': now }


    def _release_expired_limits(self):
        # Return True if any limits changed
        def _limit_expired(now, capacity_limit):
            expiry_time = self.limits_timeout + capacity_limit['start_time']            
            return now >= expiry_time
        
        now = calendar.timegm(self.clock())        
        expired = []
        for k, v in self.capacity_db.read().items():
            if _limit_expired(now, v):
                expired.append(k)
        if expired:
            self.remove_limits(expired)

        return len(expired) > 0


    def request_completed(self, request_status):
        # Return True if any limits changed
        limits_changed = False
        request_id = request_status["requestId"]
        num_created = len(request_status["machines"])
        request_envelope = self.get_request(request_id)
        if request_envelope:
            self.remove_request(request_id)

        self._release_expired_limits()
    
    def is_paused(self, nodearray_name, machine_type): 
        key = self._capacity_key(nodearray_name, machine_type)
        ret = False
        limited_buckets = self.capacity_db.read()
        if key in limited_buckets:            
            ret = True
            self.logger.info("Limiting reported priority for machine_type %s in nodearray %s to 0", machine_type, nodearray_name)

        self._release_expired_limits()
        return ret
