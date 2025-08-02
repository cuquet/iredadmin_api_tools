#!/usr/bin/env python3
import requests
import argparse
import os
import json
import warnings
from http.cookiejar import MozillaCookieJar
from urllib3.exceptions import NotOpenSSLWarning

'''
🧪 Exemples d’ús:
🔐 Login:
python3 iredapi.py login --username postmaster@melindro.org --password <password> -k

O, amb variable d’entorn:
IREDAPI_INSECURE=1 python3 iredapi.py login --username postmaster@melindro.org --password pwd

📡 Crida a l’API:
python3 iredapi.py call --endpoint /api/spampolicy/global -k

🆘 Ajuda CLI
python3 iredapi.py --help
python3 iredapi.py login --help

'''



# Evita avís per LibreSSL (macOS)
warnings.simplefilter("ignore", NotOpenSSLWarning)

DEFAULT_URL = 'https://localhost/iredadmin'
DEFAULT_COOKIE_JAR = os.path.expanduser('~/.iredapi_cookies.txt')

def get_session(cookie_file):
    session = requests.Session()
    session.cookies = MozillaCookieJar(cookie_file)
    if os.path.exists(cookie_file):
        session.cookies.load(ignore_discard=True, ignore_expires=True)
    return session

def should_skip_ssl_verification(args):
    """Determina si s’ha d’ignorar SSL (via -k o IREDAPI_INSECURE)"""
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def login(args):
    session = get_session(args.cookies)
    url = f"{args.url}/api/login"
    data = {'username': args.username, 'password': args.password}
    verify = not should_skip_ssl_verification(args)

    resp = session.post(url, data=data, verify=verify)
    if resp.status_code != 200:
        print(f"❌ Error login ({resp.status_code}): {resp.text}")
        return

    json_resp = resp.json()
    token = json_resp.get('token')
    if not token:
        print("❌ Login fallit. No s'ha rebut cap token.")
        return

    session.cookies.save(ignore_discard=True, ignore_expires=True)
    print(f"✅ Login correcte. Token: {token[:10]}...")
    print(json.dumps(json_resp, indent=2))

def call(args):
    session = get_session(args.cookies)
    url = f"{args.url}{args.endpoint}"
    verify = not should_skip_ssl_verification(args)

    headers = {}
    if args.token:
        headers['Authorization'] = f"Bearer {args.token}"

    resp = session.get(url, headers=headers, verify=verify)
    if resp.status_code != 200:
        print(f"❌ Error API ({resp.status_code}): {resp.text}")
        return

    print("✅ Resposta de l'API:")
    print(json.dumps(resp.json(), indent=2))

def main():
    parser = argparse.ArgumentParser(
        prog='iredapi',
        description='🔐 Eina CLI per consultar l\'API d\'iRedAdmin',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers(title='Subcomandes', dest='command')

    # 🔐 LOGIN
    login_parser = subparsers.add_parser('login', help='Fes login i desa cookies')
    login_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    login_parser.add_argument('--username', required=True, help='Nom d\'usuari (ex: postmaster@domini)')
    login_parser.add_argument('--password', required=True, help='Contrasenya')
    login_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer per desar cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=login)

    # 📡 CALL
    call_parser = subparsers.add_parser('call', help='Crida a un endpoint protegit')
    call_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    call_parser.add_argument('--endpoint', required=True, help='Endpoint d\'API (ex: /api/spampolicy/global)')
    call_parser.add_argument('--token', help='Token Bearer (si no es vol usar cookies)')
    call_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer de cookies')
    call_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    call_parser.set_defaults(func=call)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()

