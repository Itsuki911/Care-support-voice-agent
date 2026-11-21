# Repository Agent Guidelines

本ファイルは、このリポジトリで作業するすべての Coding Agent に共通して適用されるルールです。

## 1. ポートフォリオ資料の継続更新ルール（必須）
機能追加、バグ修正、設計変更、モデル変更、または重要な検証・改善を行った際は、実装完了時（またはコミット前）に以下のドキュメントを最新の状態へ更新すること。

- **技術解説・開発履歴**: `portfolio/portfolio-overview.md`
  - 新しい実装内容（アーキテクチャ・設計判断）
  - 開発履歴テーブルへのマイルストーン／コミット追記
  - Langfuse 解析やテストから判明した課題・修正・検証結果の追記
  - 最終更新日・基準コミットの更新
- **専門用語集**: `portfolio/glossary.md`
  - 新しい技術・ライブラリ・設計概念・監視指標を導入した場合は、新人エンジニアにも分かる形式で「一言で／詳しい解説／このシステムでの使われ方」を追記する。
- **対象範囲の注意**: 現段階では実装・検証済みの機能を中心に記載し、未着手の将来計画（`development plan/roadmap.md` の Level 3B Web 検索・GCP 移行、Level 4 ストリーミング表示等）は実装するまで「今後の展望」にとどめる。

## 2. コミュニケーション・ドキュメント方針
- ユーザーへの説明・コメント・新規ドキュメントは原則 **日本語** で簡潔に記述する。
- 新規に作成したコード・設計変更の内容は、推測ではなく実際に確認したファイル・コマンド結果に基づいて説明する。

## 3. セキュリティ・機密情報の取り扱い
- `.env`、`Test-LiveKit/.secrets/*`、OAuth クライアント／トークン JSON、API キーを Git にコミットしない・出力に露出しない。
- `LANGFUSE_ALLOW_PII` は既定 `false`（`redacted`）を維持し、会話本文やメール本文を外部トレースへ出力しない。
- 外部サービス操作（Gmail の検索・読み取り・送信等）は、必ずバックエンドの承認フロー（`Test-LiveKit/approvals.py`）を経由する設計を維持する。

## 4. 開発・テスト・環境固有のルール
- **Windows + PostgreSQL (`psycopg` 3)**: `Test-LiveKit/agent.py` における `WindowsSelectorEventLoopPolicy()` の設定および `psycopg.types.net` の事前インポートを維持し、イベントループのブロッキングや `ProactorEventLoop` 非互換を再発させない。
- **依存関係・実行コマンド**:
  - Python (`Test-LiveKit/`): `uv` を使用する（例: `uv --directory Test-LiveKit run pytest -q`）。
  - Frontend (`fronted-test/`): `npm run build` / `npm test` で型・ビルドを確認する。
- **変更後の検証**: 変更箇所に関連するテスト（`test_observability.py`, `test_trace_integration.py`, `test_approvals.py`, `test_memory_tools.py` 等）を実行してから完了報告する。
