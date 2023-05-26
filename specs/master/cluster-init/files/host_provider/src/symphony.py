import json

import logging
import requests
from shutil import which
from urllib.parse import urlencode

class MachineStates:
    building = "building"
    active = "active"
    error = "error"
    deleting = "deleting"
    deleted = "deleted"
    
    
class MachineResults:
    succeed = "succeed"
    executing = "executing"
    failed = "fail"
# LSF:    failed = "failed"
    
    
class RequestStates:
    running = "running"
    complete = "complete"
    complete_with_error = "complete_with_error"



class SymphonyRestClient:

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger or logging.getLogger()
        self.webserviceUrl = self.rest_url()
        self.username = self.config.get('symphony.soam.user', 'Admin')
        self.password = self.config.get('symphony.soam.password', 'Admin')
        self.token = None

    def rest_url(self):
        import os
        import subprocess

        egosh_cmd = "egosh"
        url = None
        try:
            # Firt, try to get the url from ego (supports manual cluster config changes)
            # egosh client view REST_HOST_FACTORY_URL | grep DESCRIPTION | sed 's/^DESCRIPTION\:\s//g' -
            # add which or command -v
            if "EGO_BINDIR" in os.environ:
                egosh_cmd = os.path.join(os.environ["EGO_BINDIR"], egosh_cmd)
            elif "EGO_LIBDIR" in os.environ:
                egosh_cmd = os.path.join(os.environ["EGO_LIBDIR"], "..", "bin", egosh_cmd)
            else:
                # which returns nothing, so revert to the default
                egosh_cmd = which(egosh_cmd) or egosh_cmd

            client_view = subprocess.check_output([egosh_cmd, 'client', 'view', 'REST_HOST_FACTORY_URL']).decode()
            description = [x for x in client_view.splitlines() if 'DESCRIPTION' in x][0]
            url = description.split()[1]
        except:        
            self.logger.exception(f"Failed to read REST service URL from {egosh_cmd}.  Will attempt to use local config.")

            # It's possible to the url from ego (supports manual cluster config changes)
            #     egosh client view REST_HOST_FACTORY_URL | grep DESCRIPTION | sed 's/^DESCRIPTION\:\s//g' -
            # But HostFactory does not have the correct environment for egosh
            # Instead, generate the url from cluster config
            webserviceHostname = self.config.get('symphony.hostfactory.rest_address', '127.0.0.1')
            webservicePort = self.config.get('HF_REST_LISTEN_PORT', self.config.get('symphony.hostfactory.HF_REST_LISTEN_PORT', '9080'))
            webserviceSsl = self.config.get('HF_REST_TRANSPORT', self.config.get('symphony.hostfactory.HF_REST_TRANSPORT', 'TCPIPv4')).lower() == 'TCPIPv4SSL'.lower()
            prefix = 'https' if webserviceSsl else 'http'
            url = '%s://%s:%s/platform/rest/hostfactory' % (prefix, webserviceHostname, webservicePort)

        self.logger.info(f"Using HF URL: {url.rstrip('/')}")
        return url.rstrip('/')

    def _raise_on_error(self, r):
        self.logger.info("Symphony REST API [%s] response (%s)", r.url, r.status_code)
        if 400 <= r.status_code < 500:
            if r.text:
                raise Exception("Invalid Symphony REST call (%s): %s" % (r.status_code, r.text))
            else:
                raise Exception("Unspecified Symphony REST Error (%s)" % r.status_code)

        r.raise_for_status()        
    
    def _login(self):
        url = self.webserviceUrl + '/auth/login'
        r = requests.get(url, auth=(self.username, self.password), verify=False)
        self._raise_on_error(r)
        
        hfcsrftokenBody = r.json()
        self.token = hfcsrftokenBody['hfcsrftoken']
        return self.token

    def update_hostfactory_templates(self, templates):
        self.logger.debug("BEGIN UPDATE TEMPLATES")
        hfcsrftoken = self._login()
        params = {'hfcsrftoken': hfcsrftoken}
        url = self.webserviceUrl + '/provider/azurecc/templates'
        r = requests.put(url, auth=(self.username, self.password), params=params, json=templates, verify=False)
        self.logger.debug("END UPDATE TEMPLATES")
        self._raise_on_error(r)
