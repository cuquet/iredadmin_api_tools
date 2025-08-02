#!/usr/bin/env python3
import sys
import os
import json
import argparse
from http.cookiejar import MozillaCookieJar
import warnings

'''
⚡️ Com utilitzar

# Login (ignora SSL)
python3 iredapi.py login --username postmaster@melindro.org --password <password> -k

# Crida a l'API amb cookies guardades
python3 iredapi.py call --endpoint /api/spampolicy/global

# Crida a l'API passant token manual
python3 iredapi.py call --endpoint /api/spampolicy/global --token TOKEN

# Esborrar cookies
python3 iredapi.py logout
'''

# Comprovació de dependències
missing = []
try:
    import requests
except ImportError:
    missing.append("requests")
try:
    import urllib3
except ImportError:
    missing.append("urllib3")

if missing:
    print(f"❌ Dependències mancants: {', '.join(missing)}")
    print("🔧 Executa: pip install " + ' '.join(missing))
    sys.exit(1)

import requests
from urllib3.exceptions import NotOpenSSLWarning

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
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def jp(data):
    """Json pretty print"""
    try:
        obj = json.loads(data) if isinstance(data, str) else data
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    except Exception:
        print(data)  # fallback, print raw

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
    jp(json_resp)

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
    jp(resp.text)

def logout(args):
    try:
        os.remove(args.cookies)
        print(f"✅ Fitxer de cookies '{args.cookies}' eliminat.")
    except FileNotFoundError:
        print(f"ℹ️ Fitxer de cookies '{args.cookies}' no existeix.")
    except Exception as e:
        print(f"❌ Error eliminant cookies: {e}")

def main():
    parser = argparse.ArgumentParser(
        prog='iredapi',
        description='🔐 CLI per a l\'API iRedAdmin\n\n'
                    'Pots usar la variable d\'entorn IREDAPI_INSECURE=1 per ignorar errors SSL.\n'
                    'Opció -k / --insecure equivalent a curl -k.\n'
                    'Usa la subcomanda "jp" per mostrar JSON bonic (json pretty print).\n',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers(title='Subcomandes', dest='command')

    login_parser = subparsers.add_parser('login', help='Fes login i desa cookies')
    login_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    login_parser.add_argument('--username', required=True, help='Nom d\'usuari')
    login_parser.add_argument('--password', required=True, help='Contrasenya')
    login_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=login)

    call_parser = subparsers.add_parser('call', help='Crida a un endpoint protegit')
    call_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    call_parser.add_argument('--endpoint', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
    call_parser.add_argument('--token', help='Token Bearer (si no vols usar cookies)')
    call_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    call_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    call_parser.set_defaults(func=call)

    logout_parser = subparsers.add_parser('logout', help='Esborra el fitxer de cookies')
    logout_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    logout_parser.set_defaults(func=logout)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
