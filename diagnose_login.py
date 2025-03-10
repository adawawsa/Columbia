import sqlite3
from werkzeug.security import check_password_hash

def test_login(user_id, password):
    """指定されたユーザーIDとパスワードでログインをテストする"""
    conn = sqlite3.connect('health_check.db')
    c = conn.cursor()
    
    # ユーザー情報を取得
    c.execute('SELECT id, password FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    
    if not user:
        print(f"ユーザーID '{user_id}' は存在しません")
        return False
    
    stored_hash = user[1]
    print(f"保存されたハッシュ: {stored_hash}")
    
    # ハッシュ値かどうかを確認
    is_hash = stored_hash.startswith('pbkdf2:') or stored_hash.startswith('scrypt:')
    print(f"ハッシュ値として認識: {is_hash}")
    
    if is_hash:
        result = check_password_hash(stored_hash, password)
        print(f"パスワード検証結果: {result}")
        return result
    else:
        # 平文で保存されている場合
        result = (stored_hash == password)
        print(f"平文での比較結果: {result}")
        return result

# テスト実行
for test_user in [('test', 'test'), ('admin', 'admin'), ('doctor', 'doctor')]:
    user_id, password = test_user
    print(f"\n--- ユーザー '{user_id}' でのログインテスト ---")
    result = test_login(user_id, password)
    print(f"ログイン成功: {result}")
