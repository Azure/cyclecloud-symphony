import unittest
from unittest.mock import MagicMock, patch
import cluster
import weighted_template_parse

class TestWeightedTemplate(unittest.TestCase):
    
    def setUp(self):
        cluster.new_node_manager = MagicMock(return_value=None)
        self.weighted_template = weighted_template_parse.WeightedTemplates("symphony", {"cyclecloud.cluster.name": "symphony","cyclecloud.config.web_server": "http://localhost","cyclecloud.config.username":"cc_admin", "cyclecloud.config.password":"password" }, None)

    @patch('cluster.Cluster.status')
    def testInRangeMachineCount(self, mock_status):
        vmTypes = {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1}
        vmTypePriority = {" Standard_D2_v2 ":1000, " Standard_D1_v2 ":100}
        maxNumber = 100
        azurecc_template = weighted_template_parse.azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10       #Interpreted as request for 10 compute units
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
    def testOutOfRangeMachineCount(self, mock_status):
        vmTypes = {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1}
        vmTypePriority = {" Standard_D2_v2 ":1000, " Standard_D1_v2 ":100}
        maxNumber = 2
        azurecc_template = weighted_template_parse.azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10       #Interpreted as request for 10 compute units
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": " Standard_D2_v2 "}, "availableCount": 1}, {"definition": {"machineType": " Standard_D1_v2 "}, "availableCount": 2}]}]}
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual( result, [(" Standard_D2_v2 ", 1)])
    
    @patch('cluster.Cluster.status')
    def testNoVMPriority(self, mock_status):
        vmTypes = { " Standard_D1_v2 ":1, " Standard_D2_v2 ":2}
        vmTypePriority = {}
        maxNumber = 100
        azurecc_template = weighted_template_parse.azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
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
        azurecc_template = weighted_template_parse.azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
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
        azurecc_template = weighted_template_parse.azurecc_template_generate(vmTypes, vmTypePriority, maxNumber)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 100
            }
        }
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": "Standard_E2a_v4"}, "availableCount": 1000}, {"definition": {"machineType": "Standard_E4a_v4"}, "availableCount": 100}, {"definition": {"machineType": "Standard_E8a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E16a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E32a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E64a_v4"}, "availableCount": 10}]}]}
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual(result, [("Standard_E64a_v4", 2)])
        
        mock_status.return_value = {"nodearrays": [{"name": "execute", "buckets": [{"definition": {"machineType": "Standard_E2a_v4"}, "availableCount": 1000}, {"definition": {"machineType": "Standard_E4a_v4"}, "availableCount": 100}, {"definition": {"machineType": "Standard_E8a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E16a_v4"}, "availableCount": 10}, {"definition": {"machineType": "Standard_E32a_v4"}, "availableCount": 0}, {"definition": {"machineType": "Standard_E64a_v4"}, "availableCount": 5}]}]}
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 900
            }
        }
        result = self.weighted_template.create_machines(input_json, azurecc_template)
        self.assertEqual(result, [("Standard_E64a_v4", 5), ("Standard_E8a_v4", 10), ("Standard_E16a_v4", 10), ("Standard_E4a_v4", 85)])
    
if __name__ == "__main__":
    unittest.main() 