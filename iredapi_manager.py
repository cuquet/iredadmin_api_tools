#!/usr/bin/env python3
import os
import sys
import json
import argparse
import getpass
import time
import threading
import requests
import logging
#import pickle

from http.cookiejar import MozillaCookieJar

API_BASE = os.getenv('IREDAPI_URL', 'https://localhost/iredadmin/api')
TOKEN_FILE = os.path.expanduser('~/.iredapi_token')
COOKIE_FILE = os.path.expanduser('~/.iredapi_cookies.txt')
LOGFILE = os.path.expanduser('~/.iredapi.log')
# Detectar RAW mode via variable d'entorn
RAW_MODE = os.getenv('IREDAPI_RAW', '0') == '1'

logging.basicConfig(filename=LOGFILE, level=logging.WARNING)

class AnsiColor:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def print_error(msg, raw=False):
    output = msg if raw else f"{AnsiColor.RED}\u274c {msg}{AnsiColor.RESET}"
    print(output)

def print_success(msg, raw=False):
    output = msg if raw else f"{AnsiColor.GREEN}\u2705 {msg}{AnsiColor.RESET}"
    print(output)

def color_json(data, indent=0):
    INDENT_STR = "  "
    def colorize(obj, level):
        pad = INDENT_STR * level
        pad_next = INDENT_STR * (level + 1)
        
        if isinstance(obj, dict):
            if not obj:
                return '{}'
            items = []
            for k, v in obj.items():
                colored_key = f'{AnsiColor.YELLOW}"{k}"{AnsiColor.RESET}'
                colored_val = colorize(v, level + 1)
                items.append(f'{pad_next}{colored_key}: {colored_val}')
            return '{\n' + ',\n'.join(items) + f'\n{pad}' + '}'
        elif isinstance(obj, list):
            if not obj:
                return '[]'
            items = [colorize(i, level + 1) for i in obj]
            return '[\n' + ',\n'.join(f'{pad_next}{item}' for item in items) + f'\n{pad}]'
        elif isinstance(obj, str):
            return f'{AnsiColor.GREEN}"{obj}"{AnsiColor.RESET}'
        elif isinstance(obj, bool):
            return f'{AnsiColor.CYAN}{obj}{AnsiColor.RESET}'
        elif obj is None:
            return f'{AnsiColor.RED}null{AnsiColor.RESET}'
        else:
            return f'{AnsiColor.CYAN}{obj}{AnsiColor.RESET}'

    return colorize(data, indent)

def jp(data, raw=False):
    if raw:
        if isinstance(data, str):
            try:
                obj = json.loads(data)
            except Exception:
                print(data)
                return
        else:
            obj = data
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        return

    try:
        if isinstance(data, str):
            data = json.loads(data)
    except Exception:
        print(data)
        return

    print(color_json(data))

class Spinner:
    def __init__(self, message="Processant...", raw=False):
        self.msg = message
        self.chars = '|/-\\'
        self.running = False
        self.thread = None
        self.raw = raw

    def start(self):
        if self.raw:
            return
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
        if self.raw:
            return
        self.running = False
        if self.thread:
            self.thread.join()

def get_session(cookie_file):
    session = requests.Session()
    try:
        session.cookies = MozillaCookieJar(cookie_file)
        if os.path.exists(cookie_file):
            session.cookies.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print_error(f"No s'ha pogut carregar el fitxer de cookies: {e}")
    return session

def should_skip_ssl_verification(args):
    # Ignora errors SSL si --insecure o variable d'entorn IREDAPI_INSECURE=1
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def handle_exception(exc, raw=False, msg="Error inesperat."):
    logging.warning(f"{msg}: {type(exc).__name__} - {exc}")
    if raw:
        print_error(msg, raw=True)
    else:
        print_error(f"{msg} ({type(exc).__name__}: {exc})")

def save_token(token):
    with open(TOKEN_FILE, 'w') as f:
        f.write(token)
    #os.chmod(TOKEN_FILE, 0o600)

def load_token(args):
    #session = get_session(args.cookies)
    # if hasattr(session, 'api_token') and session.api_token:
    #     return session.api_token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    elif args.token:
      return args.token
    return None

def show_token(args):
    """Mostra el token d'autenticació desat, amb o sense format."""
    cookies_file = args.cookies
    raw = getattr(args, 'raw', False)  # evita error si no existeix
    
    # 1. Intenta llegir el token local
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if raw:
            print(json.dumps({'_success': True, '_data': token}))
        else:
            print(f"{AnsiColor.GREEN}🔑 Token actual:{AnsiColor.RESET} {token}")
        return
    
    # 2. Si no hi ha token local, prova de llegir des de la sessió
    if os.path.exists(cookies_file):
        try:
            session_cookies = MozillaCookieJar(cookies_file)
            session_cookies.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            if raw:
                print(json.dumps({'_success': False, '_msg': f"Error llegint cookies: {e}"}))
            else:
                print(f"{AnsiColor.RED}⚠️ Error llegint cookies: {e}{AnsiColor.RESET}")
            return

        try:
            resp = requests.get(f"{args.url}/session-info", cookies=session_cookies, verify=False)
            data = resp.json()
            # print(json.dumps(data, indent=2))
            token = None
            if 'api_token' in data:
                token = data['api_token']
            elif data.get('_data', {}).get('api_token'):
                token = data['_data']['api_token']
            
            if token:
                if raw:
                    print(json.dumps({'_success': True, '_data': token}))
                else:
                    print(f"{AnsiColor.GREEN}🔑 Token de sessió:{AnsiColor.RESET} {token}")
            else:
                if raw:
                    print(json.dumps({'_success': False, '_msg': "Cap token trobat a la sessió."}))
                else:
                    print(f"{AnsiColor.RED}❌ Cap token trobat a la sessió.{AnsiColor.RESET}")
        except Exception as e:
            if raw:
                print(json.dumps({'_success': False, '_msg': f"Error llegint token de sessió: {e}"}))
            else:
                print(f"{AnsiColor.RED}❌ Error llegint token de sessió: {e}{AnsiColor.RESET}")
    
    else:
        if raw:
            print(json.dumps({'_success': False, '_msg': "No s'ha trobat cap token desat. Fes login primer."}))
        else:
            print(f"{AnsiColor.RED}❌ No s'ha trobat cap token desat. Fes login primer.{AnsiColor.RESET}")

def login(args):
    #session = get_session(args.cookies)
    session = get_session(COOKIE_FILE)
    url = f"{args.url}/login"
    data = {'username': args.username, 'password': args.password}
    verify = not should_skip_ssl_verification(args)
  
    spinner = Spinner("Fent login...", raw=args.raw)
    spinner.start()
    try:
        resp = session.post(url, data=data, verify=verify)
    except Exception as e:
        spinner.stop()
        logging.warning(f"Error durant login: {type(e).__name__} - {e}")
        if args.raw:
            print(json.dumps({'_success': False, '_msg': str(e)}))
        else:
            handle_exception(e, raw=False, msg="Error durant l'autenticació")
        return
    finally:
        spinner.stop()

    try:
        json_resp = resp.json()
    except ValueError:
        msg = "Resposta no és JSON vàlida."
        if args.raw:
            print(json.dumps({'_success': False, '_msg': msg}))
        else:
            print_error(msg, raw=False)
        return

    if resp.status_code == 200 and 'token' in json_resp:
        #session.api_token = json_resp['token']  # Guardar token a la sessió
        save_token(json_resp['token']) # Guardar token a fitxer
        session.cookies.save(ignore_discard=True, ignore_expires=True)
        #with open(COOKIE_FILE, 'wb') as f:
        #    pickle.dump(requests.utils.dict_from_cookiejar(session.cookies), f)
                
        if args.raw:
            print(json.dumps({'_success': True , '_data': json_resp}))
        else:
            print_success(f"Login correcte. Token: {json_resp['token'][:10]}...", raw=False)
            jp(json_resp, raw=False)
    else:
        msg = json_resp.get('_msg', 'Desconegut')
        if args.raw:
            print(json.dumps({'_success': False, '_msg': msg}))
        else:
            print_error(f"Error login: {msg}", raw=False)

def call(args):
    #session = get_session(args.cookies)
    
    verify = not should_skip_ssl_verification(args)
  
    token = load_token(args)
    if not token:
        msg = "No hi ha cap token. Cal fer login primer."
        if args.raw:
            print(json.dumps({'_success': False, '_msg': msg}))
        else:
            print_error(msg, raw=False)
        return

    headers = {
        'Authorization': f"Bearer {token}", 
        'Accept': 'application/json'
        }
    headers.setdefault('Content-Type', 'application/json')
    
    data_to_send = None
    if args.data:
        try:
            json_data = json.loads(args.data)
            data_to_send = json.dumps(json_data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        except ValueError:
            data_to_send = args.data.encode('utf-8')
            headers['Content-Type'] = 'text/plain'

    #url = f"{API_BASE}/{args.endpoint.strip('/')}"
    url = f"{args.url.rstrip('/')}{args.endpoint}"
    method = args.method.upper()

    spinner = Spinner("🚀 Cridant a l'API...", raw=args.raw)
    spinner.start()
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, verify=verify)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, verify=verify, data=data_to_send)
        elif method == 'PUT':
            resp = requests.put(url, headers=headers, verify=verify, data=data_to_send)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, verify=verify)
        elif method == 'PATCH':
            resp = requests.patch(url, headers=headers, verify=verify, data=data_to_send)
        else:
            if not args.raw:
                print(f"{AnsiColor.RED}❌ Mètode HTTP no suportat: {method}{AnsiColor.RESET}")
            return
    except Exception as e:
        spinner.stop()
        logging.warning(f"Error durant crida HTTP: {type(e).__name__} - {e}")
        if args.raw:
            print(json.dumps({'_success': False, '_msg': str(e)}))
        else:
            handle_exception(e, raw=False, msg="Error durant la crida HTTP: {type(e).__name__} - {e}")
        return
    finally:
        spinner.stop()

    try:
        content = resp.json()
    except ValueError:
        if args.raw:
            print(json.dumps({'_success': False, '_msg': 'Resposta no JSON'}))
        else:
            print(resp.text)
        return

    if args.raw:
        if method == 'GET':
            print(json.dumps({'_success': True, '_data': content}))
        else:
            print(json.dumps({'_success': True}))
    else:
        jp(content, raw=False)

def logout(args):
    """Esborra fitxers de sessió: cookies i token."""
    success = True
    errors = []

    # Esborra el fitxer de cookies
    try:
        os.remove(args.cookies)
        if not args.raw:
            print(f"{AnsiColor.GREEN}✅ Fitxer de cookies '{args.cookies}' eliminat.{AnsiColor.RESET}")
    except FileNotFoundError:
        if not args.raw:
            print(f"ℹ️ Fitxer de cookies '{args.cookies}' no existeix.")
    except Exception as e:
        success = False
        errors.append(f"Error eliminant cookies: {e}")
        if not args.raw:
            print(f"{AnsiColor.RED}❌ Error eliminant cookies: {e}{AnsiColor.RESET}")

    # Esborra el fitxer de token
    try:
        os.remove(TOKEN_FILE)
        if not args.raw:
            print(f"{AnsiColor.GREEN}✅ Fitxer de token '{TOKEN_FILE}' eliminat.{AnsiColor.RESET}")
    except FileNotFoundError:
        if not args.raw:
            print(f"ℹ️ Fitxer de token '{TOKEN_FILE}' no existeix.")
    except Exception as e:
        success = False
        errors.append(f"Error eliminant token: {e}")
        if not args.raw:
            print(f"{AnsiColor.RED}❌ Error eliminant token: {e}{AnsiColor.RESET}")

    # Sortida en format RAW (JSON)
    if args.raw:
        if success:
            print(json.dumps({'_success': True}))
        else:
            print(json.dumps({'_success': False, '_msg': '; '.join(errors)}))

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
      ),)
    parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors de certificat SSL')
    parser.add_argument('-r', '--raw', action='store_true', help='Sortida RAW sense colors')
    parser.add_argument('-t', '--token', help='Token d\'autenticació personalitzat')
    parser.add_argument('--cookies', default=COOKIE_FILE, help='Fitxer de cookies')
    parser.set_defaults(func=lambda args: parser.print_help())
  
    subparsers = parser.add_subparsers(title='Subcomandes',dest='command')

    login_parser = subparsers.add_parser('login', help='Iniciar sessió i desa cookies')
    #login_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API (ex: https://localhost/iredadmin)')
    login_parser.add_argument('-u', '--username', required=True, help='Nom d\'usuari')
    login_parser.add_argument('-p', '--password', required=True, help='Contrasenya')
    login_parser.add_argument('-c', '--cookies', default=COOKIE_FILE, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=login)

    call_parser = subparsers.add_parser('call', help='Fer una crida a l\'API')
    call_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    call_parser.add_argument('-e', '--endpoint', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
    call_parser.add_argument('-t', '--token', help='Token Bearer (opcional si has fet login abans)')
    call_parser.add_argument('-m','--method', default='GET', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], help='Mètode HTTP per a la crida (GET per defecte)')
    call_parser.add_argument('-d', '--data', help='Dades a enviar en POST/PUT/PATCH (format text o JSON)')
    call_parser.add_argument('-c', '--cookies', default=COOKIE_FILE, help='Fitxer cookies')
    call_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    call_parser.set_defaults(func=call)

    logout_parser = subparsers.add_parser('logout', help='Esborra el fitxer de cookies')
    logout_parser.add_argument('--cookies', '-c', default=COOKIE_FILE, help='Fitxer cookies')
    logout_parser.set_defaults(func=logout)

    token_parser = subparsers.add_parser('token', help='Mostra el token desat')
    token_parser.add_argument('--cookies', '-c', default=COOKIE_FILE, help='Fitxer cookies')
    token_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API (necessari si no hi ha fitxer de token)')
    token_parser.set_defaults(func=show_token)

    args = parser.parse_args()

    # RAW mode via variable d'entorn
    if RAW_MODE:
        args.raw = True

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
