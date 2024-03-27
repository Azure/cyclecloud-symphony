import unittest
from unittest.mock import MagicMock, patch
import weighted_template_parse
import cyclecloud_provider


def azurecc_template_generate(vmTypes, maxNumber=100):
        azurecc_template = [{
        "templateId":   "execute",     
        "attributes" :   {
                    "type": ["String", "X86_64"],
                "nram": ["Numeric", "4096"],
                    "ncpus":    ["Numeric", 1],
                    "nodearray":    ["String", "execute"]
                    
                },
        "vmTypes": {" Standard_D2_v2 ":2, " Standard_D1_v2 ":1},
        "priceInfo":    ["String", "price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit"],
        "rank": ["Numeric", "0"],
        "maxNumber":    100
        }]
        azurecc_template[0]["vmTypes"] = vmTypes
        azurecc_template[0]["maxNumber"] = maxNumber
        return azurecc_template
class TestWeightedTemplate(unittest.TestCase):
    
    def setUp(self):
        self.weighted_template = weighted_template_parse.WeightedTemplates( None)
    
    def test_parse_weighted_template(self):
        vmTypes = {"Standard_D2_v2":2,  "Standard_D1_v2":1}
        templates = azurecc_template_generate(vmTypes)
        print(templates)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10       #Interpreted as request for 10 compute units
            }
        }
        self.assertEqual(self.weighted_template.parse_weighted_template(input_json, templates), vmTypes)
    
if __name__ == "__main__":
    unittest.main() 