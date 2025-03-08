from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # 本番環境では安全な値に変更すること
CORS(app)

def init_db():
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    
    # ユーザーテーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            department TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 予約テーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            exam_type TEXT NOT NULL,
            preferred_date DATE NOT NULL,
            preferred_time TIME NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # テストユーザーの追加
    c.execute('INSERT OR IGNORE INTO users (id, password, name, department, role) VALUES (?, ?, ?, ?, ?)',
             ('test', 'test', 'テストユーザー', '総務部', 'user'))
    
    # 管理者ユーザーの追加
    c.execute('INSERT OR IGNORE INTO users (id, password, name, department, role) VALUES (?, ?, ?, ?, ?)',
             ('admin', 'admin', '管理者', '人事部', 'admin'))
    
    conn.commit()
    conn.close()

def get_all_reservations():
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    try:
        c.execute('''
            SELECT 
                r.id,
                r.exam_type,
                r.preferred_date,
                r.preferred_time,
                r.status,
                r.created_at,
                r.created_at,
                u.name,
                u.department
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.created_at DESC
        ''')
        reservations = c.fetchall()
        print(f"Found {len(reservations)} reservations")  # デバッグ用
        for res in reservations:  # デバッグ用
            print(f"Reservation: {res}")
        return reservations
    except Exception as e:
        print(f"Error fetching reservations: {e}")  # デバッグ用
        return []
    finally:
        conn.close()

def update_reservation_status(reservation_id, new_status):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('UPDATE reservations SET status = ? WHERE id = ?', (new_status, reservation_id))
    conn.commit()
    conn.close()

def get_user_reservations(user_id):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        SELECT exam_type, preferred_date, preferred_time, status, created_at
        FROM reservations
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    reservations = c.fetchall()
    conn.close()
    return reservations

def count_reservations_by_status(user_id):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        SELECT status, COUNT(*) as count
        FROM reservations
        WHERE user_id = ?
        GROUP BY status
    ''', (user_id,))
    counts = dict(c.fetchall())
    conn.close()
    return {
        'pending': counts.get('pending', 0),
        'approved': counts.get('approved', 0),
        'next_exam': get_next_exam_date(user_id)
    }

def get_next_exam_date(user_id):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        SELECT preferred_date
        FROM reservations
        WHERE user_id = ? AND status = 'approved' AND preferred_date >= date('now')
        ORDER BY preferred_date ASC
        LIMIT 1
    ''', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# データベースの初期化
init_db()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

class User(UserMixin):
    def __init__(self, id, name, department, role):
        self.id = id
        self.name = name
        self.department = department
        self.role = role
    
    def is_admin(self):
        return self.role == 'admin'

def get_user_by_id(user_id):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('SELECT id, name, department, role FROM users WHERE id = ?', (user_id,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2], user_data[3])
    return None

def verify_user(user_id, password):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('SELECT id, name, department, role FROM users WHERE id = ? AND password = ?', (user_id, password))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2], user_data[3])
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('この操作には管理者権限が必要です。')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# HTML template with modern, gradient design
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康診断管理システム - ログイン</title>
    <style>
        .error-message {
            color: #e53e3e;
            text-align: center;
            margin-bottom: 1rem;
            font-weight: 500;
        }
        body {
            margin: 0;
            padding: 0;
            min-height: 100vh;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-container {
            background: rgba(255, 255, 255, 0.95);
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 400px;
            backdrop-filter: blur(10px);
        }
        h1 {
            color: #2d3748;
            text-align: center;
            margin-bottom: 2rem;
            font-weight: 600;
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        label {
            display: block;
            color: #4a5568;
            margin-bottom: 0.5rem;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e2e8f0;
            border-radius: 6px;
            font-size: 1rem;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background: linear-gradient(to right, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-1px);
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>健康診断管理システム</h1>
        {% if error %}
        <div class="error-message">{{ error }}</div>
        {% endif %}
        <form method="post" action="/login">
            <div class="form-group">
                <label for="employee_id">社員ID</label>
                <input type="text" id="employee_id" name="employee_id" required placeholder="テストID: test">
            </div>
            <div class="form-group">
                <label for="password">パスワード</label>
                <input type="password" id="password" name="password" required placeholder="テストパスワード: test">
            </div>
            <button type="submit">ログイン</button>
        </form>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template_string(HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    employee_id = request.form.get('employee_id')
    password = request.form.get('password')
    
    user = verify_user(employee_id, password)
    if user:
        login_user(user)
        return redirect(url_for('dashboard'))
    else:
        return render_template_string(HTML_TEMPLATE, error="ユーザーIDまたはパスワードが正しくありません")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # 予約状況の取得
    stats = count_reservations_by_status(current_user.id)
    reservations = get_user_reservations(current_user.id)
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        employee_id=current_user.name,
        department=current_user.department,
        pending_count=stats['pending'],
        approved_count=stats['approved'],
        next_exam=stats['next_exam'],
        reservations=reservations
    )

@app.route('/reservation', methods=['GET'])
@login_required
def reservation():
    if current_user.is_admin():
        flash('管理者は予約申請できません')
        return redirect(url_for('admin_dashboard'))
    return render_template_string(
        RESERVATION_TEMPLATE,
        employee_id=current_user.name,
        department=current_user.department
    )

@app.route('/submit_reservation', methods=['POST'])
@login_required
def submit_reservation():
    if current_user.is_admin():
        flash('管理者は予約申請できません')
        return redirect(url_for('admin_dashboard'))

    exam_type = request.form.get('exam_type')
    preferred_date = request.form.get('preferred_date')
    preferred_time = request.form.get('preferred_time')
    notes = request.form.get('notes')
    
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO reservations 
            (user_id, exam_type, preferred_date, preferred_time, notes, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (current_user.id, exam_type, preferred_date, preferred_time, notes, 'pending'))
        conn.commit()
        flash('予約申請を受け付けました。')
    except Exception as e:
        flash('予約申請に失敗しました。')
        print(f"Error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    reservations = get_all_reservations()
    return render_template_string(ADMIN_TEMPLATE, 
        employee_id=current_user.name,
        department=current_user.department,
        reservations=reservations
    )

@app.route('/admin/approve/<int:reservation_id>')
@login_required
@admin_required
def approve_reservation(reservation_id):
    update_reservation_status(reservation_id, 'approved')
    flash('予約を承認しました。')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:reservation_id>')
@login_required
@admin_required
def reject_reservation(reservation_id):
    update_reservation_status(reservation_id, 'rejected')
    flash('予約を却下しました。')
    return redirect(url_for('admin_dashboard'))

# 管理者用ダッシュボードのテンプレート
ADMIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康診断管理システム - 管理者ダッシュボード</title>
    <style>
        :root {
            --primary-color: #667eea;
            --secondary-color: #764ba2;
            --text-color: #2d3748;
            --sidebar-width: 250px;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background: #f7fafc;
        }
        
        .header {
            position: fixed;
            top: 0;
            left: var(--sidebar-width);
            right: 0;
            height: 60px;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 2rem;
            z-index: 100;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .logout-btn {
            padding: 0.5rem 1rem;
            background: linear-gradient(to right, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
        }
        
        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            width: var(--sidebar-width);
            height: 100vh;
            background: white;
            box-shadow: 2px 0 4px rgba(0,0,0,0.1);
            padding-top: 2rem;
        }
        
        .logo {
            text-align: center;
            padding: 1rem;
            font-size: 1.2rem;
            font-weight: bold;
            color: var(--primary-color);
        }
        
        .nav-menu {
            list-style: none;
            padding: 0;
            margin: 2rem 0;
        }
        
        .nav-item {
            padding: 1rem 2rem;
            color: var(--text-color);
            cursor: pointer;
            transition: background-color 0.2s;
        }
        
        .nav-item:hover {
            background: rgba(102, 126, 234, 0.1);
            color: var(--primary-color);
        }
        
        .nav-item a {
            text-decoration: none;
            color: inherit;
            display: block;
        }
        
        .main-content {
            margin-left: var(--sidebar-width);
            margin-top: 60px;
            padding: 2rem;
        }
        
        .applications-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 1.5rem;
        }
        
        .applications-list h2 {
            margin: 0 0 1.5rem 0;
            color: var(--text-color);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        
        th {
            background: #f8fafc;
            font-weight: 600;
        }
        
        tr:hover {
            background: #f8fafc;
        }
        
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        
        .status-pending {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-approved {
            background: #dcfce7;
            color: #166534;
        }
        
        .status-rejected {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .action-buttons {
            display: flex;
            gap: 0.5rem;
        }
        
        .btn {
            padding: 0.25rem 0.75rem;
            border-radius: 6px;
            font-size: 0.875rem;
            text-decoration: none;
            cursor: pointer;
        }
        
        .btn-approve {
            background: #dcfce7;
            color: #166534;
        }
        
        .btn-reject {
            background: #fee2e2;
            color: #991b1b;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">健康診断管理システム</div>
        <ul class="nav-menu">
            <li class="nav-item"><a href="/admin/dashboard">管理者ダッシュボード</a></li>
            <li class="nav-item"><a href="/dashboard">ユーザーダッシュボード</a></li>
            <li class="nav-item"><a href="#">ユーザー管理</a></li>
            <li class="nav-item"><a href="#">システム設定</a></li>
        </ul>
    </div>
    
    <header class="header">
        <div class="user-info">
            <span>{{ employee_id }} (管理者)</span>
            <a href="/logout" class="logout-btn">ログアウト</a>
        </div>
    </header>
    
    <main class="main-content">
        <div class="applications-list">
            <h2>予約申請一覧</h2>
            {% if reservations %}
            <table>
                <thead>
                    <tr>
                        <th>申請日</th>
                        <th>社員名</th>
                        <th>所属</th>
                        <th>健診種別</th>
                        <th>希望日時</th>
                        <th>ステータス</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for reservation in reservations %}
                    <tr>
                        <td>{{ reservation[6] }}</td>
                        <td>{{ reservation[7] }}</td>
                        <td>{{ reservation[8] }}</td>
                        <td>{{ reservation[1] }}</td>
                        <td>{{ reservation[2] }} {{ reservation[3] }}</td>
                        <td>
                            <span class="status-badge status-{{ reservation[4] }}">
                                {{ '承認済' if reservation[4] == 'approved' else '却下' if reservation[4] == 'rejected' else '申請中' }}
                            </span>
                        </td>
                        <td>
                            {% if reservation[4] == 'pending' %}
                            <div class="action-buttons">
                                <a href="/admin/approve/{{ reservation[0] }}" class="btn btn-approve">承認</a>
                                <a href="/admin/reject/{{ reservation[0] }}" class="btn btn-reject">却下</a>
                            </div>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="text-align: center; color: #666; padding: 2rem;">予約申請はありません</p>
            {% endif %}
        </div>
    </main>
</body>
</html>
'''

# 予約申請画面のテンプレート
RESERVATION_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康診断管理システム - 予約申請</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
    <script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
    <script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/ja.js"></script>
    <style>
        :root {
            --primary-color: #667eea;
            --secondary-color: #764ba2;
            --text-color: #2d3748;
            --sidebar-width: 250px;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background: #f7fafc;
        }
        
        .header {
            position: fixed;
            top: 0;
            left: var(--sidebar-width);
            right: 0;
            height: 60px;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 2rem;
            z-index: 100;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .logout-btn {
            padding: 0.5rem 1rem;
            background: linear-gradient(to right, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        
        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            width: var(--sidebar-width);
            height: 100vh;
            background: white;
            box-shadow: 2px 0 4px rgba(0,0,0,0.1);
            padding-top: 2rem;
        }
        
        .logo {
            text-align: center;
            padding: 1rem;
            font-size: 1.2rem;
            font-weight: bold;
            color: var(--primary-color);
        }
        
        .nav-menu {
            list-style: none;
            padding: 0;
            margin: 2rem 0;
        }
        
        .nav-item {
            padding: 1rem 2rem;
            color: var(--text-color);
            cursor: pointer;
            transition: background-color 0.2s;
        }
        
        .nav-item:hover {
            background: rgba(102, 126, 234, 0.1);
            color: var(--primary-color);
        }
        
        .main-content {
            margin-left: var(--sidebar-width);
            margin-top: 60px;
            padding: 2rem;
        }

        .reservation-form {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            max-width: 800px;
            margin: 0 auto;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            color: var(--text-color);
            font-weight: 500;
        }

        .form-control {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e2e8f0;
            border-radius: 6px;
            font-size: 1rem;
            transition: border-color 0.2s;
        }

        .form-control:focus {
            outline: none;
            border-color: var(--primary-color);
        }

        select.form-control {
            background-color: white;
        }

        textarea.form-control {
            min-height: 100px;
            resize: vertical;
        }

        .submit-btn {
            display: block;
            width: 100%;
            padding: 1rem;
            background: linear-gradient(to right, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }

        .submit-btn:hover {
            transform: translateY(-1px);
        }

        .form-title {
            margin: 0 0 2rem 0;
            color: var(--text-color);
            text-align: center;
        }

        .time-slots {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 1rem;
            margin-top: 0.5rem;
        }

        .time-slot {
            padding: 0.5rem;
            border: 2px solid #e2e8f0;
            border-radius: 6px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .time-slot:hover {
            border-color: var(--primary-color);
            background: rgba(102, 126, 234, 0.1);
        }

        .time-slot.selected {
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">健康診断管理システム</div>
        <ul class="nav-menu">
            <li class="nav-item"><a href="/dashboard" style="text-decoration: none; color: inherit;">ダッシュボード</a></li>
            <li class="nav-item"><a href="/reservation" style="text-decoration: none; color: inherit;">健診予約申請</a></li>
            <li class="nav-item"><a href="#" style="text-decoration: none; color: inherit;">結果確認</a></li>
            <li class="nav-item"><a href="#" style="text-decoration: none; color: inherit;">履歴</a></li>
            <li class="nav-item"><a href="#" style="text-decoration: none; color: inherit;">設定</a></li>
        </ul>
    </div>
    
    <header class="header">
        <div class="user-info">
            <span>{{ employee_id }}</span>
            <a href="/logout" class="logout-btn" style="text-decoration: none;">ログアウト</a>
        </div>
    </header>
    
    <main class="main-content">
        <form class="reservation-form" action="/submit_reservation" method="POST">
            <h2 class="form-title">健康診断予約申請</h2>
            
            <div class="form-group">
                <label for="exam_type">健診種別</label>
                <select id="exam_type" name="exam_type" class="form-control" required>
                    <option value="">選択してください</option>
                    <option value="定期健康診断">定期健康診断</option>
                    <option value="特殊健康診断">特殊健康診断</option>
                    <option value="特定健康診断">特定健康診断</option>
                </select>
            </div>

            <div class="form-group">
                <label for="preferred_date">希望日</label>
                <input type="text" id="preferred_date" name="preferred_date" class="form-control" required>
            </div>

            <div class="form-group">
                <label>希望時間帯</label>
                <div class="time-slots">
                    <div class="time-slot" data-time="09:00">09:00</div>
                    <div class="time-slot" data-time="10:00">10:00</div>
                    <div class="time-slot" data-time="11:00">11:00</div>
                    <div class="time-slot" data-time="13:00">13:00</div>
                    <div class="time-slot" data-time="14:00">14:00</div>
                    <div class="time-slot" data-time="15:00">15:00</div>
                </div>
                <input type="hidden" id="preferred_time" name="preferred_time" required>
            </div>

            <div class="form-group">
                <label for="notes">備考</label>
                <textarea id="notes" name="notes" class="form-control" placeholder="特記事項があればご記入ください"></textarea>
            </div>

            <button type="submit" class="submit-btn">予約を申請する</button>
        </form>
    </main>

    <script>
        // カレンダーの初期化
        flatpickr("#preferred_date", {
            locale: "ja",
            dateFormat: "Y/m/d",
            minDate: "today",
            disable: [
                function(date) {
                    return (date.getDay() === 0 || date.getDay() === 6);
                }
            ]
        });

        // 時間帯選択の処理
        document.querySelectorAll('.time-slot').forEach(slot => {
            slot.addEventListener('click', function() {
                document.querySelectorAll('.time-slot').forEach(s => s.classList.remove('selected'));
                this.classList.add('selected');
                document.getElementById('preferred_time').value = this.dataset.time;
            });
        });
    </script>
</body>
</html>
'''

# ダッシュボード画面のテンプレート
DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>健康診断管理システム - ダッシュボード</title>
    <style>
        :root {
            --primary-color: #667eea;
            --secondary-color: #764ba2;
            --text-color: #2d3748;
            --sidebar-width: 250px;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            background: #f7fafc;
        }

        .nav-item a {
            display: block;
            width: 100%;
            height: 100%;
            text-decoration: none;
            color: inherit;
        }
        
        .header {
            position: fixed;
            top: 0;
            left: var(--sidebar-width);
            right: 0;
            height: 60px;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 2rem;
            z-index: 100;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .logout-btn {
            padding: 0.5rem 1rem;
            background: linear-gradient(to right, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        
        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            width: var(--sidebar-width);
            height: 100vh;
            background: white;
            box-shadow: 2px 0 4px rgba(0,0,0,0.1);
            padding-top: 2rem;
        }
        
        .logo {
            text-align: center;
            padding: 1rem;
            font-size: 1.2rem;
            font-weight: bold;
            color: var(--primary-color);
        }
        
        .nav-menu {
            list-style: none;
            padding: 0;
            margin: 2rem 0;
        }
        
        .nav-item {
            padding: 1rem 2rem;
            color: var(--text-color);
            cursor: pointer;
            transition: background-color 0.2s;
        }
        
        .nav-item:hover {
            background: rgba(102, 126, 234, 0.1);
            color: var(--primary-color);
        }
        
        .main-content {
            margin-left: var(--sidebar-width);
            margin-top: 60px;
            padding: 2rem;
        }
        
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .stat-card {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .stat-card h3 {
            margin: 0 0 1rem 0;
            color: var(--text-color);
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary-color);
        }
        
        .applications-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 1.5rem;
        }
        
        .applications-list h2 {
            margin: 0 0 1.5rem 0;
            color: var(--text-color);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        
        th {
            background: #f8fafc;
            font-weight: 600;
        }
        
        tr:hover {
            background: #f8fafc;
        }
        
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        
        .status-pending {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-approved {
            background: #dcfce7;
            color: #166534;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">健康診断管理システム</div>
        <ul class="nav-menu">
            <li class="nav-item"><a href="/dashboard">ダッシュボード</a></li>
            <li class="nav-item"><a href="/reservation">健診予約申請</a></li>
            <li class="nav-item"><a href="#">結果確認</a></li>
            <li class="nav-item"><a href="#">履歴</a></li>
            <li class="nav-item"><a href="#">設定</a></li>
        </ul>
    </div>
    
    <header class="header">
        <div class="user-info">
            <span>{{ employee_id }}</span>
            <a href="/logout" class="logout-btn" style="text-decoration: none;">ログアウト</a>
        </div>
    </header>
    
    <main class="main-content">
        <div class="dashboard-grid">
            <div class="stat-card">
                <h3>申請中の予約</h3>
                <div class="stat-value">{{ pending_count }}</div>
            </div>
            <div class="stat-card">
                <h3>承認済み予約</h3>
                <div class="stat-value">{{ approved_count }}</div>
            </div>
            <div class="stat-card">
                <h3>次回の健診予定</h3>
                <div class="stat-value">{{ next_exam if next_exam else '未定' }}</div>
            </div>
        </div>
        
        <div class="applications-list">
            <h2>申請状況一覧</h2>
            {% if reservations %}
            <table>
                <thead>
                    <tr>
                        <th>申請日</th>
                        <th>健診種別</th>
                        <th>希望日時</th>
                        <th>ステータス</th>
                    </tr>
                </thead>
                <tbody>
                    {% for exam_type, preferred_date, preferred_time, status, created_at in reservations %}
                    <tr>
                        <td>{{ created_at.split(' ')[0] }}</td>
                        <td>{{ exam_type }}</td>
                        <td>{{ preferred_date }} {{ preferred_time }}</td>
                        <td><span class="status-badge status-{{ status }}">{{ '承認済' if status == 'approved' else '申請中' }}</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="text-align: center; color: #666; padding: 2rem;">予約申請はありません</p>
            {% endif %}
        </div>
    </main>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=55110, debug=True)