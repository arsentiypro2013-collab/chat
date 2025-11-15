from http.server import HTTPServer, SimpleHTTPRequestHandler
import sqlite3
import hashlib
import json
import os
from urllib.parse import parse_qs
import threading

class ChatHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.setup_database()
        super().__init__(*args, **kwargs)
    
    def setup_database(self):
        """Инициализация базы данных"""
        self.conn = sqlite3.connect('chat.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Создаем таблицу пользователей с правильными колонками
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                avatar TEXT DEFAULT '1',
                theme TEXT DEFAULT 'light',
                notifications BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица контактов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (contact_id) REFERENCES users (id),
                UNIQUE(user_id, contact_id)
            )
        ''')
        
        # Таблица сообщений
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users (id),
                FOREIGN KEY (receiver_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
        print("[+] База данных инициализирована")
    
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()
    
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data)
            
            if self.path == '/api/register':
                response = self.handle_register(data)
            elif self.path == '/api/login':
                response = self.handle_login(data)
            elif self.path == '/api/settings':
                response = self.handle_settings(data)
            elif self.path == '/api/contacts':
                response = self.handle_contacts(data)
            else:
                response = {'success': False, 'message': 'Неизвестный endpoint'}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"Ошибка обработки запроса: {e}")
            self.send_error(500, str(e))
    
    def handle_register(self, data):
        """Обработка регистрации"""
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        avatar = data.get('avatar', '1')
        
        if not username or len(username) < 3:
            return {'success': False, 'message': 'Имя пользователя должно быть не менее 3 символов'}
        
        if not password or len(password) < 4:
            return {'success': False, 'message': 'Пароль должен быть не менее 4 символов'}
        
        try:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            self.cursor.execute(
                "INSERT INTO users (username, password, avatar) VALUES (?, ?, ?)",
                (username, hashed_password, avatar)
            )
            self.conn.commit()
            
            return {'success': True, 'message': 'Регистрация успешна!'}
            
        except sqlite3.IntegrityError:
            return {'success': False, 'message': 'Пользователь уже существует!'}
        except Exception as e:
            return {'success': False, 'message': f'Ошибка регистрации: {str(e)}'}
    
    def handle_login(self, data):
        """Обработка входа"""
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return {'success': False, 'message': 'Заполните все поля'}
        
        try:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            self.cursor.execute(
                "SELECT id, username, avatar, theme, notifications FROM users WHERE username = ? AND password = ?",
                (username, hashed_password)
            )
            user = self.cursor.fetchone()
            
            if user:
                user_data = {
                    'id': user[0],
                    'username': user[1],
                    'avatar': user[2],
                    'theme': user[3],
                    'notifications': bool(user[4])
                }
                return {
                    'success': True, 
                    'message': 'Вход выполнен!',
                    'user_data': user_data
                }
            else:
                return {'success': False, 'message': 'Неверное имя пользователя или пароль'}
                
        except Exception as e:
            return {'success': False, 'message': f'Ошибка входа: {str(e)}'}
    
    def handle_settings(self, data):
        """Обновление настроек"""
        username = data.get('username', '')
        settings = data.get('settings', {})
        
        try:
            updates = []
            params = []
            
            if 'theme' in settings:
                updates.append("theme = ?")
                params.append(settings['theme'])
            if 'notifications' in settings:
                updates.append("notifications = ?")
                params.append(1 if settings['notifications'] else 0)
            if 'avatar' in settings:
                updates.append("avatar = ?")
                params.append(settings['avatar'])
            
            if updates:
                params.append(username)
                query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
                self.cursor.execute(query, params)
                self.conn.commit()
                return {'success': True, 'message': 'Настройки обновлены'}
            else:
                return {'success': False, 'message': 'Нет настроек для обновления'}
                
        except Exception as e:
            return {'success': False, 'message': f'Ошибка обновления настроек: {str(e)}'}
    
    def handle_contacts(self, data):
        """Обработка операций с контактами"""
        username = data.get('username', '')
        action = data.get('action', '')
        
        try:
            if action == 'add':
                contact_username = data.get('contact_username', '')
                return self.add_contact(username, contact_username)
            elif action == 'get':
                contacts = self.get_contacts(username)
                return {'success': True, 'contacts': contacts}
            elif action == 'remove':
                contact_username = data.get('contact_username', '')
                return self.remove_contact(username, contact_username)
            else:
                return {'success': False, 'message': 'Неизвестное действие'}
                
        except Exception as e:
            return {'success': False, 'message': f'Ошибка: {str(e)}'}
    
    def add_contact(self, username, contact_username):
        """Добавление контакта"""
        if username == contact_username:
            return {'success': False, 'message': 'Нельзя добавить себя в контакты'}
        
        # Проверяем существование пользователя
        self.cursor.execute("SELECT id FROM users WHERE username = ?", (contact_username,))
        contact = self.cursor.fetchone()
        if not contact:
            return {'success': False, 'message': 'Пользователь не найден'}
        
        # Получаем ID текущего пользователя
        self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = self.cursor.fetchone()
        if not user:
            return {'success': False, 'message': 'Ошибка пользователя'}
        
        user_id = user[0]
        contact_id = contact[0]
        
        # Проверяем, не добавлен ли уже контакт
        self.cursor.execute(
            "SELECT id FROM contacts WHERE user_id = ? AND contact_id = ?",
            (user_id, contact_id)
        )
        if self.cursor.fetchone():
            return {'success': False, 'message': 'Контакт уже добавлен'}
        
        # Добавляем контакт
        self.cursor.execute(
            "INSERT INTO contacts (user_id, contact_id) VALUES (?, ?)",
            (user_id, contact_id)
        )
        self.conn.commit()
        return {'success': True, 'message': 'Контакт добавлен'}
    
    def get_contacts(self, username):
        """Получение списка контактов"""
        try:
            self.cursor.execute('''
                SELECT u.username, u.avatar 
                FROM contacts c 
                JOIN users u ON c.contact_id = u.id 
                WHERE c.user_id = (SELECT id FROM users WHERE username = ?)
                ORDER BY u.username
            ''', (username,))
            
            contacts = self.cursor.fetchall()
            return [{'username': c[0], 'avatar': c[1], 'status': 'online'} for c in contacts]
        except Exception as e:
            print(f"Ошибка получения контактов: {e}")
            return []
    
    def remove_contact(self, username, contact_username):
        """Удаление контакта"""
        try:
            self.cursor.execute('''
                DELETE FROM contacts 
                WHERE user_id = (SELECT id FROM users WHERE username = ?)
                AND contact_id = (SELECT id FROM users WHERE username = ?)
            ''', (username, contact_username))
            
            affected_rows = self.cursor.rowcount
            self.conn.commit()
            
            if affected_rows > 0:
                return {'success': True, 'message': 'Контакт удален'}
            else:
                return {'success': False, 'message': 'Контакт не найден'}
                
        except Exception as e:
            return {'success': False, 'message': f'Ошибка удаления: {str(e)}'}

def run_server(port=8000):
    """Запуск сервера"""
    web_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(web_dir)
    
    server = HTTPServer(('0.0.0.0', port), ChatHandler)
    print(f"[*] Сервер запущен на порту {port}")
    print(f"[*] Откройте: http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    run_server(port)