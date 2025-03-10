import sqlite3
from werkzeug.security import generate_password_hash

# データベース接続
conn = sqlite3.connect('health_check.db')
c = conn.cursor()

# 既存のユーザーとパスワードを取得
c.execute('SELECT id, password FROM users')
users = c.fetchall()

# 各ユーザーのパスワードをハッシュ化して更新
for user_id, password in users:
    hashed_password = generate_password_hash(password)
    c.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))
    print(f"ユーザー {user_id} のパスワードをハッシュ化しました")

# 変更を保存
conn.commit()
conn.close()

print("すべてのパスワードが更新されました。")
