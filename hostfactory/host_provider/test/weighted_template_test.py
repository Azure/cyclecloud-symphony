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
        "vmTypes": vmTypes,
        "priceInfo":    ["String", "price:0.1,billingTimeUnitType:prorated_hour,billingTimeUnitNumber:1,billingRoundoffType:unit"],
        "rank": ["Numeric", "0"],
        "maxNumber":    maxNumber
        }]
        return azurecc_template
class TestWeightedTemplate(unittest.TestCase):
    
    def setUp(self):
        self.weighted_template = weighted_template_parse.WeightedTemplates( None)
    
    def test_parse_weighted_template(self):
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 10       #Interpreted as request for 10 compute units
            }
        }

        vmTypes = {"Standard_D2_v2":2,  "Standard_D1_v2":1}
        templates = azurecc_template_generate(vmTypes)
        self.assertEqual(self.weighted_template.parse_weighted_template(input_json, templates), vmTypes)

        vmTypes = {"Standard_D2_v2":2,  "Standard_D1_v2":1, "Standard_D16_v2":16}
        templates = azurecc_template_generate(vmTypes)
        self.assertEqual(self.weighted_template.parse_weighted_template(input_json, templates), vmTypes)

    def test_allocate_weighted(self):
        vmTypes = {"Standard_D2_v2":2,  "Standard_D1_v2":1, "Standard_D16_v2":16}
        templates = azurecc_template_generate(vmTypes)
        input_json = {
            "template": {
                "templateId": "execute",
                "machineCount": 100       #Interpreted as request for 10 compute units
            }
        }

        # TODO : Mock out nodemgr and call allocate_weighted
         


if __name__ == "__main__":
    unittest.main() 