#!/usr/bin/env python3
# iredapi_manager.py
import os
import sys
import json
import argparse
import getpass
import time
import threading
import requests

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import warnings
from urllib3.exceptions import InsecureRequestWarning, NotOpenSSLWarning
# Silenciar warnings d'InsecureRequestWarning (HTTPS sense verificació)
warnings.filterwarnings("ignore", category=InsecureRequestWarning)
# Silenciar el NotOpenSSLWarning
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

from http.cookiejar import MozillaCookieJar

API_BASE = os.getenv('IREDAPI_URL', 'https://localhost/iredadmin/api')
TOKEN_FILE = os.path.expanduser('~/.iredapi_token')
COOKIE_FILE = os.path.expanduser('~/.iredapi_cookies.txt')
# Detectar RAW mode via variable d'entorn
RAW_MODE = os.getenv('IREDAPI_RAW', '0') == '1'


import sys

class AnsiColor:
    RED = '\033[31m'
    GREEN = '\033[32m'
    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    RESET = '\033[0m'

class Logger:
    DEBUG_ENABLED = os.getenv('IREDAPI_DEBUG', '0') == '1'
    @staticmethod
    def print_msg(msg, color='', symbol='', prefix='', raw=False, err=False):
        """
        Imprimeix un missatge amb format opcional de color, símbol i prefix.

        Args:
            msg (str): Missatge a imprimir.
            color (str): Codi ANSI per al color.
            symbol (str): Símbol Unicode per prefixar.
            prefix (str): Text prefix per al missatge.
            raw (bool): Si True, imprimeix sense colors ni símbols.
            err (bool): Si True, imprimeix a stderr.
        """
        if raw:
            output = msg
        else:
            parts = [part for part in [color, symbol, prefix, msg] if part]
            output = ' '.join(parts) + AnsiColor.RESET
        print(output, file=sys.stderr if err else sys.stdout)

    @staticmethod
    def error(msg, raw=False):
        """Missatge d'error en vermell amb creu (stderr)."""
        Logger.print_msg(msg, AnsiColor.RED, '\u274c', raw=raw, err=True)

    @staticmethod
    def success(msg, raw=False):
        """Missatge d'èxit en verd amb check."""
        Logger.print_msg(msg, AnsiColor.GREEN, '\u2705', raw=raw)

    @staticmethod
    def info(msg, raw=False):
        """Missatge informatiu en cian amb ℹ️ i prefix [INFO]."""
        Logger.print_msg(msg, AnsiColor.CYAN, '\u2139\uFE0F', '[INFO]', raw=raw)

    @staticmethod
    def warning(msg, raw=False):
        """Missatge d'advertència en groc amb ⚠️ i prefix [WARNING] (stderr)."""
        Logger.print_msg(msg, AnsiColor.YELLOW, '\u26A0\uFE0F', '[WARNING]', raw=raw, err=True)

    @staticmethod
    def debug(msg, raw=False):
        """Missatge de depuració en groc amb bug 🐛 i prefix [DEBUG]."""
        """Missatge de depuració només si DEBUG_ENABLED és True."""
        if Logger.DEBUG_ENABLED:
            Logger.print_msg(msg, AnsiColor.YELLOW, '\U0001F41B', '[DEBUG]', raw=raw)

def handle_exception(exc, raw=False, msg="Error inesperat:"):
    error = f"{msg} ({type(exc).__name__}: {exc})"
    output = error if raw else f"{AnsiColor.RED}\u274c {error}{AnsiColor.RESET}"
    print(output)

def json_pretty_color(data, indent=0):
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

def json_pretty(data, raw=False):
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

    print(json_pretty_color(data))

class Spinner:
    def __init__(self, message="Carregant...", raw=False):
        self.raw = raw
        self.stop_running = False
        self.thread = None

        max_msg_len = 50  # límit fix
        if len(message) > max_msg_len:
            self.message = message[:max_msg_len - 3] + '...'
        else:
            self.message = message

    def start(self):
        if self.raw:
            return
        self.stop_running = False
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def stop(self):
        if self.raw:
            return
        self.stop_running = True
        if self.thread:
            self.thread.join()
    
    def _spin(self):
        spinner_chars = ['|', '/', '-', '\\']
        idx = 0
        while not self.stop_running:
            sys.stdout.write(f"\r{self.message} {spinner_chars[idx % len(spinner_chars)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
        sys.stdout.write("\r" + " " * (len(self.message) + 2) + "\r")
        sys.stdout.flush()

class SessionManager:
    def __init__(self, token_file=TOKEN_FILE , cookie_file=COOKIE_FILE):
        self.token_file = token_file
        self.cookie_file = cookie_file
    
    def save_cookie(self, resp, domain='localhost'):
        """Guarda cookies de la resposta HTTP a MozillaCookieJar."""
        jar = MozillaCookieJar(self.cookie_file)

        for c in resp.cookies:
            if not c.domain:
                c.domain = domain  # només si no està definit
            jar.set_cookie(c)

        jar.save(ignore_discard=True, ignore_expires=True)
        for c in jar:
            if c.domain:
                Logger.debug(f"Cookie guardada: {c.name}={c.value} (domini: {c.domain})")
            else:
                Logger.debug(f"Cookie guardada: {c.name}={c.value} (sense domini)")
    
    def load_cookie(self):
        """Carrega i retorna un MozillaCookieJar si existeix."""
        if os.path.exists(self.cookie_file):
            jar = MozillaCookieJar(self.cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            return jar
        return None

    def delete_cookie(self):
        """Esborra el fitxer de cookies."""
        if os.path.exists(self.cookie_file):
            os.remove(self.cookie_file)
            
    def save_token(self, token):
        with open(self.token_file, 'w') as f:
            f.write(token)
        os.chmod(self.token_file, 0o600)

    def load_token(self, args):
        if args.token:
            return args.token
        if not os.path.exists(self.token_file):
            return None
        with open(self.token_file, 'r') as f:
            return f.read().strip()

    def delete_token(self):
        if os.path.exists(self.token_file):
            os.remove(self.token_file)

    def token_exists(self):
        return os.path.exists(self.token_file)

def should_skip_ssl_verification(args):
    # Ignora errors SSL si --insecure o variable d'entorn IREDAPI_INSECURE=1
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def print_json(data, raw=False):
    if raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        json_pretty(data, raw=False)

def cmd_show_token(args):
    cookies_file = args.cookies
    raw = getattr(args, 'raw', False)

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if raw:
            print_json({'_success': True, '_data': token})
        else:
            Logger.success(f"Token actual 🔑 : {token}")
        return

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
            token = data.get('api_token') or data.get('_data', {}).get('api_token')

            if token:
                if raw:
                    print(json.dumps({'_success': True, '_data': token}))
                else:
                    print(f"{AnsiColor.GREEN}🔑 Token de sessió:{AnsiColor.RESET} {token}")
            else:
                msg = "Cap token trobat a la sessió."
                if raw:
                    print(json.dumps({'_success': False, '_msg': msg}))
                else:
                    print(f"{AnsiColor.RED}❌ {msg}{AnsiColor.RESET}")
        except Exception as e:
            if raw:
                print(json.dumps({'_success': False, '_msg': f"Error llegint token de sessió: {e}"}))
            else:
                print(f"{AnsiColor.RED}❌ Error llegint token de sessió: {e}{AnsiColor.RESET}")
    else:
        msg = "No s'ha trobat cap token desat. Fes login primer."
        if raw:
            print(json.dumps({'_success': False, '_msg': msg}))
        else:
            print(f"{AnsiColor.RED}❌ {msg}{AnsiColor.RESET}")

def cmd_logout(args, session_mgr):
    """Esborra fitxers de sessió: cookies i token."""
    success = True
    errors = []

    try:
        #os.remove(args.cookies)
        session_mgr.delete_cookie()
        if not args.raw:
            Logger.success(f"Fitxer de cookies '{args.cookies}' eliminat.")
    except FileNotFoundError:
        if not args.raw:
            print(f"ℹ️ Fitxer de cookies '{args.cookies}' no existeix.")
    except Exception as e:
        success = False
        errors.append(f"Error eliminant cookies: {e}")
        if not args.raw:
            Logger.error(f"Error eliminant cookies: {e}")

    try:
        session_mgr.delete_token()
        if not args.raw:
            Logger.success(f"Fitxer de token '{TOKEN_FILE}' eliminat.")
    except Exception as e:
        success = False
        errors.append(f"Error eliminant token: {e}")
        if not args.raw:
            Logger.error(f"Error eliminant token: {e}")

    # Sortida en format RAW (JSON)
    if args.raw:
        if success:
            print(json.dumps({'_success': True}))
        else:
            print(json.dumps({'_success': False, '_msg': '; '.join(errors) if errors else ''}))
    else:
        if success:
            Logger.success(f" 👋 Sessió tancada.")
        else:
            Logger.error(f"Sessió no tancada: {'; '.join(errors)}")

def cmd_login(args, session_mgr):
    try:
        password = args.password or getpass.getpass("Contrasenya: ")
    except Exception:
        Logger.error("No es pot llegir la contrasenya (entorn no interactiu?)")
        return
    url = f"{args.url}/login"
    data = {'username': args.username, 'password': password}
    verify = not should_skip_ssl_verification(args)

    spinner = Spinner("Fent login...", raw=args.raw)
    spinner.start()
    try:
        resp = cmd_call(args, session_mgr, url=url, method='POST', data=data, internal=True)
    except Exception as e:
        spinner.stop()
        if args.raw:
            print(json.dumps({'_success': False, '_msg': str(e)}))
        else:
            handle_exception(e, raw=False, msg="Error durant l'autenticació")
        return
    finally:
        spinner.stop()

    if resp is None:
        # Ja s'ha mostrat error dins cmd_call, només sortim
        return
    
    #print(f"Resposta API: {resp}")
    payload = resp.json()
    if payload.get('_success') and payload.get('api_token'):
        session_mgr.save_token(payload['api_token'])
        msg= "Login correcte. Token guardat."
        
        session_mgr.save_cookie(resp, domain=args.url.split('//')[-1].split('/')[0])  # extreu domini
        
        if args.raw:
            print(json.dumps({'_success': True, '_msg': msg}))
        else:
            Logger.success(msg)
        return
    else:
        msg= f"Error d'autenticació: {resp.get('_msg')}"
        
        if args.raw:
            print(json.dumps({'_success': False, '_msg': msg}))
        else:
            Logger.error(msg)
    
def cmd_call(args, session_mgr, url=None, method=None, data=None, internal=False):
    Logger.debug(f"Estem dins cmd_call(), url={url}, method={method}, internal={internal}")
    verify = not should_skip_ssl_verification(args)
    
    # Si és login, no cal token
    if not internal:
        token = session_mgr.load_token(args)
        if not token:
            msg = "No hi ha cap token. Cal fer login primer."
            if args.raw:
                print(json.dumps({'_success': False, '_msg': msg}))
            else:
                Logger.error(msg)
            return None
    else:
        token = session_mgr.load_token(args)  # Però podríem ometre o passar None

    headers = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    headers['Accept'] = 'application/json'
    headers['Content-Type'] = 'application/json'
    
    data_to_send = None
    if data is None and args.data:
        try:
            json_data = json.loads(args.data)
            data_to_send = json.dumps(json_data).encode('utf-8')
        except ValueError:
            data_to_send = args.data.encode('utf-8')
            headers['Content-Type'] = 'text/plain'
    elif data is not None:
        data_to_send = json.dumps(data).encode('utf-8')

    if url is None:
        url = f"{args.url.rstrip('/')}{args.endpoint.rstrip('/')}"
    if method is None:
        method = args.method.upper()

    if not internal:
        spinner = Spinner("🚀 Cridant a l'API...", raw=args.raw)
        spinner.start()
        jar = session_mgr.load_cookie()
        if not args.raw:
            if jar and len(jar):
                Logger.success("Cookies carregades: 🍪 ")
                # for c in jar:
                #     Logger.debug(f"  {c.name}={c.value} (domini: {c.domain})")
            else:
                Logger.error("No s'han carregat cookies.")
    else:
        spinner = None
        jar = None
    Logger.debug(f"Cridant amb URL: {url} | METHOD: {method}")
    try:
        resp = requests.request(method, url, headers=headers, data=data_to_send, verify=verify, cookies=jar, allow_redirects=False)
        resp.raise_for_status()  # ❗️ Proposa excepció si status >= 400
    except requests.exceptions.RequestException as e:
        if spinner:
            spinner.stop()
        if args.raw:
            print_json({'_success': False, '_msg': str(e)}, raw=True)
        else:
            handle_exception(e, raw=False, msg="Error durant la crida HTTP:")
        return None
    finally:
        if spinner:
            spinner.stop()
    Logger.debug(f"Tipus de resp: {type(resp)}")
    Logger.debug(f"Contingut de resp: {resp}")
    Logger.debug(f"Contingut de resp: {resp}")
    try:
        content = resp.json()
    except ValueError:
        Logger.warning("Resposta no és JSON vàlid.")
        return None
    
    
    if internal:
        return resp # retorna tot l'objecte Response

    print_json(content, raw=args.raw)

def cmd_session(args, session_mgr):
    # Carregar el token desat
    token = session_mgr.load_token(args)
    if not token:
        # Si no hi ha token, mostrar un error
        Logger.error("No hi ha token disponible.", raw=args.raw)
        return
    args.token = token  # Assignar el token carregat a args per a la crida    
    # Fer la crida a l'API per obtenir informació de la sessió
    cmd_call(
        args, 
        session_mgr, 
        url=f"{args.url}/session-info", 
        method='GET', 
        data=None, 
        internal=False
    )

def main():
    parser = argparse.ArgumentParser(
        prog='iredapi',
        description=(
            '🔐 CLI per a l\'API iRedAdmin\n\n'
            'Pots usar la variable d\'entorn IREDAPI_INSECURE=1 per ignorar errors SSL.\n'
            'Opció -k / --insecure equivalent a curl -k.\n'
            'La URL base per defecte és https://localhost/iredadmin però la pots canviar amb:\n'
            '  --url o la variable d\'entorn IREDAPI_URL\n'
            'però si indiques --raw, el JSON es mostra en format normal (sense codi de color).'
        ),
        epilog=(
            ' ℹ️ Per a més ajuda, usa --help o ajuda subcomanda.\n'
            ' ℹ️ Per a més informació sobre les API, visita: https://iredmail.org/api.html\n'
        ),)
    parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors de certificat SSL')
    parser.add_argument('-r', '--raw', action='store_true', help='Sortida RAW sense colors')
    parser.add_argument('-t', '--token', help='Token d\'autenticació personalitzat')
    parser.add_argument('--cookies', default=COOKIE_FILE, help='Fitxer de cookies')
    parser.set_defaults(func=lambda args: parser.print_help())
  
    subparsers = parser.add_subparsers(title='Subcomandes',dest='command')

    login_parser = subparsers.add_parser('login', help='Iniciar sessió i desa cookies')
    login_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API (ex: https://localhost/iredadmin)')
    login_parser.add_argument('-u', '--username', required=True, help='Nom d\'usuari')
    login_parser.add_argument('-p', '--password', help='Contrasenya')
    login_parser.add_argument('-c', '--cookies', default=COOKIE_FILE, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=cmd_login)

    call_parser = subparsers.add_parser('call', help='Fer una crida a l\'API')
    call_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    call_parser.add_argument('-e', '--endpoint', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
    call_parser.add_argument('-t', '--token', help='Token Bearer (opcional si has fet login abans)')
    call_parser.add_argument('-m','--method', default='GET', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], help='Mètode HTTP per a la crida (GET per defecte)')
    call_parser.add_argument('-d', '--data', help='Dades a enviar en POST/PUT/PATCH (format text o JSON)')
    call_parser.add_argument('-c', '--cookies', default=COOKIE_FILE, help='Fitxer cookies')
    call_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    call_parser.set_defaults(func=cmd_call)

    logout_parser = subparsers.add_parser('logout', help='Esborra el fitxer de cookies')
    logout_parser.add_argument('--cookies', '-c', default=COOKIE_FILE, help='Fitxer cookies')
    logout_parser.set_defaults(func=cmd_logout)

    token_parser = subparsers.add_parser('token', help='Mostra el token desat')
    token_parser.add_argument('--cookies', '-c', default=COOKIE_FILE, help='Fitxer cookies')
    token_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API (necessari si no hi ha fitxer de token)')
    token_parser.set_defaults(func=cmd_show_token)
    
    session_parser = subparsers.add_parser('session', help='Mostrar informació de sessió actual')
    session_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors de certificat SSL')
    session_parser.add_argument('-d', '--data', help='Dades a enviar en JSON o text (opcional)', default=None)
    session_parser.set_defaults(func=cmd_session)

    args = parser.parse_args()
    if not args.command:
            parser.print_help()
            return
    
    # RAW mode via variable d'entorn
    if RAW_MODE:
        args.raw = True
    
    if Logger.DEBUG_ENABLED:
        Logger.info("DEBUG mode actiu 🐛")

    session_mgr = SessionManager()
    if args.command in ('login', 'call', 'logout', 'session'):
        args.func(args, session_mgr)
    else:
        args.func(args)

if __name__ == '__main__':
    main()
