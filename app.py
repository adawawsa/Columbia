from flask import Flask, render_template, render_template_string, request, redirect, url_for, flash, g, send_file, abort
from flask_cors import CORS # type: ignore
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user # type: ignore
from functools import wraps
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# アップロードファイルの最大サイズ (5MB)
MAX_CONTENT_LENGTH = 5 * 1024 * 1024

app = Flask(__name__, template_folder='templates')
# 環境変数から秘密鍵を読み込む、ない場合はデフォルト値を使用（本番環境では必ず設定すること）
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-for-development-only')
app.config['TEMPLATES_AUTO_RELOAD'] = True  # テンプレートの自動リロードを有効化
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 静的ファイルのキャッシュを無効化
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH  # アップロードサイズ制限
app.jinja_env.auto_reload = True  # Jinja2のキャッシュを無効化
app.jinja_env.cache = {}  # キャッシュをクリア
app.config['EXPLAIN_TEMPLATE_LOADING'] = True  # テンプレート読み込みの詳細表示

# 強制的にキャッシュを無効化する設定
@app.after_request
def add_header(response):
    """
    キャッシュ無効化ヘッダーを追加
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response
CORS(app)

# テンプレートのリロードを強制するためのヘルパー関数
@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        values['q'] = int(datetime.utcnow().timestamp())
    return url_for(endpoint, **values)

# アップロードされたファイルを保存するディレクトリ
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

# アップロードディレクトリが存在しない場合は作成
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# データベース接続の取得
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('health_check.db')
        g.db.row_factory = sqlite3.Row  # 結果をディクショナリ形式で取得するための設定
    return g.db

# アプリケーションコンテキスト終了時にDBコネクションをクローズ
@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

def init_db():
    db = get_db()
    c = db.cursor()
    
    # パスワードをハッシュ化する関数
    def hash_password(password):
        return generate_password_hash(password)
    
    # Check if users table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_table_exists = c.fetchone() is not None
    
    # ユーザーテーブル
    if not users_table_exists:
        c.execute('''
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                department TEXT,
                role TEXT DEFAULT 'user',
                work_type TEXT DEFAULT 'regular',
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        # Check if columns exist and add them if they don't
        c.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in c.fetchall()]
    
        if 'work_type' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN work_type TEXT DEFAULT 'regular'")
        
        if 'email' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
            
        if 'phone' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            
        if 'employee_number' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN employee_number TEXT")
            
        if 'insurance_number' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN insurance_number TEXT")
            
        # reservationsテーブルにgroup_idカラムがあるか確認し、なければ追加
        c.execute("PRAGMA table_info(reservations)")
        res_columns = [column[1] for column in c.fetchall()]
        
        if 'group_id' not in res_columns:
            c.execute("ALTER TABLE reservations ADD COLUMN group_id INTEGER")
    
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
            group_id INTEGER, -- グループ予約の場合のグループID
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (group_id) REFERENCES reservation_groups (id)
        )
    ''')
    
    # グループ予約テーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS reservation_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')
    
    # 健康診断結果テーブル
    c.execute('''
        CREATE TABLE IF NOT EXISTS exam_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_status TEXT DEFAULT 'pending', -- pending, reviewed
            reviewer_id TEXT,
            review_date TIMESTAMP,
            comments TEXT,
            FOREIGN KEY (reservation_id) REFERENCES reservations (id),
            FOREIGN KEY (reviewer_id) REFERENCES users (id)
        )
    ''')
    
    # Check which columns exist before inserting
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    
    # テストユーザーの追加（簡略化）
    users_data = [
        ('test', hash_password('test'), 'テストユーザー', '総務部', 'user', 'regular', 'test@example.com'),
        ('admin', hash_password('admin'), '管理者', '人事部', 'admin', 'regular', 'admin@example.com'),
        ('doctor', hash_password('doctor'), '産業医', '健康管理室', 'doctor', 'regular', 'doctor@example.com')
    ]
    
    # 利用可能なカラムに基づいて動的にSQLを構築
    has_work_type = 'work_type' in columns
    has_email = 'email' in columns
    
    fields = ['id', 'password', 'name', 'department', 'role']
    if has_work_type:
        fields.append('work_type')
    if has_email:
        fields.append('email')
    
    # フィールド名とプレースホルダーを構築
    fields_str = ', '.join(fields)
    placeholders = ', '.join(['?'] * len(fields))
    
    # ユーザーデータの挿入
    for user in users_data:
        # 利用可能なカラム数に基づいてデータを切り詰める
        user_data = user[:len(fields)]
        
        # 既存ユーザーのパスワードを更新しないように確認
        c.execute('SELECT id FROM users WHERE id = ?', (user_data[0],))
        if not c.fetchone():
            c.execute(f'INSERT INTO users ({fields_str}) VALUES ({placeholders})', user_data)
    
    db.commit()

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
                u.name,
                u.department
            FROM reservations r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.created_at DESC
        ''')
        return c.fetchall()
    except Exception as e:
        print(f"Error fetching reservations: {e}")
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

def get_all_exam_results():
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    try:
        c.execute('''
            SELECT 
                er.id,
                er.reservation_id,
                er.file_path,
                er.upload_date,
                er.review_status,
                u.name as user_name,
                u.department,
                r.exam_type,
                r.preferred_date
            FROM exam_results er
            JOIN reservations r ON er.reservation_id = r.id
            JOIN users u ON r.user_id = u.id
            ORDER BY er.upload_date DESC
        ''')
        results = c.fetchall()
        return results
    except Exception as e:
        print(f"Error fetching exam results: {e}")
        return []
    finally:
        conn.close()

def get_employee_reservation_status():
    """全社員の健診予約状況を取得する"""
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    try:
        # 全社員を取得
        c.execute('''
            SELECT 
                u.id,
                u.name,
                u.department,
                u.work_type,
                (
                    SELECT COUNT(*) 
                    FROM reservations r 
                    WHERE r.user_id = u.id AND r.status = 'approved'
                ) as has_approved,
                (
                    SELECT MAX(preferred_date) 
                    FROM reservations r 
                    WHERE r.user_id = u.id AND r.status = 'approved'
                ) as latest_exam_date,
                (
                    SELECT exam_type 
                    FROM reservations r 
                    WHERE r.user_id = u.id AND r.status = 'approved' 
                    ORDER BY preferred_date DESC LIMIT 1
                ) as latest_exam_type,
                u.employee_number,
                u.insurance_number
            FROM users u
            WHERE u.role != 'admin' AND u.role != 'doctor'
            ORDER BY u.department, u.name
        ''')
        employees = c.fetchall()
        
        # 部署ごとにグループ化（辞書内包表記を使用して簡略化）
        departments = {}
        for emp in employees:
            dept = emp[2] or '未所属'
            departments.setdefault(dept, []).append(emp)
        
        return departments
    except Exception as e:
        print(f"Error fetching employee reservation status: {e}")
        return {}
    finally:
        conn.close()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

login_manager = LoginManager()
login_manager.init_app(app)

# データベースの初期化はアプリケーションコンテキスト内で行う
with app.app_context():
    init_db()
login_manager.login_view = 'index'

class User(UserMixin):
    def __init__(self, id, name, department, role, work_type=None, email=None, phone=None):
        self.id = id
        self.name = name
        self.department = department
        self.role = role
        self.work_type = work_type
        self.email = email
        self.phone = phone
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_doctor(self):
        return self.role == 'doctor'
    
    def get_exam_type(self):
        """勤務形態に基づいて適切な健診種別を返す"""
        if self.work_type == 'night':
            return '特殊健康診断'
        return '定期健康診断'

def get_user_by_id(user_id):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('SELECT id, name, department, role, work_type, email, phone FROM users WHERE id = ?', (user_id,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2], user_data[3], 
                   user_data[4], user_data[5], user_data[6])
    return None

def verify_user(user_id, password):
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    try:
        # ユーザー情報を取得
        c.execute('SELECT id, name, department, role, work_type, email, phone, password FROM users WHERE id = ?', (user_id,))
        user_data = c.fetchone()
        
        if not user_data:
            return None
        
        stored_password = user_data[7]
        
        # パスワードの検証
        if stored_password.startswith(('pbkdf2:', 'scrypt:')):
            # ハッシュ化されたパスワードの検証
            if check_password_hash(stored_password, password):
                return User(user_data[0], user_data[1], user_data[2], user_data[3], 
                          user_data[4], user_data[5], user_data[6])
        else:
            # 移行期間中の平文パスワード検証（将来的に削除）
            if stored_password == password:
                return User(user_data[0], user_data[1], user_data[2], user_data[3], 
                          user_data[4], user_data[5], user_data[6])
        
        return None
    finally:
        conn.close()

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

# ルート定義
@app.route('/')
def index():
    print("=== DEBUG: Using template login.html ===")
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # テンプレートを使用する
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    employee_id = request.form.get('employee_id')
    password = request.form.get('password')
    
    user = verify_user(employee_id, password)
    if user:
        login_user(user)
        if user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    else:
        flash('ユーザーIDまたはパスワードが正しくありません', 'danger')
        return render_template('login.html')

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
    
    return render_template('dashboard.html', stats=stats, reservations=reservations)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    reservations = get_all_reservations()
    exam_results = get_all_exam_results()
    employee_status = get_employee_reservation_status()
    
    return render_template('admin_dashboard.html', reservations=reservations, 
                           exam_results=exam_results, employee_status=employee_status)

@app.route('/admin/approve/<int:reservation_id>')
@login_required
@admin_required
def approve_reservation(reservation_id):
    update_reservation_status(reservation_id, 'approved')
    flash('予約を承認しました。', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:reservation_id>')
@login_required
@admin_required
def reject_reservation(reservation_id):
    update_reservation_status(reservation_id, 'rejected')
    flash('予約を却下しました。', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/reservation')
@login_required
def reservation():
    # 部署リストの取得
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('SELECT DISTINCT department FROM users WHERE department IS NOT NULL')
    departments = [dept[0] for dept in c.fetchall()]
    conn.close()
    
    # 勤務形態に基づく推奨健診タイプ
    recommended_exam_type = current_user.get_exam_type()
    
    return render_template('reservation.html', 
                           departments=departments, 
                           recommended_exam_type=recommended_exam_type)

@app.route('/submit_reservation', methods=['POST'])
@login_required
def submit_reservation():
    exam_type = request.form.get('exam_type')
    preferred_date = request.form.get('preferred_date')
    preferred_time = request.form.get('preferred_time')
    notes = request.form.get('notes')
    is_group = request.form.get('is_group') == 'on'
    group_department = request.form.get('group_department')
    
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    
    group_id = None
    if is_group:
        c.execute('INSERT INTO reservation_groups (name, department, created_by) VALUES (?, ?, ?)',
                 (f"{group_department}健康診断予約", group_department, current_user.id))
        group_id = c.lastrowid
    
    c.execute('''
        INSERT INTO reservations 
        (user_id, exam_type, preferred_date, preferred_time, notes, group_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (current_user.id, exam_type, preferred_date, preferred_time, notes, group_id))
    
    conn.commit()
    conn.close()
    
    flash('予約申請が完了しました。承認をお待ちください。', 'success')
    return redirect(url_for('dashboard'))

@app.route('/upload_results')
@login_required
def upload_results():
    # 承認済み予約の取得
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        SELECT id, exam_type, preferred_date
        FROM reservations 
        WHERE user_id = ? AND status = 'approved'
        ORDER BY preferred_date DESC
    ''', (current_user.id,))
    approved_reservations = c.fetchall()
    conn.close()
    
    return render_template('upload_results.html', reservations=approved_reservations)

@app.route('/submit_results', methods=['POST'])
@login_required
def submit_results():
    reservation_id = request.form.get('reservation_id')
    if 'result_file' not in request.files:
        flash('ファイルが選択されていません', 'danger')
        return redirect(url_for('upload_results'))
    
    file = request.files['result_file']
    if file.filename == '':
        flash('ファイルが選択されていません', 'danger')
        return redirect(url_for('upload_results'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        save_filename = f"{current_user.id}_{timestamp}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, save_filename)
        file.save(filepath)
        
        conn = sqlite3.connect('health_check.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO exam_results 
            (reservation_id, file_path) 
            VALUES (?, ?)
        ''', (reservation_id, filepath))
        conn.commit()
        conn.close()
        
        flash('健康診断結果が正常にアップロードされました', 'success')
        return redirect(url_for('dashboard'))
    
    flash('許可されていないファイル形式です', 'danger')
    return redirect(url_for('upload_results'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    email = request.form.get('email')
    phone = request.form.get('phone')
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    
    # パスワード変更の場合
    if current_password and new_password:
        c.execute('SELECT password FROM users WHERE id = ?', (current_user.id,))
        stored_password = c.fetchone()[0]
        
        # パスワードハッシュの検証
        if not check_password_hash(stored_password, current_password):
            flash('現在のパスワードが正しくありません', 'danger')
            conn.close()
            return redirect(url_for('profile'))
        
        # 新しいパスワードのハッシュ化
        hashed_password = generate_password_hash(new_password)
        c.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, current_user.id))
        flash('パスワードが更新されました', 'success')
    
    # プロフィール情報の更新
    c.execute('UPDATE users SET email = ?, phone = ? WHERE id = ?', (email, phone, current_user.id))
    conn.commit()
    conn.close()
    
    flash('プロフィール情報が更新されました', 'success')
    return redirect(url_for('profile'))

@app.route('/admin/view_result/<int:result_id>')
@login_required
@admin_required
def view_result(result_id):
    """健康診断結果ファイルを表示する"""
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        SELECT file_path FROM exam_results WHERE id = ?
    ''', (result_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        flash('ファイルが見つかりません', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    file_path = result[0]
    if not os.path.exists(file_path):
        flash('ファイルが存在しません', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    return send_file(file_path, as_attachment=True)

@app.route('/admin/mark_reviewed/<int:result_id>')
@login_required
@admin_required
def mark_reviewed(result_id):
    """健康診断結果を確認済みにする"""
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    c.execute('''
        UPDATE exam_results 
        SET review_status = 'reviewed', 
            reviewer_id = ?, 
            review_date = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (current_user.id, result_id))
    conn.commit()
    conn.close()
    
    flash('健康診断結果を確認済みにしました', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/group_reservations')
@login_required
def group_reservations():
    # データベースの構造を確認
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    
    # 実際のグループ予約テーブル構造を確認
    c.execute("PRAGMA table_info(reservation_groups)")
    columns = [column[1] for column in c.fetchall()]
    
    # 予約テーブルの構造を確認
    c.execute("PRAGMA table_info(reservations)")
    res_columns = [column[1] for column in c.fetchall()]
    
    # データベース構造に基づいたダミーデータで表示
    sample_groups = []
    
    # 部署毎のグループ予約の例
    if current_user.department == '人事部':
        sample_groups = [
            (1, '総務部健康診断予約', '総務部', '2023-11-01 10:00:00', '管理者', 5),
            (2, '営業部健康診断予約', '営業部', '2023-11-05 14:30:00', '管理者', 8),
            (3, '開発部健康診断予約', '開発部', '2023-11-08 09:15:00', '管理者', 12)
        ]
    else:
        # 自部署のみ
        sample_groups = [
            (1, f'{current_user.department}健康診断予約', current_user.department, '2023-11-01 10:00:00', current_user.name, 3)
        ]
    
    conn.close()
    
    return render_template('group_reservations.html', group_reservations=sample_groups)

# アプリケーションをローカルホストで実行
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
