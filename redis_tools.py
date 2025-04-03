import redis
import json
import os
import sys
REDIS_HOST = '192.168.0.121'
SECRETS_DIR = '/home/cjr/secrets'

def get_json_from_file_as_dict(file):
    try:
        with open(file, 'r') as f:
            return json.loads(f.read())
    except:
        print('Unable to read JSON from ' + file)
        return None
    

def get_all_files_in_directory(directory):
    try:
        files = []
        for object in os.listdir(directory):
            if os.path.isfile(directory + '/' + object):
                files.append(directory + '/' + object)
            else:
                files += get_all_files_in_directory(directory + '/' + object)
        
        return files
    except:
        raise Exception('Failed to enumerate files in directory ' + directory)
    

def get_concatenated_secrets_dict(directory):
    secrets_dict = {'secrets': {}}
    directory = os.path.abspath(directory)
    for file in get_all_files_in_directory(directory):
        contents = get_json_from_file_as_dict(file)
        if contents:
            (secrets_dict['secrets'])[os.path.basename(file).split('.')[0]] = contents

    return secrets_dict


def get_redis_cursor(host='localhost', port=6379):
    return redis.Redis(host, port, db=0, decode_responses=True)


def load_secrets_into_redis(directory):
    try:
        r = get_redis_cursor(host=REDIS_HOST)
        r.json().set('secrets', '$', get_concatenated_secrets_dict(directory))
        return True
    except:
        return False


def get_secrets_dict():
    """
    Gets the secrets dictionary from Redis.
    If the dictionary is empty (probably because it hasn't been loaded yet), load it first then return it.
    """
    r = get_redis_cursor(host=REDIS_HOST)
    secrets_list = r.json().get('secrets', '$')
    if not secrets_list or len(secrets_list) == 0:
        result = load_secrets_into_redis(SECRETS_DIR)
        secrets_list = r.json().get('secrets', '$')
        if result == True and len(secrets_list) == 1:
            return secrets_list[0]
        else:
            raise Exception('Failed to get secrets dictionary from Redis.')
    else:
        return secrets_list[0]
    

if __name__ == '__main__':
    if '--reload' in sys.argv or '-r' in sys.argv:
        if load_secrets_into_redis(SECRETS_DIR) == True:
            print('Loaded secrets into Redis successfully.')
        else:
            print('Failed to load secerts into Redis.')
    else:
        print('Options:\n--reload (-r) -> Loads secrets into Redis.')