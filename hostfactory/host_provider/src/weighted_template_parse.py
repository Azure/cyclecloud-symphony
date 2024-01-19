from collections import OrderedDict
import logging

class WeightedTemplates():
    
    def __init__(self, logger=None):        
            self.logger = logger or logging.getLogger()

    def parse_weighted_template(self, input_json, azurecc_template):
        symphony_templates = azurecc_template
        self.logger.debug("symphony_templates: %s", symphony_templates)
        vm_types = {}
        for template in symphony_templates:
            self.logger.debug("template: %s", template)
            self.logger.debug("templateId: %s", input_json["template"]["templateId"])
            if template["templateId"] == input_json["template"]["templateId"]:
                    vm_types = template["vmTypes"]
        return vm_types