
import os
import requests
import time
import json
import urllib3

ilm_policies = {
  "default-norollover": """{
    "policy": {
      "phases": {
        "hot": {
          "min_age": "0ms",
          "actions": {
            "set_priority": {
              "priority": 100
            }
          }
        },
        "warm": {
          "min_age": "7d",
          "actions": {
            "forcemerge": {
              "max_num_segments": 1
            },
            "readonly": {},
            "set_priority": {
              "priority": 50
            },
            "shrink": {
              "number_of_shards": 1
            }
          }
        },
        "delete": {
          "min_age": "30d",
          "actions": {
            "delete": {
              "delete_searchable_snapshot": true
            }
          }
        }
      }
    }
  }""",
  "default-rollover": """{
    "policy": {
      "phases": {
        "hot": {
          "min_age": "0ms",
          "actions": {
            "rollover": {
              "max_primary_shard_size": "20gb",
              "max_age": "7d"
            },
            "set_priority": {
              "priority": 100
            }
          }
        },
        "warm": {
          "min_age": "7d",
          "actions": {
            "forcemerge": {
              "max_num_segments": 1
            },
            "readonly": {},
            "set_priority": {
              "priority": 50
            },
            "shrink": {
              "number_of_shards": 1
            }
          }
        },
        "delete": {
          "min_age": "30d",
          "actions": {
            "delete": {
              "delete_searchable_snapshot": true
            }
          }
        }
      }
    }
  }"""
}

class SessionConfig:
  def __init__(self):
    self.elastic_username = os.environ.get('CONNECTION_USERNAME')
    if self.elastic_username is None or self.elastic_username == "":
      raise Exception('Missing elastic_username')

    self.elastic_password = os.environ.get('CONNECTION_PASSWORD')
    if self.elastic_password is None or self.elastic_password == "":
      raise Exception('Missing elastic_password')

    self.elastic_host = os.environ.get('ELASTIC_HOST')
    if self.elastic_host is None or self.elastic_host == "":
      raise Exception('Missing elastic_host')

    port = os.environ.get('ELASTIC_PORT')
    if port is None or port == "":
      raise Exception('Missing elastic_port')

    self.elastic_port = 0
    try:
      self.elastic_port = int(port)
    except Exception as e:
      raise Exception('Could not parse elastic_port: %s' % e)

    self.elastic_uri = ""
    uri = os.environ.get('ELASTIC_URI')
    if uri is not None and uri != "":
      self.elastic_uri = uri.rstrip('/') + "/"

    if self.elastic_uri is None or self.elastic_uri == "":
      self.elastic_uri = ("https://%s:%s/" % (self.elastic_host, self.elastic_port))

    self.elastic_auth = (self.elastic_username, self.elastic_password)

    # Configure requests session
    self.requestsSession = requests.Session()
    self.requestsSession.auth = self.elastic_auth
    self.requestsSession.verify = False
    self.requestsSession.headers = {
      "Content-Type": "application/json"
    }

def log_msg(msg):
  print(msg, flush=True)

def debug_request_result(result):
  log_msg('Request Result: %s' % result.text)
  log_msg('Request Status Code: %s' % result.status_code)

#
# set_ilm_policy - Apply an ILM policy to the elastic environment
def set_ilm_policy(session, name, content, update=False):
  policy_uri = session.elastic_uri + "_ilm/policy/" + name

  # Check if the ILM policy exists
  log_msg('Checking for ILM policy: %s' % name)
  result = session.requestsSession.get(policy_uri)
  debug_request_result(result)

  # If the policy does not exist, create it
  if result.status_code == 404:
    log_msg('ILM policy not found. Creating.')
    result = session.requestsSession.put(policy_uri, content)
    debug_request_result(result)
    result.raise_for_status()
    if result.json()['acknowledged'] != True:
      raise Exception('Failed to create ILM policy - acknowledgement missing')
    log_msg('Create for ILM policy successful.')
    return

  # Make sure we were successful
  result.raise_for_status()
  log_msg('ILM Policy found')

  # Status is not missing and not error, so the ILM policy exists. Update it here, if requested
  if update:
    log_msg('Updating ILM policy')
    result = session.requestsSession.put(policy_uri, content)
    debug_request_result(result)
    result.raise_for_status()
    if result.json()['acknowledged'] != True:
      raise Exception('Failed to update ILM policy - acknowledgement missing')

#
# set_user - Create/Update a user account for the elastic environment
def set_user(session, name, content, update=False):
  user_uri = session.elastic_uri + "_security/user/" + name

  # Check if the user exists
  log_msg('Checking for user: %s' % name)
  result = session.requestsSession.get(user_uri)
  debug_request_result(result)

  # If the user does not exist, create it
  if result.status_code == 404:
    log_msg('User not found. Creating.')
    result = session.requestsSession.post(user_uri, content)
    debug_request_result(result)
    result.raise_for_status()
    if result.json()['created'] is None:
      raise Exception('Failed to create user - created field missing')
    log_msg('Create for user successful.')
    return

  # Make sure we were successful
  result.raise_for_status()
  log_msg('User found')

  # Status is not missing and not error, so the user exists. Update it here, if requested
  if update:
    log_msg('Updating user')
    result = session.requestsSession.put(user_uri, content)
    debug_request_result(result)
    result.raise_for_status()
    if result.json()['created'] is None:
      raise Exception('Failed to update user - created field missing')

#
# set_cluster_setting - Post JSON to the cluster setting sapi
def set_cluster_setting(session, name, content):
  setting_uri = session.elastic_uri + "_cluster/settings"

  log_msg('Updating cluster setting: %s' % name)
  result = session.requestsSession.put(setting_uri, content)
  debug_request_result(result)
  result.raise_for_status()
  if result.json()['acknowledged'] != True:
    raise Exception('Failed to update cluster settings - not acknowledged')

#
# set_user_password - update the password for a user
def set_user_password(session, name, password):
  user_uri = session.elastic_uri + "_security/user/" + name + "/_password"

  if password is None or password == "":
    raise Exception('Missing password for user')

  log_msg('Updating user password: %s' % name)
  result = session.requestsSession.put(user_uri, """{ "password": %s }""" % json.dumps(password))
  debug_request_result(result)
  result.raise_for_status()

#
# wait_connection - wait for the elastic environment to become ready
def wait_connection(session):
  check_uri = session.elastic_uri + "_cat/health?format=json"

  attempt = 1
  while True:
    # Attempt to connect to the elastic environment
    log_msg('Elastic connection attempt: %s' % attempt)
    try:
      result = requests.get(check_uri, auth=session.elastic_auth, verify=False)
      debug_request_result(result)

      # Return if we connected and the cluster status is green
      if result.ok and result.json()[0]['status'] == 'green':
        return
    except Exception as e:
      log_msg('Could not connect to elastic: %s' % e)

    # Break here if we have tried too many times
    attempt = attempt + 1
    if attempt > 30:
      # If we've exhausted all attempts, but the status is still red or yellow,
      # then return and attempt to perform the elastic configuration anyway.
      if result.ok:
        return
      raise Exception('Could not connect to elastic and exhausted attempts')

    # Wait 30 seconds before trying again
    time.sleep(30)

def main():

  # Disable cert warnings for urllib3/requests
  urllib3.disable_warnings()

  # Session setup for connectivity to the elastic environment
  session = SessionConfig()
  log_msg('Elastic URI: %s' % session.elastic_uri)
  log_msg('Elastic Username: %s' % session.elastic_username)

  # Wait for the elastic environment to become available
  log_msg('Starting wait for elastic environment')
  wait_connection(session)

  # Apply ILM policies to the environment
  for key in ilm_policies.keys():
    set_ilm_policy(session, key, ilm_policies[key])

  # Set user passwords
  password = os.environ.get('LOGSTASH_SYSTEM_PASSWORD')
  if password is not None and password != "":
    set_user_password(session, "logstash_system", password)

  password = os.environ.get('BEATS_SYSTEM_PASSWORD')
  if password is not None and password != "":
    set_user_password(session, "beats_system", password)

  password = os.environ.get('KIBANA_SYSTEM_PASSWORD')
  if password is not None and password != "":
    set_user_password(session, "kibana_system", password)

  password = os.environ.get('APM_SYSTEM_PASSWORD')
  if password is not None and password != "":
    set_user_password(session, "apm_system", password)

  password = os.environ.get('ELASTIC_PASSWORD')
  if password is not None and password != "":
    set_user_password(session, "elastic", password)

  # Logstash user configuration
  logstash_username = os.environ.get('LOGSTASH_USERNAME')
  logstash_password = os.environ.get('LOGSTASH_PASSWORD')

  if logstash_username is None or logstash_username == "":
    raise Exception('Missing logstash username')

  if logstash_password is None or logstash_password == "":
    raise Exception('Missing logstash password')

  set_user(session, logstash_username, """
  {
    "enabled": true,
    "password": %s,
    "roles": [ "superuser" ]
  }
  """ % json.dumps(logstash_password), update=True)

  # Filebeat user configuration
  filebeat_username = os.environ.get('FILEBEAT_USERNAME')
  filebeat_password = os.environ.get('FILEBEAT_PASSWORD')

  if filebeat_username is None or filebeat_username == "":
    raise Exception('Missing filebeat username')

  if filebeat_password is None or filebeat_password == "":
    raise Exception('Missing filebeat password')

  set_user(session, filebeat_username, """
  {
    "enabled": true,
    "password": %s,
    "roles": [ "superuser" ]
  }
  """ % json.dumps(filebeat_password), update=True)

  set_cluster_setting(session, "auto_create_index", """{
    "persistent": {
      "action": {
        "auto_create_index": "false"
      }
    }
  }""")

if __name__ == "__main__":
  main()
