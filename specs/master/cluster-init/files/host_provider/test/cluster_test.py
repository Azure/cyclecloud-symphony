import unittest
import cluster
import logging

class TestCluster(unittest.TestCase):
    
    def test_limit_request_by_available_count(self):
        pass
        def make_new_request(machine_count=1):
            request_set = {'count': machine_count,                       
                        'requestId': "abcd",
                        'definition': {'machineType': "Standard_D2_v2"},
                        'nodeAttributes': {'Tags': {"foo": "bar"},
                                            'Configuration': "user_data"},
                        'nodearray': 'execute'}
            request = {'requestId': "abcd",'sets': [request_set]}
            return request
        
        status ={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                        "machineType": "Standard_D2_v2"
                    },"availableCount":100}]} ]}
        
            
        def run_test(request_count, expected_count):
            req = make_new_request(request_count)
            limited_req = cluster.limit_request_by_available_count(status, req, logging)
            self.assertEqual(limited_req["sets"][0]["count"], expected_count)  
        
        def run_test_zero_available(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                "machineType": "Standard_D2_v2"
            },"availableCount":0}]} ]}
            self.assertRaises(RuntimeError, cluster.limit_request_by_available_count, status, req, logging)    
                   
        run_test(1, 1)
        run_test(99, 99)
        run_test(100, 100)
        run_test(101, 100)   
        run_test_zero_available(10)
        
if __name__ == "__main__":
    unittest.main()
    