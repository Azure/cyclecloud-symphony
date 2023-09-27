import os
import json
from collections import OrderedDict
import math
import unittest
import cluster
import logging
from unittest.mock import MagicMock, patch
import string
SUCCESS = 1
FAILURE = 0


class WeightedTemplates():
    
    def __init__(self, cluster_name, provider_config, logger=None):        
            cluster_name = provider_config.get("cyclecloud.cluster.name")
            self.cluster=cluster.Cluster(cluster_name, provider_config, logger)
            self.logger = logger or logging.getLogger()
            
    def read_templates(self):
        template_dir="/mnt/c/Users/nidhimehta/Cyclecloud/linux_sym7_3/MS"
        conf_path = os.path.join(template_dir, "azureccprov_templates.json")
        with os.open(conf_path, 'r') as json_file:
            symphony_templates = json.load(json_file)
        return symphony_templates

    def create_machines(self, input_json, azurecc_template):
        symphony_templates = azurecc_template
        result = []
        for template in symphony_templates:
            if template["templateId"] == input_json["template"]["templateId"]:
                nodearray_name = template["attributes"]["nodearray"][1]
                vm_types_weight = template["vmTypes"]
                req_count = input_json["template"]["machineCount"]
                vm_priority_dict = template["vmTypePriority"]
                maxNumber = template["maxNumber"]
                if vm_priority_dict is None or vm_priority_dict == {}:
                    vm_types = template["vmTypes"]
                else:
                    vm_types = dict(sorted(vm_priority_dict.items(), key=lambda item: item[1], reverse=True))
                print(vm_types)
                for vm_type in vm_types:
                    avail_count = self.cluster.get_avail_count(vm_type, nodearray_name) 
                    print ("maxNumber: " + str(maxNumber)) 
                    print("avail_count: " + str(avail_count)) 
                    vm_type_weight = vm_types_weight[vm_type]    
                    print("vm type weight: " + str(vm_type_weight))
                    req_count_weight = math.ceil(req_count/vm_type_weight)   
                    if avail_count >=  req_count_weight:
                        if req_count_weight > maxNumber:
                            if maxNumber > 0:
                                print("Creating vmType: " + vm_type + " with count: " + str(maxNumber))
                                result.append((vm_type, maxNumber))
                                break
                            else:
                                print("Reached maxNumber")
                                break
                        print("Creating vmType: " + vm_type + " with count: " + str(req_count_weight))
                        result.append((vm_type, req_count_weight))
                        break                          
                    else:
                        if avail_count > 0:
                            if avail_count > maxNumber:
                                print("Creating vmType: " + vm_type + " with count: " + str(maxNumber))
                                print("Reached maxNumber")
                                result.append((vm_type, maxNumber))
                                break
                            print("Creating vmType: " + vm_type + " with count: " + str(avail_count))
                            req_count = req_count - avail_count * vm_type_weight
                            maxNumber = maxNumber - avail_count * vm_type_weight
                            result.append((vm_type, avail_count))
        return result

def azurecc_template_generate(vmTypes, vmTypePriority, maxNumber):
    azurecc_template = [{
      "templateId":   "execute",     
      "attributes" :   {
                "type": ["String", "X86_64"],
               "nram": ["Numeric", "4096"],
                "ncpus":    ["Numeric", 1],
                "nodearray":    ["String", "execute"]
                
            },
       "vmTypes": {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1},
       "vmTypePriority": {" Standard_D2_v2 ":1000, " Standard_D1_v2 ":100},
       "priceInfo":    ["String", "price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit"],
       "rank": ["Numeric", "0"],
       "maxNumber":    100
       }]
    azurecc_template[0]["vmTypes"] = vmTypes
    azurecc_template[0]["vmTypePriority"] = vmTypePriority 
    azurecc_template[0]["maxNumber"] = maxNumber
    return azurecc_template

class TestWeightedTemplate(unittest.TestCase):
    
    def setUp(self):
        self.weighted_template = WeightedTemplates("symphony", {"cyclecloud.cluster.name": "symphony"}, None)
    
    @patch('cluster.Cluster.status')
    def testInRangeMachineCount(self, mock_status):
        vmTypes = {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1}
        vmTypePriority = {" Standard_D2_v2 ":1000, " Standard_D1_v2 ":100}
        maxNumber = 100
        azurecc_template = azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 5}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 5}]}]}
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D2_v2 ", 5)])
        
        input_json["template"]["machineCount"] = 15
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D2_v2 ", 5), (" Standard_D1_v2 ", 5)])
        
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 10}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 10}]}]}
        input_json["template"]["machineCount"] = 25
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D2_v2 ", 10), (" Standard_D1_v2 ", 5)])
    
    @patch('cluster.Cluster.status')
    def testNoVMPriority(self, mock_status):
        vmTypes = { " Standard_D1_v2 ":1, " Standard_D2_v2 ":2}
        vmTypePriority = {}
        maxNumber = 100
        azurecc_template = azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 5}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 5}]}]}

        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D1_v2 ", 5), (" Standard_D2_v2 ", 3)])
        
        input_json["template"]["machineCount"] = 15
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D1_v2 ", 5), (" Standard_D2_v2 ", 5)])
        
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 10}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 10}]}]}
        input_json["template"]["machineCount"] = 25
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D1_v2 ", 10), (" Standard_D2_v2 ", 8)])
        
    @patch('cluster.Cluster.status')
    def testMaxNumberLessThanAvailCount(self, mock_status):
        vmTypes = { " Standard_D1_v2 ":1, " Standard_D2_v2 ":2}
        vmTypePriority = {}
        maxNumber = 5
        azurecc_template = azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 5}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 5}]}]}

        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D1_v2 ", 5)])
        
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 10}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 10}]}]}
        input_json["template"]["machineCount"] = 25
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D1_v2 ", 5)])
        
    @patch('cluster.Cluster.status')
    def test6SKUsAllESeries(self, mock_status):
        vmTypes = {"Standard_E2a_v4":2, "Standard_E4a_v4":4, "Standard_E8a_v4":8, "Standard_E16a_v4":16, "Standard_E32a_v4":32, "Standard_E64a_v4":64}
        vmTypePriority = {"Standard_E2a_v4":90, "Standard_E4a_v4":94, "Standard_E8a_v4":98, "Standard_E16a_v4":95, "Standard_E32a_v4":99, "Standard_E64a_v4":100}
        maxNumber = 1000
        azurecc_template = azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 100
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": "Standard_E2a_v4"}, "availableCount": 1000}, {"definition": {"machineType": "Standard_E4a_v4"}, "availableCount": 100}, {"definition": {"machineType": "Standard_E8a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E16a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E32a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E64a_v4"}, "availableCount": 10}]}]}
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEquals(result, [("Standard_E64a_v4", 2)])
        
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": "Standard_E2a_v4"}, "availableCount": 1000}, {"definition": {"machineType": "Standard_E4a_v4"}, "availableCount": 100}, {"definition": {"machineType": "Standard_E8a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E16a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E32a_v4"}, "availableCount": 0}, {"definition": {"machineType": "Standard_E64a_v4"}, "availableCount": 5}]}]}
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 900
            }
        }
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEquals(result, [("Standard_E64a_v4", 5), ("Standard_E8a_v4", 10), ("Standard_E16a_v4", 10), ("Standard_E4a_v4", 85)])
    
if __name__ == "__main__":
    unittest.main() 
