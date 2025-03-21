import collections
from copy import deepcopy
import json
import logging
import logging.config
from logging.handlers import RotatingFileHandler
from concurrent_log_handler import ConcurrentRotatingFileHandler
import os
import shutil
import subprocess
import sys
import traceback
import time
from builtins import str

import os


class UserError(Exception):
    pass


class ConfigError(Exception):
    pass


_logging_init = False

class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.operation_id = int(time.time())
        return super().format(record)

 
def init_logging(loglevel=logging.INFO, logfile=None):
    global _logging_init
    if logfile is None:
        logfile = "azurecc_prov.log"
    logfile_path = os.path.join(os.getenv("PRO_LOG_DIR", "."), logfile)
    
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(operation_id)s - %(asctime)s %(levelname)-8s %(message)s'
            },
        },
        'handlers': {
            'file': {
                # The values below are popped from this dictionary and
                # used to create the handler, set the handler's level and
                # its formatter.
                '()': ConcurrentRotatingFileHandler,
                'level': logging.INFO,
                'formatter': 'default',
                # The values below are passed to the handler creator callable
                # as keyword arguments.
                # 'owner': ['root', 'cyclecloud'],
                'filename': logfile_path,
            },
        },
        'root': {
            'handlers': ['file'],
            'level': logging.INFO,
            
        },
    }
    logging.config.dictConfig(LOGGING)
    
    try:
        root_logger = logging.getLogger()
        filtered_handlers = []
        for handler in root_logger.handlers:
            filtered_handlers.append(handler)
            
        root_logger.handlers = filtered_handlers
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.ERROR)
    except:
        pass
    
    # this is really chatty
    requests_logger = logging.getLogger("requests.packages.urllib3.connectionpool")
    requests_logger.setLevel(logging.WARN)
    
    logger = logging.getLogger("cyclecloud")
    
    if _logging_init:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    tenMB = 10 * 1024 * 1024
    logfile_handler = ConcurrentRotatingFileHandler(logfile_path, mode='a',maxBytes=tenMB, backupCount=5)
    logfile_handler.setLevel(loglevel)
    logfile_handler.setFormatter(CustomFormatter('%(operation_id)s - %(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    logger.addHandler(logfile_handler)
    
    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(logging.DEBUG)
    stderr_handler.setFormatter(CustomFormatter('%(operation_id)s - %(levelname)s - %(message)s'))
    
    logger.addHandler(stderr_handler)
    
    _logging_init = True
    
    return logger


class JsonStore:
    
    def __init__(self, name, directory, formatted=False):
        assert name not in ['hosts.json', 'requests.json'], "Illegal json name."
        self.path = os.path.join(directory, name)
        self.lockpath = self.path + ".lock"
        if not os.path.exists(self.lockpath):
            with open(self.lockpath, "a"):
                pass
        
        self.formatted = formatted
        self.data = None
        self.lockfp = None
        self.lock_count = 0
        self.logger = init_logging()

    def clear(self):
        with self as json_data:
            json_data = {}
            self.data = {}
    
    def _lock(self):
        self.lock_count += 1
        if self.lock_count > 1:
            return True
        iter = 0
        while iter < 18:
            iter += 1
            try:
                self.lockfp = open(self.lockpath, 'w')
                if os.name == 'nt':
                    self.logger.warning("Skip locking on windows.  TODO: replace fcntl for windows")
                else:
                    import fcntl
                    fcntl.lockf(self.lockfp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except IOError:
                self.logger.exception("Could not acquire lock - %s" % self.lockpath)
                time.sleep(10)
        return False
            
    def _unlock(self):
        self.lock_count -= 1
        if self.lock_count > 0:
            return
        
        try:
            self.lockfp.close()
        except IOError:
            self.logger.exception("Error closing lock - %s" % self.lockpath)
            
    def read(self):
        return self._read(do_lock=True)
            
    def _read(self, do_lock=True):
        if do_lock and not self._lock():
            raise RuntimeError("Could not get lock %s" % self.lockpath)
        
        if os.path.exists(self.path):
            try:
                self.data = load_json(self.path)
            except Exception:
                self.logger.exception("Could not reload %s - hosts may need to be manually removed from the system's hosts.json file." % self.path)
                self.data = {}
        else:
            self.data = {}
        
        if do_lock:
            self._unlock()
            
        return self.data
    
    def write(self, data):
        self._lock()
        self._write(data)
        self._unlock()
    
    def _write(self, data):
        with open(self.path + ".tmp", "w") as fw:
            indent = 2 if self.formatted else None
            json.dump(data, fw, indent=indent, sort_keys=True)
        shutil.move(self.path + ".tmp", self.path)
                  
    def __enter__(self):
        if not self._lock():
            raise RuntimeError("Could not get lock %s" % self.lockpath)
        return self._read(do_lock=False)         
    
    def __exit__(self, *args):
        self._write(self.data)
        self._unlock()
        

def failureresponse(response):
    '''
    Decorator to ensure that a sane default response is always sent back to Symphony.
    '''
    def decorator(func):
        def _wrap(*args, **kwargs):
            logger = init_logging()
            try:
                return func(*args, **kwargs)
            except UserError as ue:
                with_message = deepcopy(response)
                message = str(ue)
                logger.debug(traceback.format_exc())
                
                try:
                    message_data = json.loads(message)
                    message = "Http Status %(Code)s: %(Message)s" % message_data
                except Exception:
                    pass
                
                with_message["message"] = message
                # args[0] is  self
                return args[0].stdout_handler.try_handle(with_message)
            except Exception as e:
                logger.exception(str(e))
                logger.debug(traceback.format_exc())
                with_message = deepcopy(response)
                with_message["message"] = str(e)
                return args[0].stdout_handler.try_handle(with_message)
            except SystemExit as se:
                # NOTE: see terminate_machines for more info
                logger.exception("System Exit occured intentionally write 0 json so symphony recovers")
                raise
            except:  # nopep8 ignore the bare except
                logger.exception("Caught unknown exception...")
                logger.debug(traceback.format_exc())
                with_message = deepcopy(response)
                with_message["message"] = traceback.format_exc()
                return args[0].stdout_handler.try_handle(with_message)
        return _wrap
    return decorator


class ProviderConfig:
    
    def __init__(self, config, jetpack_config=None):
        self.config = config
        self.logger = init_logging()
        if jetpack_config is None:
            try:
                with open("/opt/cycle/jetpack/config/node.json") as json_file:
                    jetpack_config = json.load(json_file)
            except (FileNotFoundError) as ex:
                jetpack_config = {}
        self.jetpack_config = jetpack_config
        
    def get(self, key, default_value=None):
        if not key:
            return self.config
        
        keys = key.split(".")
        top_value = {**self.jetpack_config, **self.config}
        for n in range(len(keys)):
            if top_value is None:
                break
            
            if not hasattr(top_value, "keys"):
                self.logger.warning("Invalid format, as a child key was specified for %s when its type is %s ", key, type(top_value))
                return {}
                
            value = top_value.get(keys[n])
            
            if n == len(keys) - 1 and value is not None:
                return value
            
            top_value = value
            
        if top_value is None:
            try:
                return self.jetpack_config.get(key, default_value)
            except ConfigError as e:
                if key in str(e):
                    return default_value
                raise
        
        return top_value
    
    def set(self, key, value):
        keys = key.split(".")
        
        top_value = self.config
        for top_key in keys[:-1]: 
            tmp_value = top_value.get(top_key, {})
            top_value[top_key] = tmp_value
            top_value = tmp_value
            
        top_value[keys[-1]] = value

    def __str__(self) -> str:
        return json.dumps(self.config)


def provider_config_from_environment(pro_conf_dir=os.getenv('PRO_CONF_DIR', os.getcwd())):    
    config_file = os.path.join(pro_conf_dir, "conf", "azureccprov_config.json")
    if os.name == 'nt':
        # TODO: Why does the path matter?   Can we use one or the other for both OSs?
        config_file = os.path.join(pro_conf_dir, "azureccprov_config.json")


    hf_conf_dir = os.getenv('HF_CONFDIR', os.path.join(pro_conf_dir, "..", "..", ".."))
    hf_config_file = os.path.join(hf_conf_dir, "hostfactoryconf.json")
    
    delayed_log_statements = []
    
    # on disk configuration
    config = {}
    if os.path.exists(config_file):
        delayed_log_statements.append((logging.DEBUG, "Loading provider config: %s" % config_file))
        config = load_json(config_file)
    else:
        try:
            with open(config_file, "w") as fw:
                json.dump({}, fw)
            delayed_log_statements.append((logging.WARN, "Provider config does not exist, creating an empty one: %s" % config_file))
        except IOError:
            delayed_log_statements.append((logging.DEBUG, "Provider config does not exist and can't write a default one: %s" % config_file))
            
    if os.path.exists(hf_config_file):
        config.update(load_json(hf_config_file))

    import logging as logginglib
    log_level_name = config.get("log_level", "info")
    
    log_levels = {
        "debug": logginglib.DEBUG,
        "info": logginglib.INFO,
        "warn": logginglib.WARN,
        "error": logginglib.ERROR
    }
    
    fine = False
    if log_level_name.lower() == "fine":
        fine = True
        log_level_name = "debug"
    
    if log_level_name.lower() not in log_levels:
        delayed_log_statements.append(((logging.WARN, "Unknown logging level: %s" % log_level_name.lower())))
        log_level_name = "info"
    
    logger = init_logging(log_levels[log_level_name.lower()])
    
    for level, message in delayed_log_statements:
        logger.log(level, message)    
    return ProviderConfig(config), logger, fine


class Hostnamer:
    
    def __init__(self, use_fqdn=True):
        self.use_fqdn = use_fqdn
    
    def hostname(self, private_ip_address):
        stdout = subprocess.check_output(["getent", "hosts", private_ip_address]).decode()
        toks = [x.strip() for x in stdout.split()]
        if self.use_fqdn:
            if len(toks) >= 2:
                return toks[1]
            return toks[0]
        else:
            return toks[-1]
        
    def private_ip_address(self, hostname):
        stdout = subprocess.check_output(["getent", "hosts", hostname]).decode()
        toks = [x.strip() for x in stdout.split()]
        return toks[0]
    
        
def load_json(path):
    with open(path) as fr:
        return json.load(fr, object_pairs_hook=collections.OrderedDict)
