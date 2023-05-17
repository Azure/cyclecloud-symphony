import unittest

from symphony import RequestStates, MachineStates, MachineResults
from capacity_tracking_db import CapacityTrackingDb

class MockClock:
    
    def __init__(self, now):
        self.now = now
        
    def __call__(self):
        return self.now
    

class TestHostFactory(unittest.TestCase):

    def test_requests_CRUD(self):

        config = {}
        cluster_name = "test_cluster"
        clock = MockClock((1970, 1, 1, 0, 0, 0))

        db = CapacityTrackingDb(config, cluster_name, clock)
        db.reset()
        self.assertFalse(db.get_requests())

        request_id = "dummy_request_id"
        nodearray = {"machineType": ["a4", "a8"], "Configuration": {"autoscaling": {"enabled": True}, "symphony": {"autoscale": True}}}
        request_set = {'count': 1,                       
                    'requestId': request_id,
                    'definition': {'machineType': "A8"},
                    'nodearray': nodearray}

        db.add_request(request_set)
        self.assertEqual(1, len(db.get_requests()))
        stored_requests = db.get_requests()
        self.assertIn(request_id, stored_requests)
        self.assertEqual(request_id, stored_requests[request_id]['requestId'])

        db.remove_request(request_id)
        self.assertFalse(db.get_requests())

    def test_capacity_limit_and_expiry(self):

        def build_request_set(request_id, machine_type, machine_count, user_data={}):
            MACHINE_TYPES = {
                "A4": {"Name": "A4", "vcpuCount": 4, "memory": 1., "Location": "ukwest", "Quota": 10},
                "A8": {"Name": "A8", "vcpuCount": 8, "memory": 2., "Location": "ukwest", "Quota": 20}
            }

            a4bucket = {"maxCount": 100, "definition": {"machineType": "A4"}, "virtualMachine": MACHINE_TYPES["A4"]}
            a8bucket = {"maxCoreCount": 800, "definition": {"machineType": "A8"}, "virtualMachine": MACHINE_TYPES["A8"]}
            nodearray = {"name": "execute",
                         "UserData": {},
                         "nodearray": {"machineType": ["a4", "a8"], "Configuration": {"autoscaling": {"enabled": True}, "symphony": {"autoscale": True}}},
                         "buckets": [a4bucket, a8bucket]}
            request_set = {'count': machine_count,                       
                           'requestId': request_id,
                           'definition': {'machineType': machine_type},
                           'nodeAttributes': {'Tags': {"foo": "bar"},
                                              'Configuration': user_data},
                           'nodearray': 'execute'}
            return request_set
                                    
        config = {}
        cluster_name = "test_cluster"
        clock = MockClock((1970, 1, 1, 0, 0, 0))

        db = CapacityTrackingDb(config, cluster_name, clock)
        db.reset()
        self.assertFalse(db.get_requests())

        # request 100 <= bucket['MaxCount']
        request_id = "test_request_id"
        request_set = build_request_set(request_id, "A4", 100)
        db.add_request(request_set)
        self.assertIsNotNone(db.get_request(request_id))

        # request completed with only 1 machine
        #create_response = {"requestId": request_id,
          #                 "status": RequestStates.complete,
           #                "machines": [{"name": "host-123", "machineId": "id-123"}]}
        #db.request_completed(create_response)
        db.pause_capacity(request_set.get("nodearray"), request_set['definition']['machineType'])
        key = db._capacity_key("execute", "A4")
        capacity_db = db.capacity_db.read()
        self.assertIn(key, capacity_db)
        db._release_expired_limits()
        capacity_db = db.capacity_db.read()
        self.assertIn(key, capacity_db)

        # Now verify that capacity is limited
        self.assertFalse(db.is_paused("execute", "A4"))

        # Finally advance clock just over 5 min to expire the limit - default expiry is 300 sec
        db.clock.now = (1970, 1, 1, 0, 5, 10)
        db._release_expired_limits()
        capacity_db = db.capacity_db.read()
        self.assertNotIn(key, capacity_db)



if __name__ == "__main__":
    unittest.main()
