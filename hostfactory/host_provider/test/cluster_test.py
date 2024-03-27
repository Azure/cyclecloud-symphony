import unittest
import cluster
import logging
from unittest.mock import MagicMock

class TestCluster(unittest.TestCase):
    
    def test_limit_request_by_available_count(self):
        pass
        #self.provider.config.set("symphony.disable_active_count_fix", True)
        cluster_name = "TestCluster"
        provider_config = {"User" : "abcd"}
        cluster.new_node_manager = MagicMock(return_value=None)
        cluster_test = cluster.Cluster(cluster_name, provider_config, logging)
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
        
            
        def run_test(request_count, expected_count, disable_active_count_fix=False):
            req = make_new_request(request_count)
            if disable_active_count_fix:
                cluster_test.provider_config["symphony.disable_active_count_fix"] = True
            limited_req = cluster_test.limit_request_by_available_count(status, req, logging)
            self.assertEqual(limited_req["sets"][0]["count"], expected_count)  
        
        def run_test_zero_available(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                "machineType": "Standard_D2_v2"
            },"availableCount":0}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging) 
               
        def run_test_nodearray_removed(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute2", "buckets": [{"definition": {
                "machineType": "Standard_D2_v2"
            },"availableCount":100}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging) 

        def run_test_machine_type_removed(request_count):
            req = make_new_request(request_count)
            status={"nodearrays":[{ "name" : "execute", "buckets": [{"definition": {
                "machineType": "Standard_D1_v2"
            },"availableCount":100}]} ]}
            self.assertRaises(RuntimeError, cluster_test.limit_request_by_available_count, status, req, logging)       
        
        #Test if requested count is less than equal to available count                    
        run_test(1, 1)
        run_test(99, 99)
        run_test(100, 100)
        #Test if requested count is more than available count
        run_test(101, 100)  
        #Test runtime errors
        run_test_zero_available(10)
        run_test_nodearray_removed(10)
        run_test_machine_type_removed(10)
        #Test if active count fix is disabled
        run_test(101, 101, True)  
        
if __name__ == "__main__":
    unittest.main()
    