# Voice Agent Lab ダッシュボードモック

`01_dashboard.png` と実装設計書 §4.2 を参照した初回レビュー用の画面です。表示値は `app/demo-data.ts` などの合成データです。画面上部のタブで各パネルを切り替えられます。期間と環境は固定です。

## ローカル起動

Node.js 22 以上と npm を使用します。環境変数や外部サービスの認証情報は不要です。

```sh
cd evaluation-web
npm ci
npm run dev
```

ブラウザーで http://localhost:3000 を開きます。

```sh
npm run build
npm run typecheck
```

通常セッションの安全性は「未実施」と表示します。独立した安全性テストは合否件数と内訳を表示します。サイドバーとクイックアクションは画面構成の確認用です。
