# iRedAPI CLI `iredapi_manager.py`

## 1. Descripció general

`iredapi_manager.py` és una eina de línia de comandes (CLI) per interactuar amb l'API REST d’iRedAdmin. Facilita operacions com login, consultes d’usuaris i administració remota de comptes mitjançant crides HTTP. Està pensada per a administradors de sistemes que treballin amb iRedMail.

- Implementa una CLI senzilla per interactuar amb l’API d’iRedAdmin:
  - Login i desar token + cookies.
  - Fer crides HTTP (GET, POST, PUT, DELETE, PATCH).
  - Mostrar el token.
  - Logout (esborrar cookies i token).
- Mostra JSON amb colors ANSI per facilitar la lectura.
- Utilitza un spinner ASCII per feedback visual a la consola.
- Permet ignorar errors SSL (com `curl -k`).
- Usa fitxers per emmagatzemar cookies (`~/.iredapi_cookies.txt`) i token (`~/.iredapi_token`).
- Les URLs, fitxers de cookies i paràmetres són configurables via arguments i variables d’entorn.

## 1. 🔧 Funcionalitats

- Iniciar sessió (`login`) amb nom d’usuari i contrasenya.
- Desa automàticament el token i les cookies.
- Crides a l’API (`call`) amb suport per GET, POST, PUT, DELETE i PATCH.
- Mostrar el token actual (`token`).
- Mostrar la sessió actual (`session`).
- Tancar la sessió (`logout`) esborrant fitxers de token i cookies.
- Suport per output RAW (`--raw`) i desactivació de verificació SSL (`--insecure`).
- JSON amb colors i símbols Unicode per facilitar la lectura (o RAW per scripts).
- Spinner visual per indicar accions en progrés.
- Configurable amb variables d’entorn:
  - `IREDAPI_URL`: URL base de l’API (per defecte: `https://localhost/iredadmin/api`)
  - `IREDAPI_RAW=1`: activa mode RAW per defecte
  - `IREDAPI_INSECURE=1`: ignora errors SSL
  - `IREDAPI_MASK_SENSITIVE=0`: Mostra claus sensibles (com api_token, password, etc.)
  - `IREDAPI_DEBUG=1`: mostra missatges `Logger.debug()` per depuració
   
| Cas                    | `MASK_SENSITIVE_DATA` | `--show-secrets` | Resultat           |
| ---------------------- | --------------------- | ---------------- | ------------------ |
| cap dels dos           | True (default)        | False            | S'amaguen secrets  |
| només `--show-secrets` | True                  | ✅ True          | Es mostren secrets |
| només var d'entorn `IREDAPI_MASK_SENSITIVE=1` | False                 | False            | Es mostren secrets |
| tots dos               | False                 | ✅ True          | Es mostren secrets |


## 1. 📁 Fitxers utilitzats

- `~/.iredapi_token`: token desat
- `~/.iredapi_cookies.txt`: cookies de sessió

## 🧪 Exemples d’ús

### 🔑 Iniciar sessió
```bash
$ ./iredapi_manager.py login -u admin@example.com
Contrasenya: ********
```
Sortida esperada: 

```bash
✅ Login correcte. Token guardat.
```
### 👤 Consultar sessió

```bash
$ ./iredapi_manager.py session
```
Sortida esperada: 

```bash
🚀 Cridant a l'API... | ✅ Cookies carregades: 🍪 
{
  "_success": True,
  "_data": {
      "username": <USERNAME>,
      "is_global_admin": True,
      "is_domain_admin": False,
      "is_mail_admin": False,
      "is_user_admin": False,
      "token_present": True,
      "api_token": "SlfyCPAM...",
  }
}
```

### 📞 Fer una crida GET
```bash
$ ./iredapi_manager.py call -e /user/list
```

Sortida esperada: 

```bash
✅ Cookies carregades: 🍪 
🚀 Cridant a l'API...
{
  "_success": true,
  "_data": [
    {
      "mail": "admin@example.com",
      "active": true,
      ...
    }
  ]
}
```
### 📤 Fer una crida POST amb dades
```bash
$ ./iredapi_manager.py call -e /user/create -m POST -d '{"mail": "nou@exemple.cat", "password": "secret"}'
```

Sortida esperada: 

```bash
✅ Cookies carregades: 🍪 
🚀 Cridant a l'API...
✅ Usuari creat correctament.
```

### 🔑 Mostrar token

```bash
$ ./iredapi_manager.py token
```

Sortida esperada: 

```bash
✅ Token actual 🔑 : tejD1VUv...
```

### 🚪 Tancar sessió
```bash
$ ./iredapi_manager.py logout
```

Sortida esperada: 

```bash
✅ Fitxer de cookies eliminat.
✅ Fitxer de token eliminat.
👋 Sessió tancada.
```

### 🧪 Exemple: Variables d'entorn
#### 🔧 Configuració temporal (només per la sessió actual de terminal)
```bash
# 🔁 Indica la URL base de l'API (sobreescriu el valor per defecte)
export IREDAPI_URL="https://mail.example.com/iredadmin/api"

# 🎨 Mostra el JSON sense colors (equivalent a --raw)
export IREDAPI_RAW=1

# 🛡️ Ignora errors de certificat SSL (equivalent a --insecure o curl -k)
export IREDAPI_INSECURE=1

# 🐛 Activa missatges de depuració (Logger.debug)
export IREDAPI_DEBUG=1

# 🔐 mostra els valors sensibles:
# SENSITIVE_KEYS = {'password', 'api_token', 'session_id', 'token'}
export IREDAPI_MASK_SENSITIVE=0
```

#### 🚫 Desactivar (netejar variables)
```bash
unset IREDAPI_RAW        # Torna a activar colors en la sortida
unset IREDAPI_INSECURE   # Torna a validar els certificats SSL
unset IREDAPI_DEBUG      # Amaga missatges de depuració
unset IREDAPI_MASK_SENSITIVE # Amaga dades sensibles 
```

#### 🧑‍💻 Exemple d’ús combinat amb crida
```bash
$ export IREDAPI_URL="https://mail.example.com/iredadmin/api"
$ export IREDAPI_RAW=1
$ export IREDAPI_INSECURE=1
$ export IREDAPI_DEBUG=1
$ export IREDAPI_MASK_SENSITIVE=0

$ ./iredapi_manager.py call -e /user/example@example.com -m GET
```
Sortida esperada:

```json
{
  "_success": true,
  "_data": {
    "username": "example@example.com",
    ...
  }
}
```
(amb `IREDAPI_DEBUG=1` també veuries línies amb `[DEBUG]` sobre l’URL, token, etc.)

### ℹ️ Ajuda
Consulta totes les opcions amb:
```bash
$ ./iredapi_manager.py --help
```

Sortida esperada: 

```bash
usage: iredapi [-h] [--url URL] [-k] [-r] [-t TOKEN] [--cookies COOKIES] {login,call,logout,token,session} ...

🔐 CLI per a l'API iRedAdmin Pots usar la variable d'entorn IREDAPI_INSECURE=1 per ignorar errors SSL. Opció -k / --insecure equivalent a curl -k. La URL base per defecte és https://localhost/iredadmin però la pots
canviar amb: --url o la variable d'entorn IREDAPI_URL però si indiques --raw, el JSON es mostra en format normal (sense codi de color).

optional arguments:
  -h, --help            show this help message and exit
  --url URL             URL base de l'API
  -k, --insecure        Ignora errors de certificat SSL
  -r, --raw             Sortida RAW sense colors
  -t TOKEN, --token TOKEN
                        Token d'autenticació personalitzat
  --cookies COOKIES     Fitxer de cookies

Subcomandes:
  {login,call,logout,token,session}
    login               Iniciar sessió i desa cookies
    call                Fer una crida a l'API
    logout              Esborra el fitxer de cookies
    token               Mostra el token desat
    session             Mostrar informació de sessió actual

ℹ️ Per a més ajuda, usa --help o ajuda subcomanda. ℹ️ Per a més informació sobre les API, visita: https://iredmail.org/api.html
```

# 📁 .env per a iredapi_manager.py
## 🔍 Què és un .env?
Un fitxer `.env` és un arxiu de text que conté variables d'entorn definides línia a línia. S'utilitza per configurar paràmetres sense modificar el codi font.

Encara que `iredapi_manager.py` no carrega `.env` automàticament, pots fer-ho tu mateix amb source, o usar-lo com a referència ràpida.

## 📝 Exemple de .env
```dotenv
# URL base de l'API d’iRedAdmin
IREDAPI_URL=https://mail.example.com/iredadmin/api

# Desactiva colors ANSI i símbols → JSON brut (equivalent a --raw)
IREDAPI_RAW=1

# Ignora errors de certificat SSL (equivalent a -k / --insecure)
IREDAPI_INSECURE=1

# Mostra missatges de depuració detallats (Logger.debug)
IREDAPI_DEBUG=1

# Mostra dades sensibles definides a SENSITIVE_KEYS = {'password', 'api_token', 'session_id', 'token'}
IREDAPI_MASK_SENSITIVE=0
```

### ▶️ Com fer-lo servir
Crea el fitxer `.env`:

```bash
$ nano ~/.iredapi.env
```
Enganxa-hi el contingut anterior i desa'l.
Carrega'l a la sessió actual de terminal:

```bash
$ source ~/.iredapi.env
```

Executa el script com sempre:

```bash
$ ./iredapi_manager.py session
```
🧼 Per desactivar les variables:
```bash
$ unset IREDAPI_RAW
$ unset IREDAPI_INSECURE
$ unset IREDAPI_DEBUG
```
### ℹ️ Notes
Les variables de `.env` tenen efecte mentre la terminal estigui oberta o fins que facis unset.

Pots afegir `source ~/.iredapi.env` al teu `~/.bashrc`, `~/.zshrc` o `~/.profile` si vols que es carreguin sempre automàticament.


## 📄 Llicència

Aquest projecte està disponible sota la llicència MIT. Consulta el fitxer `LICENSE` per a més informació.

## 🙌 Crèdits

Desenvolupat per cuque@gmail.com. Inspirat en l'ús de l’API REST d’iRedAdmin.
