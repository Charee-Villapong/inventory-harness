# 実行チームと管理チーム（二段構成）

ハーネスは二段のチームで回す。

| チーム | 役割 | 担うこと |
|---|---|---|
| 管理チーム | 取りまとめ（coordinator）／検閲係（reviewer）＋ハーネスの機械的ゲート | ちゃんとやったかを管理する。進行・集計・報告、質の独立検閲、マトリクス消化・段階遷移・証跡必須・完了ゲートによる機械的な担保 |
| 実行チーム | 調査係（scout）／テスト係（test-author）／実装係（implementer）／実働テスト係（live-tester） | やることを実行する。調査、特性テスト、実装、実働確認 |

接点は **証跡必須の段階遷移**。実行チームの成果は、証跡（検閲結果・
検閲実施記録・コミットハッシュ・報告先への参照）として管理チームが
受け取り、候補の履歴に残る。証跡のない遷移はコードが拒否する。

係の編成は、この `team/` の定義から行う。チャット側の文章でその都度
場当たりに編成しない。

- 管理チーム: [coordinator](coordinator.md) / [reviewer](reviewer.md)
- 実行チーム: [scout](scout.md) / [test-author](test-author.md) /
  [implementer](implementer.md) / [live-tester](live-tester.md)
