"""Generate Level 3 RAG test documents (PDF/TXT/Markdown) and evaluation dataset.

All content is fictional (company: 株式会社あおばソリューションズ, attendance system: AobaTime).
Uses ReportLab's built-in UnicodeCIDFont ('HeiseiKakuGo-W5') so Japanese PDFs generate
identically on macOS and Windows without OS-specific font paths.

Usage:
    cd Test-LiveKit
    uv run python scripts/generate_rag_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DOCS_DIR = BASE_DIR / "tests" / "fixtures" / "rag_documents"
EVAL_DIR = BASE_DIR / "tests" / "fixtures" / "rag_evaluation"
JP_FONT = "HeiseiKakuGo-W5"


def _register_japanese_font() -> None:
    if JP_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(JP_FONT))


def _write_japanese_pdf(path: Path, title: str, pages: list[list[tuple[str, str]]]) -> None:
    """Create a multi-page Japanese PDF with real extractable text."""
    _register_japanese_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "JPTitle",
        parent=styles["Title"],
        fontName=JP_FONT,
        fontSize=16,
        leading=22,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "JPHeading",
        parent=styles["Heading2"],
        fontName=JP_FONT,
        fontSize=12,
        leading=17,
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "JPBody",
        parent=styles["BodyText"],
        fontName=JP_FONT,
        fontSize=10,
        leading=16,
        spaceAfter=6,
    )

    story = [Paragraph(title, title_style), Spacer(1, 4 * mm)]
    for page_idx, sections in enumerate(pages):
        if page_idx > 0:
            story.append(PageBreak())
        for heading, body in sections:
            story.append(Paragraph(heading, heading_style))
            for para in body.strip().split("\n\n"):
                story.append(Paragraph(para.replace("\n", "<br/>"), body_style))
            story.append(Spacer(1, 2 * mm))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=title,
    )
    doc.build(story)


def generate_documents() -> list[Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # 1. company_rules.pdf (2 pages)
    company_rules_path = DOCS_DIR / "company_rules.pdf"
    _write_japanese_pdf(
        company_rules_path,
        "株式会社あおばソリューションズ 就業・勤怠規程（第4版）",
        [
            [
                (
                    "第1条 勤務開始時刻および終了時刻",
                    "標準勤務時間（定時）は、始業時刻を午前9時00分、終業時刻を午後6時00分とし、1日の所定労働時間は8時間とします。"
                    "全社共通のフレックスタイム制度を選択している部署では、コアタイムを午前10時30分から午後3時00分までと定め、"
                    "フレキシブルタイムは午前7時00分から午後10時00分までの範囲で勤務できます。\n\n"
                    "業務上の都合により始業時刻を繰り上げる必要がある場合は、前営業日の午後5時までに所属長へ事前相談してください。",
                ),
                (
                    "第2条 休憩時間の基準",
                    "標準勤務における休憩時間は、午後12時00分から午後1時00分までの60分間とします。"
                    "労働時間が6時間を超える場合は最低45分、8時間を超える場合は最低60分の休憩を必ず取得しなければなりません。"
                    "顧客対応などで正午に休憩を取れない場合は、午前11時00分から午後2時30分の間で連続60分の代替休憩を取得します。",
                ),
                (
                    "第3条 遅刻・早退のルール",
                    "電車遅延や体調不良などにより始業時刻に間に合わない場合は、始業時刻の午前9時00分までに所属長へチャットまたは電話で連絡し、"
                    "出社後に勤怠システムAobaTimeから遅刻届を提出してください。"
                    "公共交通機関の遅延による遅刻は、鉄道会社が発行する遅延証明書を添付することで勤怠評価上の減点対象から除外されます。\n\n"
                    "私用または体調不良による早退を行う場合は、退社前に所属長の口頭承認を得た上で、当日中に早退申請を登録してください。",
                ),
            ],
            [
                (
                    "第4条 年次有給休暇の申請ルール",
                    "入社日から6か月間継続勤務し、全労働日の8割以上出勤した社員に対して、初年度10日間の年次有給休暇を付与します。"
                    "年次有給休暇は1日単位のほか、午前半休（9時00分〜13時00分）または午後半休（14時00分〜18時00分）の半日単位でも取得可能です。\n\n"
                    "有給休暇の申請は、原則として取得希望日の3営業日前までにAobaTimeの休暇申請フォームから提出してください。"
                    "3日以上連続して有給休暇を取得する場合は、業務引き継ぎのため2週間前までに所属長へ申請する必要があります。"
                    "急な体調不良で当日に有給休暇へ振り替える場合は、当日の午前9時30分までに所属長へ連絡し、復帰後2営業日以内に事後申請を行ってください。",
                ),
                (
                    "第5条 時間外労働（残業）および休日出勤",
                    "所定労働時間を超えて時間外労働を行う場合は、原則として当日の午後5時00分までに残業事前申請を提出し、所属長の承認を得る必要があります。"
                    "月間の時間外労働の上限は原則45時間までとし、月30時間を超えた時点で人事部から所属長へアラート通知が送られます。"
                    "法定休日にやむを得ず出勤する場合は、事前の休日出勤申請を行い、原則として翌月末までに振替休日または代休を取得してください。",
                ),
            ],
        ],
    )
    created.append(company_rules_path)

    # 2. employee_manual.pdf (2 pages)
    employee_manual_path = DOCS_DIR / "employee_manual.pdf"
    _write_japanese_pdf(
        employee_manual_path,
        "AobaTime 社員向け勤怠操作マニュアル",
        [
            [
                (
                    "1. 出勤打刻の手順",
                    "業務を開始するタイミングで、AobaTimeのトップ画面に表示されている緑色の「出勤打刻」ボタンをクリックしてください。"
                    "オフィス出社の場合は勤務区分で「オフィス出社」を、在宅勤務の場合は「リモート勤務」を選択してから打刻します。"
                    "打刻が完了すると画面上部に「出勤打刻を受け付けました」と表示され、時刻がタイムカードへ即時記録されます。\n\n"
                    "オフィス入口のICカードリーダーに社員証をかざして打刻することも可能ですが、リモート勤務時は必ずWeb画面から打刻してください。",
                ),
                (
                    "2. 退勤打刻と休憩の記録",
                    "その日の業務をすべて終了したら、トップ画面のオレンジ色の「退勤打刻」ボタンを押して勤務を終了します。"
                    "標準の60分休憩を取得した場合は自動控除されるため個別操作は不要ですが、60分を超えて休憩を取った場合や中抜けが発生した場合は、"
                    "「休憩開始」「休憩終了」ボタンで実休憩時間を正確に記録してください。\n\n"
                    "退勤打刻後に業務を再開する必要が生じた場合は、二重打刻を行わず、翌営業日に勤怠修正申請で終了時刻を更新してください。",
                ),
            ],
            [
                (
                    "3. 打刻忘れの修正方法",
                    "出勤または退勤の打刻を忘れた場合は、左メニューの「勤怠修正申請」画面を開き、該当日の行にある「修正を申請」ボタンをクリックします。"
                    "実際の出社時刻・退社時刻を入力し、理由欄に「出勤打刻忘れのため」「外出直帰により退勤打刻漏れ」など具体的な理由を記入して送信してください。\n\n"
                    "打刻修正申請は直属の上長へ自動送信され、上長が承認すると勤怠実績へ反映されます。"
                    "打刻忘れの修正期限は、原則として発生日から5営業日以内、かつ月末締め日の前営業日までとなっています。",
                ),
                (
                    "4. 勤怠履歴と残業時間の確認",
                    "過去の勤務実績を確認したい場合は、左メニューの「月次勤怠一覧」をクリックします。"
                    "画面上部で対象年月を選択すると、日ごとの出勤時刻、退勤時刻、休憩時間、実働時間、残業時間、有給取得状況が一覧表示されます。\n\n"
                    "当月の累計残業時間や有給休暇の残日数は、画面右上のサマリーカードからいつでも確認できます。"
                    "直行または直帰を予定している日は、前日までに「直行直帰予定」フラグをオンにしておくと、上長が勤務状況を把握しやすくなります。",
                ),
            ],
        ],
    )
    created.append(employee_manual_path)

    # 3. faq.md
    faq_path = DOCS_DIR / "faq.md"
    faq_path.write_text(
        """# AobaTime 勤怠管理システム よくある質問（FAQ）

## Q1. ログインパスワードを忘れてしまいました。どうすればよいですか？
ログイン画面の下部にある「パスワードを再設定する」リンクをクリックし、会社のメールアドレス（`@aoba-solutions.example.jp`）を入力してください。
5分以内にパスワード再設定用のワンタイムURLが記載されたメールが届きます。URLの有効期限は30分間です。
メールが届かない場合は、迷惑メールフォルダを確認した上で、情報システム部ヘルプデスク（内線4100）へアカウントロック解除を依頼してください。
なお、パスワードを5回連続で誤入力するとセキュリティ保護のためアカウントが15分間自動ロックされます。

## Q2. 出勤・退勤ボタンを押しても打刻できません。対処法を教えてください。
打刻ボタンが反応しない場合は、以下の順番で切り分けを行ってください。
1. 社内VPNまたはインターネット接続が切れていないか確認し、ブラウザを再読み込み（F5またはCmd+R）してください。
2. 推奨ブラウザ（Google Chrome最新版またはMicrosoft Edge最新版）を使用しているか確認してください。SafariのプライベートブラウズではセッションCookieが保存されず打刻に失敗する場合があります。
3. ブラウザのキャッシュとCookieを削除して再ログインしてください。
4. それでも打刻できない場合は、画面に表示された時刻のスクリーンショットを撮り、チャットで上長へ出退勤時刻を連絡した上で、復旧後に「勤怠修正申請」から登録してください。

## Q3. 登録されている勤怠情報や残業時間が間違っています。どう修正すればよいですか？
当月分の勤怠データであれば、承認前（ステータスが「未提出」または「差し戻し」）の間は自分で「勤怠修正申請」から修正できます。
すでに上長の承認が完了している日のデータを訂正したい場合は、対象日の「承認取消依頼」ボタンを押し、上長に差し戻してもらってから再申請してください。
月末締め処理が完了して確定済みとなった前月以前の勤怠データに誤りを見つけた場合は、社員自身では変更できないため、人事部勤怠担当（`kintai-support@aoba-solutions.example.jp`）へ対象日・正しい時刻・理由を連絡してください。

## Q4. スマートフォンから打刻や休暇申請はできますか？
はい、社用スマートフォンまたはMDM登録済みの端末から、AobaTimeモバイルWeb画面にアクセスして出退勤打刻および休暇申請が行えます。
初回ログイン時には、認証アプリ（Authenticator）による6桁の二段階認証コードの入力が必要です。機種変更で認証アプリを移行できなかった場合は、情報システム部へ二段階認証のリセットを申請してください。

## Q5. 有給休暇の残日数が想定より少なく表示されています。
有給休暇の残日数には、すでに「承認済み」または「申請中」の未来日の休暇が仮控除として差し引かれて表示されます。
「休暇申請履歴」タブで申請中のレコードが残っていないか確認してください。取り消したはずの申請が反映されていない場合は、人事部へお問い合わせください。
""",
        encoding="utf-8",
    )
    created.append(faq_path)

    # 4. system_guide.txt
    system_guide_path = DOCS_DIR / "system_guide.txt"
    system_guide_path.write_text(
        """AobaTime 勤怠管理システム 操作・システム利用ガイド（Ver 3.2）

1. システムへのログイン方法
AobaTimeを利用するには、ブラウザで社内ポータル（https://portal.aoba-solutions.example.jp）を開き、メニューから「AobaTime 勤怠管理」をクリックします。
初回アクセス時は社員番号（例：EMP-00123）と初期パスワード、および認証アプリに表示される6桁の二段階認証コードを入力してログインしてください。
30分間操作がない場合は自動的にセッションがタイムアウトし、再ログイン画面へ遷移します。

2. 画面構成の概要
ログイン後に表示される画面は、大きく4つの領域で構成されています。
- 上部ヘッダー：現在時刻、ログイン中の社員名、通知ベルアイコン、ログアウトボタンが表示されます。
- 左サイドメニュー：「ホーム（打刻）」「月次勤怠一覧」「勤怠修正申請」「休暇・残業申請」「承認管理（管理者のみ）」「データ出力」の各機能へ移動できます。
- メインパネル：選択中の機能画面が表示されます。ホーム画面では大きな出勤打刻・退勤打刻ボタンと当日ステータスが中央に配置されています。
- 右サマリーバー：当月の出勤日数、累計残業時間、有給休暇残日数、未承認申請件数が一覧表示されます。

3. 基本操作とCSVエクスポート
月次勤怠一覧画面の右上にある「CSVダウンロード」ボタンをクリックすると、選択中の月の勤怠明細をUTF-8（BOM付き）のCSVファイルとして保存できます。
シフト勤務者やプロジェクト別工数を記録する部署では、「工数入力」タブから案件コードごとの稼働時間を0.25時間（15分）単位で登録します。
画面下部の「一時保存」ボタンは下書き保存のみを行うため、上長へ提出する際は必ず「申請を送信」ボタンを押してください。

4. エラー発生時の対応とエラーコード一覧
操作中にエラーメッセージが表示された場合は、表示されたエラーコードを控えて以下の対応を行ってください。
- エラーコード E-101（認証セッション期限切れ）：30分以上無操作だった場合に発生します。画面を再読み込みして再ログインしてください。
- エラーコード E-204（打刻時刻の重複）：すでに同一区分の打刻が登録されています。月次勤怠一覧で当日の打刻状況を確認してください。
- エラーコード E-310（申請期間外エラー）：締め処理が完了した月に対して申請を行おうとした場合に表示されます。人事部へ修正依頼を行ってください。
- エラーコード E-503（サーバーメンテナンス中）：毎月第3日曜日の午前2時00分から午前5時00分まで定期メンテナンスを実施しています。メンテナンス終了後に再度アクセスしてください。

システム障害が疑われる場合や、上記以外のエラーコードが表示された場合は、発生時刻・操作手順・エラーコードを添えて情報システム部（内線4100）へ連絡してください。
""",
        encoding="utf-8",
    )
    created.append(system_guide_path)

    # 5. business_procedures.pdf (2 pages)
    business_proc_path = DOCS_DIR / "business_procedures.pdf"
    _write_japanese_pdf(
        business_proc_path,
        "AobaTime 管理者・上長向け 勤怠承認・月末締め業務手順書",
        [
            [
                (
                    "第1章 日次の勤怠確認手順",
                    "部署の管理者および承認権限を持つ上長は、左メニューの「承認管理」から配下メンバーの日次勤怠状況を確認します。"
                    "「未打刻アラート」タブには、出勤予定時刻から2時間以上経過しても出勤打刻がない社員や、前日の退勤打刻が漏れている社員が赤字で一覧表示されます。\n\n"
                    "管理者は毎週月曜日の午前中に前週分の打刻漏れと残業実績を確認し、未処理の修正申請がある社員へリマインドを行ってください。",
                ),
                (
                    "第2章 承認フローと差し戻しルール",
                    "社員から提出された勤怠修正申請・休暇申請・残業申請は、一次承認者である直属のチームリーダーへ通知されます。"
                    "通常の打刻修正や2日以内の有給休暇は一次承認者の承認のみで確定します。"
                    "一方、3日以上の連続有給休暇、休日出勤申請、および月間残業30時間超過時の追加残業申請については、一次承認の後に部長による二次承認が必要です。\n\n"
                    "申請内容に不備がある場合（理由欄が空欄、遅延証明書の添付漏れ、実態と時刻が合わない等）は、"
                    "「差し戻し」ボタンを押し、修正が必要な点をコメント欄へ明記して申請者へ返却してください。"
                    "承認者が長期不在の場合は、事前に「代理承認者設定」から同一部署の別管理者を代理承認者に指定します。",
                ),
            ],
            [
                (
                    "第3章 月末締め処理のスケジュールと手順",
                    "株式会社あおばソリューションズの勤怠締め日は毎月末日です。"
                    "社員は翌月第1営業日の正午（午後12時00分）までに、当月分のすべての打刻漏れ修正・休暇申請を完了し、「月次勤怠提出」ボタンを押す必要があります。\n\n"
                    "部署管理者は翌月第2営業日の午後5時00分までに、配下全員の申請承認および月次勤怠の「部署締め確定」を完了させてください。"
                    "部署締め確定を行うと、該当部署の勤怠データはロックされ、人事部の給与計算システムへ連携可能な状態になります。\n\n"
                    "人事部は翌月第3営業日に全社分の締め状況を確認し、給与連携用CSVを出力して毎月の給与計算（毎月25日支給）へ引き継ぎます。",
                ),
                (
                    "第4章 管理者専用操作（ロック解除・権限管理）",
                    "部署締め確定後に重大な計算誤りや未申告の休暇が判明した場合、部署管理者単独ではロック解除できません。"
                    "管理者は「締め解除依頼」フォームから人事部へ申請し、人事部管理者が一時的に対象社員の月次ロックを解除した上で修正と再確定を行います。\n\n"
                    "新入社員の配属や部署異動に伴う承認ルートの変更は、人事部が毎月1日および16日にマスタ一括更新を行いますが、"
                    "期中の緊急変更が必要な場合は「権限変更チケット」を情報システム部へ起票してください。",
                ),
            ],
        ],
    )
    created.append(business_proc_path)

    return created


def generate_evaluation_dataset() -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    dataset = [
        # --- company_rules.pdf ---
        {
            "id": "q01",
            "query": "勤務開始時刻と終了時刻は何時ですか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 1,
            "expected_keywords": ["午前9時00分", "午後6時00分"],
        },
        {
            "id": "q02",
            "query": "フレックスタイム制度のコアタイムは何時から何時までですか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 1,
            "expected_keywords": ["午前10時30分", "午後3時00分"],
        },
        {
            "id": "q03",
            "query": "お昼休みは何分間ありますか？正午に取れないときはどうなりますか？",
            "category": "paraphrase",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 1,
            "expected_keywords": ["60分間", "代替休憩"],
        },
        {
            "id": "q04",
            "query": "電車が遅れて出社時間に間に合わない場合、減点されないようにするには何が必要ですか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 1,
            "expected_keywords": ["遅延証明書", "遅刻"],
        },
        {
            "id": "q05",
            "query": "有給休暇は何営業日前までに申請する必要がありますか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 2,
            "expected_keywords": ["3営業日前", "有給休暇"],
        },
        {
            "id": "q06",
            "query": "3日以上続けて有給を取る場合、いつまでに上長へ申請しますか？",
            "category": "paraphrase",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 2,
            "expected_keywords": ["2週間前", "連続"],
        },
        {
            "id": "q07",
            "query": "月の残業時間の上限は何時間ですか？人事部からアラートが出る基準も教えてください。",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "company_rules.pdf",
            "expected_page": 2,
            "expected_keywords": ["45時間", "30時間"],
        },
        # --- employee_manual.pdf ---
        {
            "id": "q08",
            "query": "在宅勤務のとき、出勤打刻はどの画面からどのように行いますか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "employee_manual.pdf",
            "expected_page": 1,
            "expected_keywords": ["リモート勤務", "出勤打刻"],
        },
        {
            "id": "q09",
            "query": "仕事が終わったあとの退勤打刻や中抜け休憩の記録方法を教えてください。",
            "category": "paraphrase",
            "answerable": True,
            "expected_document": "employee_manual.pdf",
            "expected_page": 1,
            "expected_keywords": ["退勤打刻", "休憩開始"],
        },
        {
            "id": "q10",
            "query": "出勤打刻を忘れた場合はどうすればいいですか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "employee_manual.pdf",
            "expected_page": 2,
            "expected_keywords": ["勤怠修正申請", "修正を申請"],
        },
        {
            "id": "q11",
            "query": "打刻漏れを直す申請には期限がありますか？何日以内に出せばよいですか？",
            "category": "paraphrase",
            "answerable": True,
            "expected_document": "employee_manual.pdf",
            "expected_page": 2,
            "expected_keywords": ["5営業日以内", "修正期限"],
        },
        {
            "id": "q12",
            "query": "過去の勤怠履歴や今月の累計残業時間はどこで確認できますか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "employee_manual.pdf",
            "expected_page": 2,
            "expected_keywords": ["月次勤怠一覧", "サマリーカード"],
        },
        # --- faq.md ---
        {
            "id": "q13",
            "query": "パスワードを忘れてログインできなくなりました。再設定の方法を教えてください。",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "faq.md",
            "expected_page": None,
            "expected_keywords": ["パスワードを再設定する", "30分間"],
        },
        {
            "id": "q14",
            "query": "パスワードを何回間違えるとアカウントがロックされますか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "faq.md",
            "expected_page": None,
            "expected_keywords": ["5回連続", "15分間"],
        },
        {
            "id": "q15",
            "query": "出勤ボタンを押しても打刻できないときの対処法は？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "faq.md",
            "expected_page": None,
            "expected_keywords": ["推奨ブラウザ", "キャッシュ"],
        },
        {
            "id": "q16",
            "query": "すでに上長に承認された日の勤怠情報が間違っていた場合、どうやって訂正しますか？",
            "category": "cross_document",
            "answerable": True,
            "expected_document": "faq.md",
            "expected_page": None,
            "expected_keywords": ["承認取消依頼", "差し戻し"],
        },
        {
            "id": "q17",
            "query": "スマートフォンから打刻や休暇の申請はできますか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "faq.md",
            "expected_page": None,
            "expected_keywords": ["モバイルWeb", "二段階認証"],
        },
        # --- system_guide.txt ---
        {
            "id": "q18",
            "query": "AobaTimeに初回ログインするときに必要な情報は何ですか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "system_guide.txt",
            "expected_page": None,
            "expected_keywords": ["社員番号", "二段階認証コード"],
        },
        {
            "id": "q19",
            "query": "操作しないで放置すると何分でタイムアウトしますか？",
            "category": "paraphrase",
            "answerable": True,
            "expected_document": "system_guide.txt",
            "expected_page": None,
            "expected_keywords": ["30分間", "タイムアウト"],
        },
        {
            "id": "q20",
            "query": "勤怠データをCSVファイルでダウンロードできますか？文字コードは何ですか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "system_guide.txt",
            "expected_page": None,
            "expected_keywords": ["CSVダウンロード", "UTF-8"],
        },
        {
            "id": "q21",
            "query": "エラーコード E-204 が表示された場合の原因と対応を教えてください。",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "system_guide.txt",
            "expected_page": None,
            "expected_keywords": ["E-204", "打刻時刻の重複"],
        },
        {
            "id": "q22",
            "query": "定期メンテナンスはいつ実施されますか？エラーコードE-503とは何ですか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "system_guide.txt",
            "expected_page": None,
            "expected_keywords": ["E-503", "第3日曜日"],
        },
        # --- business_procedures.pdf ---
        {
            "id": "q23",
            "query": "管理者が配下メンバーの打刻漏れを確認するにはどの画面を使いますか？",
            "category": "cross_document",
            "answerable": True,
            "expected_document": "business_procedures.pdf",
            "expected_page": 1,
            "expected_keywords": ["未打刻アラート", "承認管理"],
        },
        {
            "id": "q24",
            "query": "部長による二次承認が必要になる申請はどのような場合ですか？",
            "category": "natural_japanese",
            "answerable": True,
            "expected_document": "business_procedures.pdf",
            "expected_page": 1,
            "expected_keywords": ["二次承認", "部長"],
        },
        {
            "id": "q25",
            "query": "月末締め処理で社員と部署管理者の提出・確定期限はいつですか？",
            "category": "exact_match",
            "answerable": True,
            "expected_document": "business_procedures.pdf",
            "expected_page": 2,
            "expected_keywords": ["翌月第1営業日", "翌月第2営業日"],
        },
        {
            "id": "q26",
            "query": "部署締め確定のあとに誤りが見つかった場合、どうやってロックを解除しますか？",
            "category": "cross_document",
            "answerable": True,
            "expected_document": "business_procedures.pdf",
            "expected_page": 2,
            "expected_keywords": ["締め解除依頼", "人事部"],
        },
        # --- Unanswerable / Out-of-domain queries ---
        {
            "id": "q27",
            "query": "社員食堂の今週のランチメニューと食券の購入方法を教えてください。",
            "category": "unanswerable",
            "answerable": False,
            "expected_document": None,
            "expected_page": None,
            "expected_keywords": [],
        },
        {
            "id": "q28",
            "query": "海外出張時の航空券クラス規定と日当の金額を教えてください。",
            "category": "unanswerable",
            "answerable": False,
            "expected_document": None,
            "expected_page": None,
            "expected_keywords": [],
        },
    ]

    out_path = EVAL_DIR / "evaluation_dataset.json"
    out_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def verify_generated_pdfs(paths: list[Path]) -> None:
    for path in paths:
        if path.suffix.lower() != ".pdf":
            continue
        reader = PdfReader(str(path))
        assert len(reader.pages) >= 2, f"{path.name} must have >= 2 pages, got {len(reader.pages)}"
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            assert len(text) > 50, f"{path.name} page {i} extracted too little text ({len(text)} chars)"


def main() -> int:
    docs = generate_documents()
    verify_generated_pdfs(docs)
    eval_path = generate_evaluation_dataset()
    print(f"Generated {len(docs)} documents in {DOCS_DIR}")
    for p in docs:
        print(f"  - {p.name} ({p.stat().st_size} bytes)")
    print(f"Generated evaluation dataset: {eval_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
