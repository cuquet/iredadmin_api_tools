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

'''
⚡️ Com utilitzar
Quan fas login o crides API, veuràs un spinner ASCII | / - \ per indicar que està treballant.
El JSON que imprimeix està acolorit per tipus de valor amb codis ANSI, compatible amb la majoria de terminals.
Pots passar la URL base via variable IREDAPI_URL o per l’argument --url (té prioritat l’argument).
Opció -k o variable IREDAPI_INSECURE=1 per ignorar errors SSL (com curl -k).

# Login (ignora SSL)
python3 iredapi.py login --username postmaster@melindro.org --password pwd -k

# Crida a l'API amb cookies guardades
python3 iredapi.py call --endpoint /api/spampolicy/global

# Crida a l'API passant token manual
python3 iredapi.py call --endpoint /api/spampolicy/global --token CfOM847tVQkSm-UDiGUYHTFBuOcQ1XcswBaumgluoB8=

# Esborrar cookies
python3 iredapi.py logout

# Mostrar token
$ python3 iredapi.py token
🔑 Token actual: xQKa_TszBU...

$ python3 iredapi.py token --raw
xQKa_TszBU...

$ python3 iredapi.py token 
❌ No s'ha trobat cap token desat. Fes login primer.
'''


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
        # Simple impressió indentada per claredat
        pretty = json.dumps(obj, indent=2, ensure_ascii=False)
        # Per fer-ho ràpid: pintem línia a línia substituint valors per versions acolorides
        # Per simplificar, només pintarem clau i valors simples a nivell superficial.
        # Un formatador JSON molt avançat és més complex, però això ja ajuda molt.
        # Aquí només apliquem colors a valors simples en línies amb ":"
        lines = pretty.splitlines()
        for line in lines:
            if ':' in line:
                key, val = line.split(':', 1)
                key_c = AnsiColor.YELLOW + key.strip() + AnsiColor.RESET
                # Intentar interpretar val com a JSON per pintar
                val_strip = val.strip().rstrip(',')  # treu coma si n'hi ha
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
        print(f"{AnsiColor.RED}❌ Error login ({resp.status_code}):{AnsiColor.RESET} {resp.text}")
        return

    json_resp = resp.json()
    token = json_resp.get('token')
    if not token:
        print(f"{AnsiColor.RED}❌ Login fallit. No s'ha rebut cap token.{AnsiColor.RESET}")
        return

    session.cookies.save(ignore_discard=True, ignore_expires=True)
    print(f"{AnsiColor.GREEN}✅ Login correcte. Token: {token[:10]}...{AnsiColor.RESET}")
    with open(os.path.expanduser('~/.iredapi_token'), 'w') as f:
        f.write(token)
    jp(json_resp)

def call(args):
    session = get_session(args.cookies)
    url = f"{args.url}{args.endpoint}"
    verify = not should_skip_ssl_verification(args)

    headers = {}
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
        resp = session.get(url, headers=headers, verify=verify)
    finally:
        spinner.stop()

    if resp.status_code != 200:
        print(f"{AnsiColor.RED}❌ Error API ({resp.status_code}):{AnsiColor.RESET} {resp.text}")
        return

    print(f"{AnsiColor.GREEN}✅ Resposta de l'API:{AnsiColor.RESET}")
    jp(resp.text)

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
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers(title='Subcomandes', dest='command')

    login_parser = subparsers.add_parser('login', help='Fes login i desa cookies')
    login_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API (ex: https://localhost/iredadmin)')
    login_parser.add_argument('--username', required=True, help='Nom d\'usuari')
    login_parser.add_argument('--password', required=True, help='Contrasenya')
    login_parser.add_argument('--cookies', default=DEFAULT_COOKIE_JAR, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=login)

    call_parser = subparsers.add_parser('call', help='Crida a un endpoint protegit')
    call_parser.add_argument('--url', default=DEFAULT_URL, help='URL base de l\'API')
    call_parser.add_argument('--endpoint', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
    call_parser.add_argument('--token', help='Token Bearer (opcional si has fet login abans)')
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
    args.func(args)

if __name__ == '__main__':
    main()
