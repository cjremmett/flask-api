from utils import get_api_key, append_to_log, authorized_via_redis_token
import requests
from flask import request


def update_dynamic_dns_namecheap(host: str, domain_name: str, ddns_password: str, ip: str) -> None:
    try:
        requests.get(f'https://dynamicdns.park-your-domain.com/update?host={host}&domain={domain_name}&password={ddns_password}&ip={ip}')
        append_to_log('flask_logs', 'DYNAMIC_DNS', 'INFO', f'Updated NameCheap DNS for {domain_name} with IP address {ip}.')
    except Exception as e:
        append_to_log('flask_logs', 'DYNAMIC_DNS', 'ERROR', 'Exception thrown in update_dynamic_dns_namecheap: ' + repr(e))


def get_namecheap_password() -> str:
    try:
        return get_api_key('namecheap')
    except Exception as e:
        append_to_log('flask_logs', 'DYNAMIC_DNS', 'ERROR', 'Exception thrown in get_namecheap_password: ' + repr(e))


def update_namecheap_dns_record():
    try:
        if not authorized_via_redis_token(request, 'ddns'):
            return ('', 401)
        
        ddns_password = get_namecheap_password()
        host = request.args.get('host')
        domain_name = request.args.get('domain_name')
        ip = get_public_ip()
        update_dynamic_dns_namecheap(host, domain_name, ddns_password, ip)
    except Exception as e:
        append_to_log('flask_logs', 'DYNAMIC_DNS', 'ERROR', 'Exception thrown in get_namecheap_password: ' + repr(e))


def get_public_ip() -> str:
    try:
        response = requests.get('https://dynamicdns.park-your-domain.com/getip')
        return response.text
    except Exception as e:
        append_to_log('flask_logs', 'DYNAMIC_DNS', 'ERROR', 'Exception thrown in get_public_ip: ' + repr(e))
        return None