# IncAgent Security Roadmap

## v0.5.0 — 実装済み (Current)

### API認証 & アクセス制御 ✅
- **API Key認証**: Bearer token方式。HMAC-SHA256でキーをハッシュ化して保存（平文保存しない）
- **レート制限**: トークンバケット方式。IP単位で毎分60リクエスト、バースト10
- **CORS制限**: デフォルトで全オリジン拒否（明示指定のみ許可）
- **エンドポイント権限**: `/health`, `/identity` のみ公開。他は認証必須
- **ツール実行制御**: `shell_exec` はAPI経由でデフォルト拒否。allowlist/denylist設定可
- **ツール作成/自己改善**: API経由はデフォルト無効（明示的に有効化が必要）

### コード実行サンドボックス ✅
- **CodeSandbox**: LLM生成コード・カスタムツールを実行前に静的解析
- **ブロック対象**:
  - `subprocess`, `os.system`, `eval`, `exec`, `compile`, `__import__`
  - `socket`, `requests`, `urllib` (ネットワーク直接操作)
  - `pickle`, `marshal`, `shelve` (デシリアライゼーション攻撃)
  - `shutil.rmtree`, `os.remove` (ファイル削除)
  - `open(..., "w")` (任意ファイル書き込み)
- **BaseTool継承必須**: クラス定義なしのコードは拒否
- **サイズ制限**: 50KB超のコードは拒否
- **防御の多層化**: Gateway → ToolRegistry → CodeSandbox の3段階チェック

### シェルコマンド防御 ✅
- **40+パターンのブロックリスト**:
  - 破壊: `rm -rf /`, `mkfs`, `dd if=`
  - 逆シェル: `/dev/tcp/`, `bash -i >&`, `nc -e`
  - データ窃取: `.ssh/`, `.env`, `.aws/credentials`, `/etc/shadow`
  - 権限昇格: `sudo`, `su -`, `chown root`
  - クリプトマイニング: `xmrig`, `minerd`
  - システム改変: `systemctl`, `crontab`
- **Strictモード**: 環境変数 `INCAGENT_SHELL_STRICT=true` でコマンドホワイトリスト強制
- **パイプ先チェック**: `| bash`, `| python` 等のインタプリタへのパイプを検出

### Skill/Tool注入防御 ✅
- **スキル名サニタイズ**: 英数字・アンダースコア・ハイフンのみ許可
- **コンテンツ検証**: パストラバーサル・XSS・コマンドインジェクション検出
- **サイズ制限**: スキルファイル100KB上限
- **カスタムツール読み込み時検証**: ディスクからのロード時もCodeSandbox通過必須

### HMAC署名 & リプレイ防御 ✅
- **リクエスト署名**: HMAC-SHA256 + タイムスタンプ
- **タイムスタンプ鮮度チェック**: デフォルト300秒以内のリクエストのみ受付
- **エージェント間メッセージ署名**: ペイロード改ざん検出

### 監査ログ ✅
- **AuditLogger**: SQLite追記専用ログ
- **チェーンハッシュ**: SHA-256で各エントリをチェーン化（改ざん検出可能）
- **改ざん検証**: `verify_chain()` でチェーン全体の整合性チェック
- **記録対象**: 認証失敗、レート制限、ツール実行、ツール作成拒否、取引提案、紛争申請
- **APIエンドポイント**: `GET /audit` で監査ログ閲覧可能

### 入力バリデーション ✅
- **JSONボディ**: ネスト深度制限（5階層）、サイズ制限（1MB）
- **名前フィールド**: 英数字のみ、64文字以内
- **全POSTエンドポイント**: InputValidator通過必須

---

## v0.6.0 — 実装済み (Current)

### EIP-1559ガス管理 ✅
- **動的ガス推定**: `maxFeePerGas = 2 * baseFee + maxPriorityFee`
- **RBF (Replace-By-Fee)**: 10%ガスアップで再送信
- **RPCフェイルオーバー**: 複数RPCエンドポイント対応、自動再接続
- **ノンス管理**: `threading.Lock`でスレッドセーフ
- **残高チェック**: 送金前にUSDC残高確認、不足時fail-fast

### 税務トラッキング ✅
- **TaxTracker**: SQLiteベースのUSDC取引記録
- **レコードタイプ**: income, expense, escrow_in, escrow_out, refund
- **1099-NEC検出**: ベンダー毎$600/年の閾値監視
- **年次サマリ**: 総収入、総支出、純額、ベンダー数、1099対象数
- **エクスポート**: JSON/CSV形式
- **APIエンドポイント**: `GET /tax?year=2026`

### Prometheusメトリクス ✅
- **純Python実装**: 外部依存なし
- **カウンター**: trades, payments, negotiations, tools, api_requests, auth_failures, disputes
- **ゲージ**: agent_state, active_settlements, known_peers, usdc_balance, circuit_breaker
- **ヒストグラム**: negotiation_rounds, negotiation_duration, payment_amount
- **エンドポイント**: `GET /metrics`（公開、認証不要）

---

## v0.7.0 — 実装済み (Current)

### Solidityエスクロー ✅
- **IncAgentEscrow.sol**: Base/Arbitrum/Ethereum/Polygon対応のUSDCエスクローコントラクト
- **deposit()**: バイヤーがUSDCをロック（IERC20 safeTransferFrom）
- **release()**: デリバリー検証後、バイヤーが資金解放 → セラーへ
- **refund()**: デッドライン超過時、バイヤーが返金請求
- **dispute()**: いずれかの当事者が紛争申請 → アービター解決待ち
- **resolveDispute(buyerPct)**: アービターが0-100%で分配
- **タイムロック**: MIN 1時間 ~ MAX 90日
- **ReentrancyGuard**: リエントランシー攻撃防御
- **SafeERC20**: トークン転送の安全ラッパー
- **Python連携**: `PaymentExecutor.escrow_deposit/release/refund/dispute/status`
- **Settlement連携**: `SettlementMode.ESCROW` でオンチェーンエスクロー自動使用

### HTTPS/TLS ✅
- **TLS 1.3必須**: `TLSConfig(enabled=True)` でHTTPS有効化
- **自動証明書生成**: `auto_generate=True` でEC P-256自己署名証明書を自動作成
- **HTTP→HTTPSリダイレクト**: `redirect_http=True` で8080→8400リダイレクト
- **mTLS対応**: `ca_file` でCA証明書指定 → 相互TLS認証
- **最小バージョン設定**: `min_version="TLSv1.3"` or `"TLSv1.2"`
- **証明書保管**: `{org_dir}/tls/cert.pem`, `key.pem`（パーミッション0600）

---

## v0.8.0 — 次期実装予定

### Tier 1: 必須（米国法人運用に不可欠）

| 項目 | 内容 | 優先度 |
|------|------|--------|
| **KYC/AML統合** | Jumio or Stripe Identity + OFACスクリーニング | P0 |
| **マルチシグウォレット** | 2-of-3最低。Safe (Gnosis Safe) or Fireblocks統合 | P0 |
| **秘密鍵管理** | HashiCorp Vault or AWS Secrets Manager連携 | P0 |
| **Money Transmitter評価** | 弁護士レビュー（各州ライセンス要件の確認） | P0 |

### Tier 2: コンプライアンス

| 項目 | 内容 | 優先度 |
|------|------|--------|
| **不変監査ログ** | SQLite→PostgreSQL移行 or ブロックチェーンアンカリング | P1 |
| **データ暗号化** | DB暗号化（SQLCipher or PostgreSQL pgcrypto） | P2 |
| **データ保持ポリシー** | 自動アーカイブ・削除ルール | P2 |

### Tier 3: 運用品質

| 項目 | 内容 | 優先度 |
|------|------|--------|
| **Grafanaダッシュボード** | Prometheusメトリクスとの連携、アラート閾値 | P2 |
| **DR/バックアップ** | DB複製、鍵バックアップ（暗号化してKMSへ） | P2 |
| **配送トラッキング** | Shippo API統合、GPS検証 | P3 |
| **WAF/DDoS防御** | Cloudflare or AWS WAF | P2 |
| **ログ集約** | SIEM連携（Datadog, Splunk等） | P3 |

---

## セキュリティ設定例

### 最小構成（開発用）
```python
agent = IncAgent(
    name="Dev Agent",
    role="buyer",
    security={
        "require_auth": False,  # 開発時のみ
    },
)
```

### 推奨構成（本番用）
```python
agent = IncAgent(
    name="Acme Corp",
    role="buyer",
    security={
        "api_keys": ["inc_your_secret_key_here"],
        "require_auth": True,
        "allowed_origins": ["https://your-dashboard.com"],
        "rate_limit_per_minute": 30,
        "tool_denylist": ["shell_exec"],
        "allow_tool_creation_via_api": False,
        "allow_self_improve_via_api": False,
    },
)
```

### 環境変数
```bash
# API key（設定ファイルの代わりに環境変数でも指定可能）
INCAGENT_API_KEY=inc_your_secret_key

# シェルツール厳格モード（コマンドホワイトリスト強制）
INCAGENT_SHELL_STRICT=true

# データディレクトリ（ファイルツールのアクセス範囲）
INCAGENT_DATA_DIR=/path/to/agent/data
```

---

## テストカバレッジ

| テストファイル | テスト数 | カバー範囲 |
|---------------|---------|-----------|
| test_security.py | 50 | API Key, HMAC, Rate Limit, Input Validation, CodeSandbox, Shell Validation, Audit Logger, Peer Signing, Config Defaults |
| test_escrow.py | 15 | ABI, エスクローID生成, deposit/release/refund/dispute/status, Settlement連携 |
| test_payment.py | 15 | PaymentConfig, RPC failover, balance check, EIP-1559, ERC20 ABI |
| test_tls.py | 10 | TLSConfig, SSL Context, 自動証明書生成, リダイレクトアプリ |
| test_tax.py | 14 | 税務記録、1099-NEC、エクスポート |
| test_metrics.py | 14 | Counter, Gauge, Histogram, Registry |
| 全テスト | 258 | v0.7.0全機能 + 既存回帰テスト |

---

## 既知のリスクと緩和策

| リスク | 現状 | 緩和策 |
|--------|------|--------|
| LLMプロンプトインジェクション | CodeSandboxで静的解析 | v0.8でAST解析追加予定 |
| SQLiteファイル直接編集 | チェーンハッシュで改ざん検出 | v0.8でPostgreSQL移行 |
| 秘密鍵の環境変数管理 | 平文 | v0.8でVault連携 |
| 単一RPCプロバイダ | v0.6で複数RPC対応 ✅ | 解決済み |
| HTTP通信 | v0.7でTLS 1.3対応 ✅ | 解決済み |
| トラストベースのエスクロー | v0.7でSolidityコントラクト ✅ | 解決済み |
