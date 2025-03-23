# 詳細セットアップガイド

このドキュメントでは、健康診断予約システムの詳細なセットアップ手順を説明します。

## 前提条件

- Python 3.8以上がインストールされていること
- pipがインストールされていること
- Gitがインストールされていること

## インストール手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/adawawsa/Columbia.git
cd Columbia
```

### 2. 仮想環境の作成（推奨）

```bash
# Windowsの場合
python -m venv venv
venv\Scripts\activate

# macOS/Linuxの場合
python3 -m venv venv
source venv/bin/activate
```

### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数の設定

`.env`ファイルをプロジェクトのルートディレクトリに作成し、以下の内容を設定します：

```
SECRET_KEY=your_secure_random_key_here
```

安全な鍵を生成するには、以下のPythonコードを実行できます：

```python
import os
import binascii
print(binascii.hexlify(os.urandom(24)).decode())
```

### 5. データベースの初期化

アプリケーションの初回起動時に自動的にデータベースが初期化されます。
手動で初期化するには、以下のコマンドを実行します：

```python
python
>>> from app import init_db
>>> init_db()
>>> exit()
```

### 6. アプリケーションの起動

```bash
python app.py
```

ブラウザで http://localhost:5000 にアクセスしてアプリケーションを使用開始できます。

## 開発環境の設定

### ログの設定

アプリケーションのログは`server.log`ファイルに記録されます。
ログレベルを変更するには、`app.py`の以下の行を修正します：

```python
# ログレベルの変更例
# DEBUG, INFO, WARNING, ERROR, CRITICALから選択
logging.basicConfig(level=logging.DEBUG, ...)
```

### テスト用アカウント

開発環境では、以下のテストアカウントが使用できます：

- 一般ユーザー: test / test
- 管理者: admin / admin
- 産業医: doctor / doctor

## 本番環境への展開

本番環境に展開する際は、以下の点に注意してください：

1. 適切な`SECRET_KEY`を設定する
2. デバッグモードを無効にする
3. 適切なセキュリティヘッダーを設定する
4. データベースのバックアップ計画を立てる

```python
# 本番環境設定の例
app.run(debug=False, host='0.0.0.0', port=5000)
```

## トラブルシューティング

一般的な問題と解決策：

1. **依存パッケージのインストールエラー**
   - Pythonバージョンが3.8以上であることを確認
   - pip自体を更新: `pip install --upgrade pip`

2. **データベース接続エラー**
   - ファイルパーミッションを確認
   - データベースファイルが破損していないか確認

3. **アプリケーション起動エラー**
   - ポート5000が他のアプリケーションで使用されていないか確認
   - 必要なパッケージがすべてインストールされているか確認
