#!/usr/bin/env python3
# iredapi_manager.py
import os
import sys
import json
import argparse
import textwrap
import getpass
import time
import threading
import requests
from typing import Optional
import shutil
from wcwidth import wcswidth

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# import warnings
# from urllib3.exceptions import InsecureRequestWarning, NotOpenSSLWarning
# # Silenciar warnings d'InsecureRequestWarning (HTTPS sense verificació)
# warnings.filterwarnings("ignore", category=InsecureRequestWarning)
# # Silenciar el NotOpenSSLWarning
# warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

from http.cookiejar import MozillaCookieJar
from collections import OrderedDict

API_BASE = os.getenv('IREDAPI_URL', 'https://localhost/iredadmin/api')
TOKEN_FILE = os.path.expanduser('~/.iredapi_token')
COOKIE_FILE = os.path.expanduser('~/.iredapi_cookies.txt')
# Detectar RAW mode via variable d'entorn
RAW_MODE = os.getenv('IREDAPI_RAW', '0') == '1'
DEBUG_ENABLED = os.getenv('IREDAPI_DEBUG', '0') == '1'
MASK_SENSITIVE_DATA = os.getenv('IREDAPI_MASK_SENSITIVE', '1') != '0'  # per defecte, amaga dades sensibles
# Nota: != '0' perquè quan és '0', no volem fer masking si també s'afegeix --show-secrets.
SENSITIVE_KEYS = {'password', 'api_token', 'session_id', 'token'}
SPINNER_START_ICON = "🚗" # "🚀" "✈️" "🚗" "🏎️" "📡"
SPINNER_END_ICON = "🏁" # "🛬" "🎯"

def log_debug(msg, depth=1):
    import inspect
    frame = inspect.stack()[depth]
    Logger.debug(f"[{frame.function}] {msg}")

class AnsiColor:
    RED = '\033[38;2;220;100;100m'
    GREEN = '\033[32m'
    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    RESET = '\033[0m'

class Logger:
    @staticmethod
    def print_msg(msg, color='', symbol='', prefix='', raw=False, err=False, end='\n', flush=True):
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
            output = JsonFormatter(raw=raw).show((False, {'_msg': msg}))
        else:
            parts = [part for part in [color, symbol, prefix, msg] if part]
            output = ' '.join(parts) + AnsiColor.RESET
        print(output, file=sys.stderr if err else sys.stdout, end=end, flush=flush)

    @staticmethod
    def error(msg, raw=False, end='\n', flush=True):
        """Missatge d'error en vermell amb creu (stderr)."""
        Logger.print_msg(msg, AnsiColor.RED, '\u274c', raw=raw, err=True, end=end, flush=flush)

    @staticmethod
    def success(msg, raw=False, end='\n', flush=True):
        """Missatge d'èxit en verd amb check."""
        Logger.print_msg(msg, AnsiColor.GREEN, '\u2705', raw=raw, end=end, flush=flush)

    @staticmethod
    def info(msg, raw=False, end='\n', flush=True):
        """Missatge informatiu en cian amb ℹ️ i prefix [INFO]."""
        Logger.print_msg(msg, AnsiColor.CYAN, '\u2139\uFE0F', ' [INFO]', raw=raw, end=end, flush=flush)

    @staticmethod
    def warning(msg, raw=False, end='\n', flush=True):
        """Missatge d'advertència en groc amb ⚠️ i prefix [WARNING] (stderr)."""
        Logger.print_msg(msg, AnsiColor.YELLOW, '\u26A0\uFE0F', '[WARNING]', raw=raw, err=True, end=end, flush=flush)

    @staticmethod
    def debug(msg, raw=False, end='\n', flush=True):
        """Missatge de depuració en groc amb bug 🐛 i prefix [DEBUG]."""
        """Missatge de depuració només si DEBUG_ENABLED és True."""
        if DEBUG_ENABLED:
            Logger.print_msg(msg, AnsiColor.YELLOW, '\U0001F41B', '[DEBUG]', raw=raw, end=end, flush=flush)

class JsonFormatter:
    def __init__(self, raw=False):
        self.raw = raw

    def colorize(self, obj, indent=0):
        '''
        colorize() no fa servir json.dumps és perquè està construint manualment una versió acolorida i indentada del JSON, clau per clau, valor per valor.
        A diferència de json.dumps, que només serialitza dades, afegeix colors ANSI segons el tipus de dada (str, bool, null, etc.), mascara valors sensibles ("password": "***"), i aplica la indentació pròpia.
        ho fa tot amb control total sobre cada element. 
        '''
        INDENT_STR = "  "
        def _colorize(obj, level):
            pad = INDENT_STR * level
            pad_next = INDENT_STR * (level + 1)

            if isinstance(obj, dict):
                if not obj:
                    return '{}'
                items = []
                for k, v in obj.items():
                    colored_key = f'{AnsiColor.YELLOW}"{k}"{AnsiColor.RESET}'
                    if MASK_SENSITIVE_DATA and k in SENSITIVE_KEYS:
                        colored_val = f'{AnsiColor.RED}"***"{AnsiColor.RESET}'
                    else:
                        colored_val = _colorize(v, level + 1)
                    items.append(f'{pad_next}{colored_key}: {colored_val}')
                return '{\n' + ',\n'.join(items) + f'\n{pad}' + '}'
            elif isinstance(obj, list):
                if not obj:
                    return '[]'
                items = [_colorize(i, level + 1) for i in obj]
                return '[\n' + ',\n'.join(f'{pad_next}{item}' for item in items) + f'\n{pad}]'
            elif isinstance(obj, str):
                return f'{AnsiColor.GREEN}"{obj}"{AnsiColor.RESET}'
            elif isinstance(obj, bool):
                return f'{AnsiColor.CYAN}{obj}{AnsiColor.RESET}'
            elif obj is None:
                return f'{AnsiColor.RED}null{AnsiColor.RESET}'
            else:
                return f'{AnsiColor.CYAN}{obj}{AnsiColor.RESET}'

        return _colorize(obj, indent)
    
    def format(self, result):
        """
        Processa tuples o dicts per mostrar-los com JSON formatat,
        amb o sense colors, i sense claus buides.
        """
        try:
            if isinstance(result, tuple):
                success, *rest = result
                d = OrderedDict({'_success': success})
                if rest:
                    extra = rest[0]
                    if isinstance(extra, dict):
                        if '_msg' in extra and extra['_msg'] is not None:
                            d['_msg'] = extra['_msg']
                        if '_data' in extra and extra['_data'] is not None:
                            d['_data'] = extra['_data']
                    elif isinstance(extra, str):
                        d['_msg'] = extra
            elif isinstance(result, dict):
                # Construïm un diccionari ordenat amb només les claus rellevants i en l'ordre desitjat
                d = OrderedDict()
                success = result.get('_success', True)
                d['_success'] = success
                if '_msg' in result and result['_msg'] is not None:
                    d['_msg'] = result['_msg']
                if '_data' in result and result['_data'] is not None:
                    d['_data'] = result['_data']
            else:
                d = OrderedDict({'_success': False, '_msg': 'Format de dades no suportat'})
                log_debug(f"JsonFormatter.format: format no suportat: {type(result)} -> {repr(result)}")
        except Exception as e:
            log_debug(f"❌ Error processant dades: {type(e)} -> {e}")
            d = OrderedDict({'_success': False, '_msg': f'Error processant dades: {str(e)}'})

        return d
    
    def show(self, result):
        data = self.format(result)
        if self.raw:
            print(json.dumps(data, indent=None, separators=(",", ":"), ensure_ascii=False))
        else:
            print(self.colorize(data))

class Spinner:
    def __init__(self, text_start="Cridant a l'API...", text_end="Fet!", delay=0.1, raw=False):
        """
        :param text_start: Text que es mostra quan comença el spinner.
        :param text_end: Text que es mostra quan s'atura el spinner.
        :param delay: Temps entre cada pas de l'animació (mínim 0.05s, màxim 1.0s).
        :param raw: Si és True, només mostra una línia neta amb animació i resultat final.
        """
        self.raw = raw
        self.delay = max(0.05, min(delay, 1.0))

        # Icones i textos
        self.text_start = f"{SPINNER_START_ICON} {text_start}"
        self.text_end = f"{SPINNER_END_ICON} {text_end}"

        # Caràcters d'animació
        self.frames = ["|", "/", "-", "\\"]
        self.frame_index = 0

        # Altres paràmetres d'estat
        self._stop_event = threading.Event()
        self._thread = None
        self.columns = shutil.get_terminal_size().columns

    def _full_line(self, text, symbol):
        """Construeix una línia completa amb text + símbol, padding fins omplir terminal."""
        full_text = f"{text} {symbol}"
        width = wcswidth(full_text)
        padding = max(0, self.columns - width)
        return f"{full_text}{' ' * padding}"

    def _spinner_task(self):
        while not self._stop_event.is_set():
            symbol = self.frames[self.frame_index]
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            line = self._full_line(self.text_start, symbol)
            sys.stdout.write(f"\r\033[96m{line}\033[0m")  # Cyan + Reset
            sys.stdout.flush()
            time.sleep(self.delay)

    def start(self):
        self._stop_event.clear()
        if self.raw:
            # Mostra línia inicial però no anima
            symbol = self.frames[self.frame_index]
            line = self._full_line(self.text_start, symbol)
            sys.stdout.write(f"\r\033[96m{line}\033[0m")
            sys.stdout.flush()
        else:
            self._thread = threading.Thread(target=self._spinner_task)
            self._thread.start()

    def stop(self):
        self._stop_event.set()

        if self.raw:
            # Sobreescriu línia amb el missatge final
            line = self._full_line(self.text_end, "✅")
            sys.stdout.write(f"\r{line}\n")
            sys.stdout.flush()
        else:
            if self._thread:
                self._thread.join()
            # Esborra línia anterior
            sys.stdout.write("\r" + " " * self.columns + "\r")
            sys.stdout.flush()
            self._print_done()

    def _print_done(self):
        """Mostra el missatge final amb ✅, alineat completament."""
        line = self._full_line(self.text_end, "✅")
        sys.stdout.write(f"\033[96m{line}\033[0m\n")
        sys.stdout.flush()

class SessionManager:
    """
    Gestiona la sessió de l'usuari: token, cookies, headers i credencials.
    Permet guardar i carregar tokens i cookies per mantenir autenticació persistent.
    """
    def __init__(self, token_file=TOKEN_FILE , cookie_file=COOKIE_FILE):
        self.token_file = token_file
        self.cookie_file = cookie_file
        
    def _log_cookie_jar(self, jar):
        if jar and len(jar):
            log_debug("🍪 Cookies carregades o guardades", 2)
            total = len(jar)
            for i, c in enumerate(jar):
                is_last = (i == total - 1)
                prefix = "└─ " if is_last else "├─ "
                domain = f"(domini: {c.domain})" if c.domain else "(sense domini)"
                log_debug(f"{prefix}{c.name} = {c.value} {domain}", 2)
        else:
            Logger.warning("Cap cookie disponible al jar.")

    def _log_token(self, token: Optional[str]):
        if token:
            log_debug("🔑 Token carregat de la sessió actual", 2)
            display_token = token if not MASK_SENSITIVE_DATA else f"{token[:6]}...{token[-4:]}"
            log_debug(f"└─ Bearer {display_token}", 2)
        else:
            Logger.warning("⚠️ No s'ha trobat cap token d'autenticació.")

    def _log_credentials(self, args):
        log_debug(f"👤 Usuari: {args.username}, 🔑 Contrasenya: {'*' * len(args.password or '')}", 2)

    def save_cookie(self, resp, domain='localhost'):
        if not resp.cookies:
            Logger.warning("Cap cookie a desar des de la resposta.")
            return
        
        jar = MozillaCookieJar(self.cookie_file)

        for c in resp.cookies:
            c.domain = c.domain or domain  # només si no està definit
            jar.set_cookie(c)
        
        try:
            jar.save(ignore_discard=True, ignore_expires=True)
            self._log_cookie_jar(jar)
        except Exception as e:
            Logger.error(f"Error guardant cookies: {e}")

    def load_cookie(self):
        if not os.path.exists(self.cookie_file):
            log_debug("Fitxer de cookies inexistent.")
            return None
        
        jar = MozillaCookieJar(self.cookie_file)
        
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            log_debug(f"No s'han pogut carregar les cookies: {e}")
            return None
        
        if len(jar) == 0:
            log_debug("Fitxer de cookies carregat, però està buit.")
            return None

        self._log_cookie_jar(jar)

        return jar

    def delete_cookie(self):
        try:
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
                log_debug(f"🗑️  Fitxer de cookies '{self.cookie_file}' eliminat.")
            else:
                log_debug(f"📄❓ Fitxer de cookies '{self.cookie_file}' no existeix.")
            return True, None
        except Exception as e:
            return False, f"Error eliminant cookies: {e}"
    
    def cookie_exists(self) -> bool:
        # 🍪 Comprovem si hi ha cookies
        if os.path.exists(self.cookie_file):
            try:
                jar = self.load_cookie()
                return jar is not None and len(jar) > 0
            except Exception as e:
                log_debug(f"❌ No s'han pogut carregar les cookies: {e}", 2)
                return False
        return False
    
    def save_token(self, token):
        try:
            with open(self.token_file, 'w') as f:
                f.write(token)
            os.chmod(self.token_file, 0o600)
            self._log_token(token)
        except Exception as e:
            Logger.error(f"No s'ha pogut guardar el token: {e}")

    def load_token(self):
        """📥 Carrega el token des del fitxer, si existeix i és vàlid."""
        try:
            if not os.path.exists(self.token_file):
                return None
            with open(self.token_file, 'r') as f:
                token = f.read().strip()
                if token and len(token) > 10:
                    return token
                else:
                    log_debug("⚠️ Token buit o massa curt.")
        except Exception as e:
            log_debug(f"❌ Error llegint el token: {e}")
        return None

    def delete_token(self):
        try:
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
                log_debug(f"🗑️  Fitxer de token '{self.token_file}' eliminat.")
            else:
                log_debug(f"📄❓ Fitxer de token '{self.token_file}' no existeix.")
            return True, None
        except Exception as e:
            return False, f"Error eliminant token: {e}"

    def token_exists(self):
        """🧪 Retorna True si hi ha un token vàlid i registrable."""
        token = self.load_token()
        if token:
            self._log_token(token)
            return True
        return False
        
    def ensure_credentials(self, args):
        # ❌ Si no som en entorn interactiu i falten credencials, no podem continuar
        if not sys.stdin.isatty(): 
            if not getattr(args, "username", None) or not getattr(args, "password", None):
                Logger.error("Entorn no interactiu: cal passar usuari i contrasenya via arguments.", raw=args.raw)
                return False
        
        if not getattr(args, "username", None):
            try:
                args.username = input("Usuari 👤 : ")
            except Exception:
                Logger.error("No es pot llegir l'usuari (entorn no interactiu?)", raw=args.raw)
                return False
        
        if not getattr(args, "password", None):
            try:
                args.password = getpass.getpass("Contrasenya 🔑 : ")
            except Exception:
                Logger.error("No es pot llegir la contrasenya (entorn no interactiu?)", raw=args.raw)
                return False

        self._log_credentials(args)
        return True

    def get_auth_headers(self, args, include_content_type=True, requires_token=True):
        headers = {"Accept": "application/json"}

        if requires_token and self.token_exists():
            token = self.load_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                self._log_token(token)
            else:
                Logger.warning("⚠️ Token invàlid o buit tot i existir el fitxer.")
        elif requires_token:
            Logger.warning("⚠️ No s'ha trobat cap token vàlid.")
        
        if include_content_type:
            headers["Content-Type"] = "application/json"

        return headers

    def is_session_expired(self, resp) -> bool:
        """
        Detecta si la sessió ha expirat basant-se en:
        - Redireccions (ex: 302/303) cap a pàgines de login
        - Codis 401/403 quan cal autenticació
        - Contingut HTML o JSON que suggereix expiració de sessió

        :param resp: L'objecte requests.Response
        :param args: Arguments CLI, opcional per més context (raw, debug...)
        :return: True si sembla que la sessió ha expirat
        """
        # if not resp:
        #     log_debug("❗ Resposta buida: no es pot comprovar si la sessió ha expirat.", 2)
        #     return True
        
        # 🔁 Redirecció a pàgina de login
        if resp.status_code in (301, 302, 303):
            location = resp.headers.get("Location", "")
            if location and ("/login" in location or "auth" in location):
                log_debug(f"🔁 Redirecció a login detectada: {location}", 2)
                return True
        
        # 🔒 Resposta que indica falta d'autenticació
        if resp.status_code in (401, 403):
            log_debug(f"🔒 Resposta amb status {resp.status_code} → probablement sessió expirada.", 2)
            return True
        
        # 🔍 Contingut HTML que suggereix login requerit
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            if "login" in resp.text.lower() and "password" in resp.text.lower():
                log_debug("🔐 HTML suggereix pantalla de login.", 2)
                return True
        
        # 📦 JSON que diu que cal tornar a iniciar sessió
        if "application/json" in content_type:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    message = str(data.get("message", "")).lower()
                    if "expired" in message or "unauthorized" in message:
                        log_debug(f"📭 Missatge JSON d'error: {message}", 2)
                        return True
            except Exception as e:
                log_debug(f"❌ No s'ha pogut parsejar JSON: {type(e).__name__}: {e}", 2)

        # 🔎 Si tot ha fallat, considerem que la sessió és vàlida
        log_debug(f"🌐 Resposta: {resp.status_code} {resp.reason}", 2)
        return False

    def is_session_valid(self) -> bool:
        return self.cookie_exists() or self.token_exists()

    def handle_session_expired(self, args, method, url, headers, data_to_send, verify):
        log_debug("🕒 Sessió caducada: esborrem token i cookies. Cal tornar a fer login.")

        success, errors = self.clear_session()
        if not success:
            Logger.error("No s'ha pogut esborrar la sessió anterior.", raw=args.raw)
            for err in errors:
                log_debug(f"  - {err}")
            return None

        if not self.ensure_credentials(args) or not cmd_login(args, self):
            log_debug("No s'han pogut garantir les credencials per tornar a fer login.")
            return None
        Logger.info("Sessió iniciada correctament. Reintentant la crida 🔁...")

        # 🔁 Torna a carregar headers i cookies després del login
        headers = self.get_auth_headers(args, include_content_type=True, requires_token=True)
        cookies = self.load_cookie()

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                data=data_to_send,
                verify=verify,
                cookies=cookies,
                allow_redirects=False
            )
            return response
        except requests.exceptions.RequestException as e:
            Logger.error(f"[handle_session_expired] No s'ha pogut repetir la crida: {e}", raw=args.raw)
            return None

    def clear_session(self):

        success = True
        errors = []

        ok_token, err_token = self.delete_token()
        if not ok_token:
            success = False
            errors.append(err_token)

        ok_cookie, err_cookie = self.delete_cookie()
        if not ok_cookie:
            success = False
            errors.append(err_cookie)

        if success:
            log_debug("🧼 Sessió esborrada correctament. Cal tornar a iniciar sessió.")
        else:
            log_debug(f"❌ Sessió no esborrada completament: {errors}")

        return success, errors 


def should_skip_ssl_verification(args):
    # Ignora errors SSL si --insecure o variable d'entorn IREDAPI_INSECURE=1
    return args.insecure or os.getenv('IREDAPI_INSECURE') == '1'

def cmd_show_token(args):
    cookies_file = args.cookies
    raw = getattr(args, 'raw', False)

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if raw:
            JsonFormatter(raw=raw).show((True, {'_data': token}))
        else:
            Logger.success(f"Token actual 🔒 : {token}")
        return

    if os.path.exists(cookies_file):
        try:
            session_cookies = MozillaCookieJar(cookies_file)
            session_cookies.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            Logger.error(f"Error llegint cookies: {e}", raw=args.raw)
            return

        try:
            resp = requests.get(f"{args.url}/session-info", cookies=session_cookies, verify=False)
            data = resp.json()
            token = data.get('api_token') or data.get('_data', {}).get('api_token')

            if token:
                Logger.success(f"Token de sessió 🔑: {token}", raw=args.raw)
            else:
                Logger.error(f"Cap token trobat a la sessió.", raw=args.raw)
        except Exception as e:
            Logger.error(f"Error llegint token de sessió: {e}", raw=args.raw)
    else:
        Logger.error(f"No s'ha trobat cap token desat. Fes login primer.", raw=args.raw)

def cmd_logout(args, session_mgr):
    success, errors = session_mgr.clear_session()

    if success:
        Logger.success("Sessió tancada 👋.", raw=args.raw)
    else:
        Logger.error("No s'ha pogut tancar la sessió completament.", raw=args.raw)
        for err in errors:
            log_debug(err)

def cmd_login(args, session_mgr):
    if not session_mgr.ensure_credentials(args):
        return False
    
    url = f"{args.url}/login"
    payload = {'username': args.username, 'password': args.password}

    spinner = Spinner("Cridant a l'API...", "Fet!", raw=args.raw)
    spinner.start()
    try:
        resp = cmd_call(args, session_mgr, url=url, method='POST', data=payload, internal=True)
    except Exception as e:
        spinner.stop()
        if args.raw:
            JsonFormatter(raw=args.raw).show((False, {'_msg': str(e)}))
        else:
            Logger.error("Error durant l'autenticació.", raw=args.raw)
            log_debug(f"❌ Excepció: {type(e).__name__} -> {e}")
        return False  # ❌ Fallada durant la petició
    finally:
        spinner.stop()
        log_debug(f"🌐 Resposta: {resp}")

    if resp is None:
        # Ja s'ha mostrat error dins cmd_call, només sortim
        return False

    payload = resp.json()
    #if payload.get('_success') and payload.get('_data', {}).get('api_token'):
    if payload.get('_success') and '_data' in payload: 
        session_mgr.save_cookie(resp, domain=args.url.split('//')[-1].split('/')[0])  # extreu domini
        if  'api_token' in payload['_data']:
            api_token = payload['_data']['api_token']
            session_mgr.save_token(api_token)
        
        if args.raw:
            JsonFormatter(raw=args.raw).show((True, {'_msg': payload['_msg'], '_data': payload['_data']}))
        else:
            Logger.success("Login correcte. Sessió i Token guardats.")
        return True  # ✅ Login correcte
    else:
        msg= f"Error d'autenticació: {payload.get('_msg', 'Error desconegut')}"
        if args.raw:
            JsonFormatter(raw=args.raw).show((False, {'_msg': msg}))
        else:
            Logger.error(msg)
        return False  # ❌ Error d'autenticació
    
def cmd_call(args, session_mgr, url=None, method=None, data=None, internal=False):
    """
        Fa una crida HTTP autenticada a l'API i gestiona errors com sessió expirada o credencials no vàlides.
        
        :param args: Arguments d'entrada amb opcionalment token, username, password, raw, etc.
        :param session_mgr: Instància de SessionManager
        :param url: URL completa o parcial (es resoldrà si cal)
        :param method: Mètode HTTP ("GET", "POST", etc.)
        :param data: Cos de la petició (dict o string)
        :param internal: Si True, no mostra cap sortida de log d'usuari (només errors tècnics)
        :return: La resposta HTTP (`requests.Response`) o None si falla
    """

    verify = not should_skip_ssl_verification(args)
    
    # Resol URL i mètode si no vénen específicats
    url = url or f"{args.url.rstrip('/')}{args.endpoint.rstrip('/')}"
    method = (method or args.method).upper()
    
    # ✨ Si no és internal i no tenim sessió activa, forcem login
    if not internal and not session_mgr.is_session_valid():
        Logger.info(f"[cmd_call] No hi ha sessió activa. S'inicia login interactiu...", raw=args.raw)
        if not session_mgr.ensure_credentials(args) or not cmd_login(args, session_mgr):
            Logger.error(f"[cmd_call] No s'ha pogut iniciar sessió.", raw=args.raw)
            return None
    
    # 🛂 Construïm capçaleres d'autenticació
    #    → Si és sessió amb token: s'inclou "Authorization: Bearer ..."
    #    → Si només fem servir cookies: no s'inclou token si internal=True
    headers = session_mgr.get_auth_headers(args, include_content_type=True, requires_token=not internal)
    log_debug(f"🌐 Iniciant crida url={url}, method={method}, headers={headers}, internal={internal}...")

    # 📦 Prepara el cos de la petició
    payload = None
    if data is None and args.data:
        try:
            json_data = json.loads(args.data)
            payload = json.dumps(json_data).encode('utf-8')
        except ValueError:
            payload = args.data.encode('utf-8')
            headers['Content-Type'] = 'text/plain'
    elif data is not None:
        payload = json.dumps(data).encode('utf-8')

    # ⏳ Spinner si no és crida interna
    spinner = Spinner("Cridant a l'API...", "Fet!", raw=args.raw) if not internal else None
    if spinner:
        spinner.start()

    max_retries = 2
    resp = None
    
    try:
        for attempt in range(max_retries):
            try:
                log_debug(f"🔁 Intent {attempt + 1}/{max_retries}")
                # 🌐 Crida HTTP amb autenticació:
                #    - Si s'utilitzen cookies, s'inclouen automàticament via `session_mgr.load_cookie()`
                resp = requests.request(
                    method, 
                    url, 
                    headers=headers, 
                    data=payload, 
                    verify=verify, 
                    cookies=session_mgr.load_cookie() if not internal else None, 
                    allow_redirects=True
                )
                
                # 🕒 Si la sessió ha caducat (ex: redirecció 303 → login page), intenta renovar-la
                if session_mgr.is_session_expired(resp):
                    spinner.stop() if spinner else None
                    Logger.warning("[cmd_call] Sessió caducada 🕒. Reintentant amb nou login...")
                    
                    # 🔁 Intenta reiniciar la sessió i repetir la crida
                    resp = session_mgr.handle_session_expired(args, method, url, headers, payload, verify)
                    if not resp:
                        Logger.error("[cmd_call] Error al reintentar després de renovar la sessió.", raw=args.raw)
                        return None
                    
                # ❗️ Llança excepció si el codi de resposta és 4xx o 5xx
                resp.raise_for_status()
                break # Èxit → sortim del bucle
            except requests.exceptions.RequestException as e:
                log_debug(f"❌ Error en l'intent {attempt + 1}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    log_debug(f" 🌐 Resposta: {e.response.text.strip()}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Espera abans de reintentar
                    continue
                else:
                    raise  # el tornem a llençar i ho agafem fora
    except requests.exceptions.RequestException as e:
        Logger.error(f"[cmd_call] ❌ Error durant la crida HTTP ({type(e).__name__}: {e})", raw=args.raw)
        return None
    finally:
        if spinner:
            time.sleep(3)  # 👈 força un delay per mostrar el spinner
            spinner.stop()
        log_debug(f"🌐 Resposta: {resp.status_code} {resp.reason}" if resp else "🌐 No s'ha rebut cap resposta HTTP")

    # 📄 Intenta interpretar resposta com JSON
    try:
        content = resp.json()
    except ValueError:
        Logger.warning("[cmd_call] Resposta no és JSON vàlid.")
        return None
    
    # 📤 Retorna resultat si és internal. Si no, el mostra formatat
    return resp if internal else JsonFormatter(raw=args.raw).show(content)

def cmd_session(args, session_mgr):
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
        description=textwrap.dedent('''\
            🔐 CLI per a l\'API iRedAdmin
            
            Pots usar la variable d\'entorn IREDAPI_INSECURE=1 per ignorar errors SSL o bé l\'opció -k/ --insecure.
            La URL base per defecte és https://localhost/iredadmin però la pots canviar amb --url o una variable d\'entorn, IREDAPI_URL.
            Si indiques -r / --raw, el JSON es mostra en cru (sense color ni tabulació).
        '''),
        epilog=textwrap.dedent('''\
            Per a més ajuda, usa --help o ajuda subcomanda.
            Per a més informació sobre les API, visita: https://iredmail.org/api.html
        '''),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors de certificat SSL')
    parser.add_argument('-r', '--raw', action='store_true', help='Sortida RAW sense colors')
    parser.add_argument('--cookies', default=COOKIE_FILE, help='Fitxer de cookies')
    parser.add_argument('--show-secrets', action='store_true', help='Mostra valors sensibles com API token, contrasenyes, etc.')
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers(title='Subcomandes',dest='command')

    login_parser = subparsers.add_parser('login', help='Iniciar sessió i desa cookies')
    login_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API (ex: https://localhost/iredadmin)')
    login_parser.add_argument('-u', '--username', help='Nom d\'usuari')
    login_parser.add_argument('-p', '--password', help='Contrasenya')
    login_parser.add_argument('-c', '--cookies', default=COOKIE_FILE, help='Fitxer cookies')
    login_parser.add_argument('-k', '--insecure', action='store_true', help='Ignora errors SSL (com curl -k)')
    login_parser.set_defaults(func=cmd_login)

    call_parser = subparsers.add_parser('call', help='Fer una crida a l\'API')
    call_parser.add_argument('--url', default=API_BASE, help='URL base de l\'API')
    call_parser.add_argument('-e', '--endpoint', required=True, help='Endpoint API (ex: /api/spampolicy/global)')
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
    
    global MASK_SENSITIVE_DATA
    if args.show_secrets:
        MASK_SENSITIVE_DATA = False
    
    if DEBUG_ENABLED:
        Logger.info("🐛 [DEBUG] mode actiu")

    session_mgr = SessionManager()
    if args.command in ('login', 'call', 'logout', 'session'):
        args.func(args, session_mgr)
    else:
        args.func(args)

if __name__ == '__main__':
    main()
