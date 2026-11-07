# inventory-harness

「棚卸し〜リファクタリング実施」の漏れを二度と起こさないための実行基盤
（ハーネス）。対象範囲・段階・完了条件を自然言語の手順書ではなくコードで
定義し、「観点 × 対象」の全セルを消化しないとランを完了にできない担保を
コードで持つ。

発端：2026-11-07 のリファクタリング候補洗い出しで、md整理（SKILL.md
肥大化）が別観点だったため実施範囲から漏れかけた。

## 構成（疎結合な段階別 tool ＋ 指揮役 skill）

```
config.json            観点レジストリ・対象設定・除外リスト
SKILL.md               指揮役（判断の要点と tool の実行順のみ）
team/                  実行チームと管理チームの役割定義（正本）
tools/
  common.py            共有の中核（設定読込・対象列挙・状態保存・状態機械）
  discover_targets.py  段階1: 対象の自動列挙
  build_matrix.py      段階2: ラン生成とマトリクス作成
  add_candidate.py     段階3: 候補登録
  mark_cell.py         段階4: セルの消化記録
  advance_candidate.py 段階5: 候補の段階遷移
  run_status.py        段階6: 状態集計（未消化セル・段階別件数）
  close_run.py         段階7: 完了チェック付きクローズ
  run_repo_tests.py    独立tool: 対象リポジトリの pytest 実行と件数集計（JSON出力）
  pre_push_scan.py     独立tool: 追跡ファイルの個人情報・接続情報・認証情報の混入走査（JSON出力）
state/runs/<run_id>.json  ランの状態（永続化、.gitignore 対象）
tests/                 pytest
```

各 tool は個別に実行・テストでき、連携は config と state のファイル形式
のみ。tool 同士は呼び合わない。

## 使い方

前提：`python3 -m venv .venv && .venv/bin/pip install pytest black isort`
（実行自体は標準ライブラリのみで動く）

```bash
# 対象の確認
.venv/bin/python -m tools.discover_targets

# ラン生成（観点×対象の全セルが pending で作られる）
.venv/bin/python -m tools.build_matrix --run-id monthly-20261201

# 候補登録とセルの消化記録
.venv/bin/python -m tools.add_candidate monthly-20261201 refactoring skills --title "重複処理の共通化"
.venv/bin/python -m tools.mark_cell monthly-20261201 refactoring skills --result candidates
.venv/bin/python -m tools.mark_cell monthly-20261201 refactoring fortune --result none

# 候補の段階遷移（証跡必須の遷移は --evidence が要る）
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to characterized
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to in_progress
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to reviewed --evidence "review: <検閲結果への参照>"
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to scanned --evidence "scan: <検閲実施記録への参照>"
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to pushed --evidence <コミットハッシュ>
.venv/bin/python -m tools.advance_candidate monthly-20261201 C-001 --to reported --evidence "report: <報告先への参照>"

# 状態集計と完了チェック
.venv/bin/python -m tools.run_status monthly-20261201
.venv/bin/python -m tools.close_run monthly-20261201   # 未消化があれば exit 1 で拒否
```

各 tool は `--config` / `--state-dir` で設定と状態の置き場所を変更できる。

独立 tool 2 本（段階 tool と違い、他 tool を呼ばず引数と JSON 出力だけで連携する）:

```bash
# 対象リポジトリのテスト実行と件数集計（--cmd でコマンド上書き、--out で JSON 書出）
.venv/bin/python -m tools.run_repo_tests ~/workspace/github-mirrors/<repo>

# 追跡ファイルの混入走査。ヒット文字列自体は出力せず、種別と場所だけを返す
# ローカルパターンは scan-patterns.local.json（.gitignore 対象）があれば併用する
.venv/bin/python -m tools.pre_push_scan ~/workspace/github-mirrors/<repo>
```

## 観点（config.json で追加・無効化可能）

| id | 内容 |
|---|---|
| refactoring | コードの重複・肥大化・直書き値 |
| test-thinness | テスト薄弱箇所と現状固定テストの要否 |
| skill-md-bloat | SKILL.md の肥大化（残骸・重複チェック・起きない分岐） |
| md-redundancy | md 全般の冗長・不要文言・重複定義 |
| dead-config | 死んでいる config キー・効かない設定（処遇は別件） |

対象は `~/workspace/github-mirrors/` 配下の全 git リポジトリと
`~/workspace/custom-skills/`。除外は config の `exclude` のみ
（初期除外：deadline-ledger＝廃止・削除待ち）。新リポジトリは次回列挙で
自動的に入る。

## 候補の状態機械

```
found -> characterized -> in_progress -> reviewed -> scanned -> pushed -> reported
  └─ どの段階からでも decision_pending（判断待ち。元の状態へ復帰可）
  └─ どの段階からでも rejected_as_spec（仕様判断として別件化・終端）
```

### 証跡必須の遷移（仕様変更）

実行チームの成果を管理チームが受け取る接点として、次の遷移では
証跡（成果物への参照）が必須になった。証跡は候補の履歴に
`{"kind": ..., "ref": ...}` として残る。空・空白のみは拒否される。

| 遷移先 | 必須の証跡 | kind |
|---|---|---|
| reviewed | 検閲係の検閲結果への参照 | review |
| scanned | push 前検閲の実施記録への参照 | scan |
| pushed | コミットハッシュ（7〜40桁の hex、形式チェックあり） | commit |
| reported | 報告先への参照 | report |

それ以外の遷移でも `--evidence` で任意の参照を残せる（kind は note）。

後方互換：証跡は履歴への追加のみで、旧形式の state（履歴に証跡を
持たない候補）はそのまま読み込め、移行は不要。新コードで旧 state の
候補を通常どおり遷移できることを確認済み。

## チーム構成（二段）

- 管理チーム（ちゃんとやったかを管理する）：取りまとめ・検閲係＋
  ハーネスの機械的ゲート（マトリクス消化・段階遷移・証跡必須・
  完了ゲート）
- 実行チーム（やることを実行する）：調査係・テスト係・実装係・
  実働テスト係

役割定義は `team/` が正本。係の編成はこの定義から行う。

## 現在の状態

2026-11-07 の候補リスト（68件）を取り込んだラン `monthly-20261107` が
state にある。全候補は found から開始（取り込み時点で完了報告が届いて
いなかったため）。未消化セル24件は、前回洗い出しで md 系・dead-config の
調査が及ばなかった範囲をそのまま表している。

## 開発

```bash
.venv/bin/python -m pytest        # テスト
.venv/bin/python -m black tools tests
.venv/bin/python -m isort tools tests
```
