import unittest

from symphony import RequestStates, MachineStates, MachineResults
from request_tracking_db import RequestTrackingDb

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

        db = RequestTrackingDb(config, cluster_name, clock)
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

if __name__ == "__main__":
    unittest.main()
