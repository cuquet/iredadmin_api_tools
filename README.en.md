# iRedAPI CLI – `iredapi_manager.py`

## What is it?

`iredapi_manager.py` is a command-line interface (CLI) tool to interact with the iRedAdmin REST API. It enables sysadmins to manage users and perform administrative tasks remotely through HTTP API calls.

- Simple CLI to:
  - Login and store token + session cookies
  - Make HTTP API requests (GET, POST, PUT, DELETE, PATCH)
  - Show current token or session
  - Logout (delete token and cookies)
- Displays JSON output with syntax highlighting and Unicode symbols
- Spinner for visual feedback on actions
- Supports skipping SSL certificate validation (like `curl -k`)
- Uses local files to store session data (`~/.iredapi_cookies.txt`)
- URLs, cookie files, and parameters configurable via CLI arguments or environment variables

## 🔧 Features

- `login`: Authenticate with username and password
- Automatically saves token and cookies
- `call`: Make HTTP API requests to any endpoint
- `token`: Show current token
- `session`: Show current session details
- `logout`: Delete token and cookie files
- Optional RAW output (`--raw`) for scripting
- Optional SSL verification bypass (`--insecure`)
- JSON colorized output for readability (unless RAW is enabled)
- ASCII spinner shows ongoing actions
- Environment variable support:
  - `IREDAPI_URL`: API base URL (default: `https://localhost/iredadmin/api`)
  - `IREDAPI_RAW=1`: enables RAW mode by default
  - `IREDAPI_INSECURE=1`: disables SSL verification
  - `IREDAPI_DEBUG=1`: shows `Logger.debug()` output for debugging

## 📁 Used Files

- `~/.iredapi_cookies.txt`: stores session cookies

## 🧪 Examples

### 🔐 Login

```bash
$ ./iredapi_manager.py login -u admin@example.com
Contrasenya: ********  # request for password
```
Expected output:

```bash
✅  Login correcte. Token guardat. #Login successful. Token saved.
```

### 📞 Perform a GET request

```bash
$ ./iredapi_manager.py call -e /user/list
```
Expected output:

```bash
✅  Cookies carregades: 🍪 #Loaded cookies 
🚀 Cridant a l'API... # Calling API...
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

### 📤 Perform a POST request with JSON data

```bash
$ ./iredapi_manager.py call -e /user/create -m POST -d '{"mail": "new@domain.com", "password": "secret"}'
```
Expected output:

```bash
✅ Cookies carregades: 🍪 
🚀 Cridant a l'API...
✅ Usuari creat correctament. #User successfully created.
```

### 🔑 Show current token

```bash
$ ./iredapi_manager.py token
```
Expected output:

```bash
✅ Token actual 🔑 : tejD1VUv... # Current token
```

### 🚪 Logout

```bash
$ ./iredapi_manager.py logout
```
Expected output:

```bash
✅ Fitxer de cookies eliminat. #Cookies file deleted.
✅ Fitxer de token eliminat. #Token file deleted.
👋 Sessió tancada. #Logged out.
```

### 🧪 Using Environment Variables
#### 🔧 Temporary configuration (current terminal session only)

```bash
export IREDAPI_URL="https://mail.example.com/iredadmin/api"
export IREDAPI_RAW=1        # Disable color output
export IREDAPI_INSECURE=1   # Skip SSL verification
export IREDAPI_DEBUG=1      # Show debug messages
```

#### 🔄 Disable variables
```bash
unset IREDAPI_RAW
unset IREDAPI_INSECURE
unset IREDAPI_DEBUG
```

#### 👩‍💻 Example with custom environment

```bash
$ export IREDAPI_URL="https://mail.example.com/iredadmin/api"
$ export IREDAPI_RAW=1
$ export IREDAPI_INSECURE=1
$ export IREDAPI_DEBUG=1

$ ./iredapi_manager.py call -e /user/example@example.com -m GET
```
Expected output:

```json
{
  "_success": true,
  "_data": {
    "username": "example@example.com",
    ...
  }
}
```
(With IREDAPI_DEBUG=1 enabled, you’ll also see [DEBUG] messages showing URL, token, etc.)

### ℹ️ Help
Get all options with:

```bash
$ ./iredapi_manager.py --help
```

Expected output:

```bash
usage: iredapi [-h] [--url URL] [-k] [-r] [-t TOKEN] [--cookies COOKIES] {login,call,logout,token,session} ...

🔐 CLI for iRedAdmin REST API. You can use the IREDAPI_INSECURE=1 environment variable to skip SSL verification. The -k / --insecure option is equivalent to curl -k. Default base URL is https://localhost/iredadmin/api,
but you can override it with --url or the IREDAPI_URL env variable. Use --raw to disable JSON coloring.

optional arguments:
  -h, --help            Show help and exit
  --url URL             Base API URL
  -k, --insecure        Skip SSL certificate verification
  -r, --raw             Raw JSON output (no colors or symbols)
  -t TOKEN, --token TOKEN
                        Custom authentication token
  --cookies COOKIES     Cookie file to use

Subcommands:
  {login,call,logout,token,session}
    login               Authenticate and save cookies
    call                Make API request
    logout              Delete session cookies
    token               Show saved token
    session             Display current session details

ℹ️ For more help, use --help or subcommand help. ℹ️ For full API documentation, visit: https://iredmail.org/api.html
```

# 📁 .env Support (optional)
## 🔍 What is a .env file?
A `.env` file is a text file with environment variable definitions. It’s useful to configure CLI settings without modifying the code.

Although `iredapi_manager.py` doesn’t auto-load .env files, you can source one manually.

## 📝 Example .env file
```dotenv
# API base URL
IREDAPI_URL=https://mail.example.com/iredadmin/api

# Disable ANSI color / Unicode formatting
IREDAPI_RAW=1

# Skip SSL verification
IREDAPI_INSECURE=1

# Enable debug output
IREDAPI_DEBUG=1
```

### ▶️ Usage
Create the file:

```bash
$ nano ~/.iredapi.env
```
Paste the content above, save it, then:

```bash
$ source ~/.iredapi.env
```
Then run the CLI:

```bash
$ ./iredapi_manager.py session
```
🧼 To disable the variables:

```bash
$ unset IREDAPI_RAW
$ unset IREDAPI_INSECURE
$ unset IREDAPI_DEBUG
You can also add source ~/.iredapi.env to your ~/.bashrc, ~/.zshrc, or ~/.profile to auto-load it on shell startup.
```

## 📄 License
This project is available under the MIT license. See the LICENSE file for more details.

## 🙌 Credits
Developed by cuque@gmail.com. Inspired by real-world usage of the iRedAdmin REST API.