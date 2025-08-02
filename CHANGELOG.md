# 📜 Changelog – iRedAPI CLI

All notable changes to this project will be documented in this file.

---

## 🔖 v0.11 – Final version with full CLI and .env support
- Completed CLI with login, API calls, logout, token/session inspection
- Support for `.env` and environment variables
- Improved JSON output with Unicode and color
- Final refinements and cleanup

---

## 🔖 v0.10 – Polish and usability improvements
- Enhanced session handling
- Improved error messages and fallback behavior

---

## 🔖 v0.9.1 – Minor bugfixes
- Fixed typos and logging issues
- Compatibility with token-less requests

---

## 🔖 v0.9 – Token/session inspection commands
- Added `token` and `session` subcommands
- Improved authentication persistence

---

## 🔖 v0.8 – Better output formatting
- Integrated colorized JSON using `rich`
- Added spinners for long-running actions

---

## 🔖 v0.7 – Add SSL/insecure toggle
- Support for `--insecure` and `IREDAPI_INSECURE`
- Improved argument parsing

---

## 🔖 v0.6 – RAW mode and environment support
- Added `--raw` and `IREDAPI_RAW`
- Initial support for `.env` workflows

---

## 🔖 v0.5 – Unified error handling
- Centralized error and response handling
- Standardized status icons in console

---

## 🔖 v0.4 – Add support for POST/PUT/DELETE
- `call` command supports all HTTP verbs
- JSON body via `-d` argument

---

## 🔖 v0.3 – Basic `call` support
- Can send GET requests to API endpoints
- Handles session token automatically

---

## 🔖 v0.2 – Improved login
- Automatic token and cookie saving
- Better login error messages

---

## 🔖 v0.1 – Initial version
- Basic CLI with login support
- Token handling and cookie storage
