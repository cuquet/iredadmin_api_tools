#!/usr/bin/env python3
import sys
import os
import json
import argparse
import time
import threading
import requests
import warnings

from urllib3.exceptions import NotOpenSSLWarning
# Ignorar avisos LibreSSL (macOS)
warnings.simplefilter("ignore", NotOpenSSLWarning)

DEFAULT_URL = os.getenv('IREDAPI_URL', 'https://localhost/iredadmin')
DEFAULT_COOKIE_JAR = os.path.expanduser('~/.iredapi_cookies.txt')

# === COLORS ANSI sense dependències externes ===
class AnsiColor:
    RESET = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    CYAN = '\033[36m'

def colorize_json(obj):
    """Pinta valors JSON bàsics amb colors ANSI."""
    if isinstance(obj, str):
        return AnsiColor.GREEN + f'"{obj}"' + AnsiColor.RESET
    elif isinstance(obj, bool):
        return AnsiColor.YELLOW + str(obj).lower() + AnsiColor.RESET
    elif obj is None:
        return AnsiColor.RED + 'null' + AnsiColor.RESET
    elif isinstance(obj, (int, float)):
        return AnsiColor.CYAN + str(obj) + AnsiColor.RESET
    elif isinstance(obj, list):
        return '[' + ', '.join(colorize_json(i) for i in obj) + ']'
    elif isinstance(obj, dict):
        items = []
        for k,v in obj.items():
            items.append(f'{AnsiColor.YELLOW}"{k}"{AnsiColor.RESET}: {colorize_json(v)}')
        return '{' + ', '.join(items) + '}'
    else:
        return str(obj)

def jp(data):
    """Pretty print JSON amb colors ANSI."""
    try:
        obj = json.loads(data) if isinstance(data, str) else data
        pretty = json.dumps(obj, indent=2, ensure_ascii=False)
        lines = pretty.splitlines()
        for line in lines:
            if ':' in line:
                key, val = line.split(':', 1)
                key_c = AnsiColor.YELLOW + key.strip() + AnsiColor.RESET
                val_strip = val.strip().rstrip(',')
                try:
                    val_obj = json.loads(val_strip)
                    val_c = colorize_json(val_obj)
                except Exception:
                    val_c = val_strip
                print(f"{key_c}: {val_c}")
            else:
                print(line)
    except Exception:
        print(data)

# === Spinner ASCII per feedback visual ===
class Spinner:
    def __init__(self, message="Processant..."):
        self.msg = message
        self.chars = '|/-\\'
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        def run():
            i = 0
            while self.running:
                print(f"\r{self.msg} {self.chars[i % len(self.chars)]}", end='', flush=True)
                time.sleep(0.1)
                i += 1
            print('\r' + ' ' * (len(self.msg) + 2) + '\r', end='', flush=True)
        self.thread = threading.Thread(target=run)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

def get_session(cookie_file):
    from http.cookiejar import MozillaCookieJar
    import os
    import requests

    session = requests.Session()
    session.cookies = MozillaCookieJar(cookie_file)
    if os.path.exists(cookie_file):
        session.cookies.load(ignore_discard=True, ignore_expires=True)
    return session

def should_skip_ssl_verification(args):
    # Ignora errors SSL si --insecure o variable d'entorn IREDAPI_INSECURE=1
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def login(args):
    session = get_session(args.cookies)
    url = f"{args.url}/api/login"
    data = {'username': args.username, 'password': args.password}
    verify = not should_skip_ssl_verification(args)

    spinner = Spinner("Fent login...")
    spinner.start()
    try:
        resp = session.post(url, data=data, verify=verify)
    finally:
        spinner.stop()

    if resp.status_code != 200:
        if args.raw:
            print(resp.text)
        else:
            print(f"{AnsiColor.RED}❌ Error login ({resp.status_code}):{AnsiColor.RESET} {resp.text}")
        return

    json_resp = resp.json()
    token = json_resp.get('token')
    if not token:
        print(f"{AnsiColor.RED}❌ Login fallit. No s'ha rebut cap token.{AnsiColor.RESET}")
        return

    session.cookies.save(ignore_discard=True, ignore_expires=True)
    with open(os.path.expanduser('~/.iredapi_token'), 'w') as f:
        f.write(token)
    # 👇 Mostra resposta segons --raw
    if args.raw:
        print(json.dumps(json_resp, indent=2, ensure_ascii=False))
    else:
        print(f"{AnsiColor.GREEN}✅ Login correcte. Token: {token[:10]}...{AnsiColor.RESET}")
        jp(json_resp)

def call(args):
    session = get_session(args.cookies)
    url = f"{args.url}{args.endpoint}"
    verify = not should_skip_ssl_verification(args)

    headers = {'Content-Type': 'application/json'}
    token = args.token
    if not token:
        token_file = os.path.expanduser('~/.iredapi_token')
        if os.path.exists(token_file):
            with open(token_file) as f:
                token = f.read().strip()
    if token:
        headers['Authorization'] = f"Bearer {token}"
    else:
        print(f"{AnsiColor.RED}❌ No s'ha trobat cap token. Fes login primer o usa --token.{AnsiColor.RESET}")
        return

    spinner = Spinner("Cridant a l'API...")
    spinner.start()
    try:
        method = args.method.upper()
        data_to_send = args.data.encode('utf-8') if args.data else None

        if method == 'GET':
            resp = session.get(url, headers=headers, verify=verify)
        elif method == 'POST':
            resp = session.post(url, headers=headers, verify=verify, data=data_to_send)
        elif method == 'PUT':
            resp = session.put(url, headers=headers, verify=verify, data=data_to_send)
        elif method == 'DELETE':
            resp = session.delete(url, headers=headers, verify=verify)
        elif method == 'PATCH':
            resp = session.patch(url, headers=headers, verify=verify, data=data_to_send)
        else:
            if not args.raw:
                print(f"{AnsiColor.RED}❌ Mètode HTTP no suportat: {method}{AnsiColor.RESET}")
            return
    finally:
        spinner.stop()

    if resp.status_code not in (200, 201, 204):
        if args.raw:
            print(resp.text)
        else:
            print(f"{AnsiColor.RED}❌ Error API ({resp.status_code}):{AnsiColor.RESET} {resp.text}")
        return
    
    if not args.raw:
        print(f"{AnsiColor.GREEN}✅ Resposta de l'API:{AnsiColor.RESET}")
    
    if resp.text:
        print(resp.text if args.raw else jp(resp.text))
    else:
        print("(Sense contingut de resposta)")

def logout(args):
    """Esborra fitxers de sessió: cookies i token."""
    # Esborra el fitxer de cookies
    try:
        os.remove(args.cookies)
        print(f"{AnsiColor.GREEN}✅ Fitxer de cookies '{args.cookies}' eliminat.{AnsiColor.RESET}")
    except FileNotFoundError:
        print(f"ℹ️ Fitxer de cookies '{args.cookies}' no existeix.")
    except Exception as e:
        print(f"{AnsiColor.RED}❌ Error eliminant cookies: {e}{AnsiColor.RESET}")

    # Esborra el fitxer de token
    token_file = os.path.expanduser('~/.iredapi_token')
    try:
        os.remove(token_file)
        print(f"{AnsiColor.GREEN}✅ Fitxer de token '{token_file}' eliminat.{AnsiColor.RESET}")
    except FileNotFoundError:
        print(f"ℹ️ Fitxer de token '{token_file}' no existeix.")
    except Exception as e:
        print(f"{AnsiColor.RED}❌ Error eliminant token: {e}{AnsiColor.RESET}")

def show_token(args):
    """Mostra el token d'autenticació desat, amb o sense format."""
    token_file = os.path.expanduser('~/.iredapi_token')
    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
        if args.raw:
            print(token)
        else:
            print(f"{AnsiColor.GREEN}🔑 Token actual:{AnsiColor.RESET} {token}")
    else:
        print(f"{AnsiColor.RED}❌ No s'ha trobat cap token desat. Fes login primer.{AnsiColor.RESET}")

def main():
    parser = argparse.ArgumentParser(
        prog='iredapi',
        description=(
            '🔐 CLI per a l\'API iRedAdmin\n\n'
            'Pots usar la variable d\'entorn IREDAPI_INSECURE=1 per ignorar errors SSL.\n'
            'Opció -k / --insecure equivalent a curl -k.\n'
            'La URL base per defecte és https://localhost/iredadmin però la pots canviar amb:\n'
            '  --url o la variable d\'entorn IREDAPI_URL\n'
            'Usa la subcomanda "jp" (integrada) per mostrar JSON bonic.\n'
            'però si indiques --raw, el JSON es mostra en format normal (sense codi de color).'
        ),
        epilog=(
            'ℹ️ Per a més ajuda, usa --help o ajuda subcomanda.\n'
            'ℹ️ Per a més informació sobre les API, visita: https://iredmail.org/api.html\n'
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-r', '--raw', action='store_true', help='Mostra les respostes en cru (sense colors ni format)')
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers(title='Subcomandes', dest='command')

    login_parser = subparsers.add_parser('login', help='Fes login i desa cookies')
    login_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API (ex: https://localhost/iredadmin)')
    login_parser.add_argument('--username', '-u', required=True, help='Nom d\'usuari')
    login_parser.add_argument('--password', '-p', required=True, help='Contrasenya')
    login_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=login)

    call_parser = subparsers.add_parser('call', help='Crida a un endpoint protegit')
    call_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    call_parser.add_argument('--endpoint', '-e', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
    call_parser.add_argument('--token', '-t', help='Token Bearer (opcional si has fet login abans)')
    call_parser.add_argument('--method', '-m', default='GET', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], help='Mètode HTTP per a la crida (GET per defecte)')
    call_parser.add_argument('--data', '-d',help='Dades a enviar en POST/PUT/PATCH (format text o JSON)')
    call_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    call_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    call_parser.set_defaults(func=call)

    logout_parser = subparsers.add_parser('logout', help='Esborra el fitxer de cookies')
    logout_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    logout_parser.set_defaults(func=logout)

    token_parser = subparsers.add_parser('token', help='Mostra el token desat')
    token_parser.add_argument('--raw', action='store_true', help='Mostra només el token sense colors ni prefix')
    token_parser.set_defaults(func=show_token)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
