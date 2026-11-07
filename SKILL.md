---
name: inventory-harness
description: 棚卸し〜リファクタリング実施を、観点×対象のマトリクスで漏れなく回すためのハーネスの指揮役。手順の実体は tools/ の各 tool（コード）にあり、本書は判断の要点と tool の実行順だけを持つ。
---

# 棚卸しハーネス（指揮役）

対象範囲・段階・完了条件はすべてコード（`tools/` と `config.json`）で定義する。
本書に手順の実体を長く書かない。新しい観点は `config.json` の
`viewpoints` に追加する（コード変更不要）。対象はミラー配下のリポジトリと
custom-skills が自動列挙され、除外は config の `exclude` のみで行う。

## tool の実行順（各 tool は独立実行可能、連携はファイル経由のみ）

1. `discover_targets` — 対象の自動列挙を確認
2. `build_matrix` — ランを作り、観点×対象の全セルを生成
3. セルごとに調査し、候補があれば `add_candidate`、終わったら `mark_cell`
4. 候補の段階は `advance_candidate` で進める
   （found → characterized → in_progress → reviewed → scanned → pushed
   → reported。判断待ちは decision_pending、仕様判断に回すものは
   rejected_as_spec）
5. `run_status` — 未消化セルと段階別候補数を確認
6. `close_run` — 全セル消化の時だけ閉じられる。未消化が残れば拒否される

## 月次点検のランを回す流れ

1. `build_matrix` で当月ランを生成し、`run_status` で未消化セルの全体像を掴む。
2. 未消化セルを1つずつ調査する。前回ランの候補・状態は state に残っている
   ので、中断しても `run_status` から再開できる。
3. 候補は見つけた時点で `add_candidate` し、セルは調査が終わるまで
   pending のままにしない／したまま完了報告しない。
4. 実施は別プログラム（役割分離：特性テスト先行→実装→独立検閲→push前
   検閲）が担い、進捗は `advance_candidate` でハーネスに反映する。
5. 全セルが消化されたら `close_run` で閉じ、初めて「完了」と報告できる。

## 判断の要点

- **未消化セルが残るランは完了ではない。** close_run が拒否するのが正で、
  迂回して完了扱いにしない。
- **dead-config は検出まで**。消す／効かせるは仕様判断なので、候補を
  rejected_as_spec にして別件として本人に上げる。
- 候補の実施可否・優先度は本人の承認事項。ハーネスは状態管理だけを行う。
- 仕様とのズレをリファクタリングに混ぜない。見つけたら別件化する。
