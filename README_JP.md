<p align="center">
  <img src="assets/banner.png" alt="ai_crypto_agent_banner" width="800" />
</p>

<p align="center">
  <a href="README_CN.md"><img src="https://img.shields.io/badge/简体中文-red?style=for-the-badge" alt="简体中文" /></a>
  <a href="README.md"><img src="https://img.shields.io/badge/English-blue?style=for-the-badge" alt="English" /></a>
  <a href="README_JP.md"><img src="https://img.shields.io/badge/日本語-green?style=for-the-badge" alt="日本語" /></a>
</p>

# 🐋 AI クジラ監視 & 量化取引ターミナル (Dolores V2.0)

**本プロジェクトは、<font color="red">無料のオンチェーンリソース</font>を活用し、4時間足をベースとした分析を行う、<font color="red">超低コストな AI トレンド量化取引</font>および<font color="red">オンチェーンデータ監視</font>ターミナルです。24時間365日、人間の介入なしに市場を判断し、OKX の実盤またはペーパートレードで自動取引を実行します。**

📺 **デモサイト:** [https://whale.sparkvalues.com/](https://whale.sparkvalues.com/)

# ⭐ 機能リスト

> ⚠️ **免責事項**：本プロジェクトは学習および研究を目的としており、いかなる投資アドバイスも構成しません。

| モジュール | 実装状況 |
| :--- | :--- |
| **クジラ監視 (Whale Hub)** | ✅ ETH/SOL チェーン上の大口送金をリアルタイム監視<br>✅ 多次元データの統合 (DefiLlama, Moralis, Etherscan)<br>✅ 24h/7d ステーブルコイン & トークンの純流出入分析<br>✅ クジラの「蓄積」と「分配」のダイバージェンス信号を正確に特定<br>✅ グローバル時価総額比率と流動性の変化を動的に追跡 |
| **AI 取引システム (Dolores)** | ✅ DeepSeek-V3 を脳とした4時間周期の自動意思決定<br>✅ **Qlib 相対強弱モデル**: 複数通貨のスコアリングとランクに基づくウェイト推奨<br>✅ **ナラティブ vs リアリティ・チェック**: ニュース主導か織り込み済みかのトラップを識別<br>✅ **戦術的規律 (4D Rules)**: 流動性ラッシュの回避とファンディング・トラップへの強制防御信号<br>✅ シャドーモード (模擬) と実盤の切り替え / OCO 指値・逆指値対応 |
| **マクロ・流動性・オンチェーン** | ✅ **Z-Score 異常検知**: 出来高と資金調達率の統計的な極端な乖離を監視<br>✅ **クジラ・フロー**: $ETH/$SOL の7日間/24時間の純流入を深く統合<br>✅ **ヒゲ感知 (Wick Ratio)**: 長い下ヒゲ/上ヒゲなどの反転シグナルを自動識別<br>✅ FRB金利予測、円キャリートレードリスク、DXY/VIX/恐怖強欲指数の統合 |
| **システム統合 & 自動化** | ✅ MongoDB によるミリ秒単位の状態同期と GitHub リアルタイムデータ永続化<br>✅ Telegram & Discord によるリアルタイム取引速報<br>✅ フロントエンドとバックエンドの完全デカップリング (React + Flask)<br>✅ K線確定に合わせた自動 Run Loop スケジューリング |

---

本システムは、Python バックエンド・スケジューリングエンジンと、優れた多次元データ視覚化を備えた React/Next.js Web3 フロントエンドダッシュボードで構成されています。
![whale.sparkvalues.com](image.png)
AI モデルによる取引根拠と収益曲線
![alt text](image-2.png)
![alt text](image-5.png)
![alt text](image-4.png)
4時間周期の Telegram 通知
![alt text](image-1.png)
4時間周期の Discord 通知
![alt text](image-6.png)

---

# 🌟 主要機能

### 1. エージェント型 AI トレーダー (Agentic AI Trader)
単純なグリッドや移動平均戦略ではありません。コア脳（DeepSeek LLM）が、資金、テクニカル、マクロ、レバレッジ、ポートフォリオの6次元マルチモーダル情報を統合し、取引実行時に**取引ロジック (Rationale)** と **リスク管理プラン (Exit Plan)** を自動生成します。
*   **OKX V5 統合アカウント対応**: ロング/ショート両方向の契約取引、動的レバレッジ計算、リアルタイムの含み損益 (uPnL) 監視を自動で処理します。
*   **OCO 注文内蔵**: 取引ごとに OKX へ利確・損切りの条件付き注文を自動送信し、ドローダウンを厳格に管理します。
*   **ナラティブ検証 & シナリオ選択**: ニュースが「織り込み済み」かどうかを判断させ、「トレンドフォロー」「平均回帰」「クジラ先回り」の3つのシナリオから最適なものを選択させます。
*   <font color="red">**歴史的自己反省**</font>: AI は取引前に過去の判断と収益パフォーマンスを分析し、現在のリスク許容度を動的に調整します。

### 2. 六次元の全方位感知 (Multi-Dimensional Perception)
モデルは4時間ごとに以下のデータを読み込み、深い考察を行います：
*   **🐋 オンチェーンフロー**: クジラの取引額、ステーブルコイン/トークンの純流入・流出を追跡 (Moralis & Solana Helius API 経由)。
*   **📊 テクニカル指標エンジニアリング**: 生の価格データだけでなく、RSI、ADX、MACD、および **星評価システム (Star Ratings)** (価格帯、出来高異常、RSI極値に基づく0〜3の評価) を使用します。
*   **💸 デリバティブ清算**: ロング/ショートの強制ロスカットデータを監視し、ショートスクイーズの機会を探ります。
*   **🌍 マクロ経済 (Macro)**: FRB 利下げ予測 (Fed Futures)、ドル指数 (DXY)、米10年債利回り (US10Y)、VIX 指数、円キャリートレードの影響、恐怖強欲指数をシームレスに統合。
*   **📰 ニュース・センチメント**: 主要なクリプトニュースをリアルタイムで収集し、センチメント分析を行います。

### 3. 高度なリスク管理と取引規律 (Tactical Discipline)
仮想通貨市場の高ボラティリティに対応するため、Dolores は厳格な「戦場の規律」を設けています：
*   **流動性ラッシュ回避 (Anti-Liquidity Rush)**: 一方的なロスカット連鎖 (>3倍比率) や垂直的な価格変動時は、ロスカットを「燃料」と見なし、ボラティリティが収まるまで逆張りを禁止します。
*   **右側エントリーロジック (Wick Confirmation)**: クジラの警告が出ても、長いヒゲ (Wick Ratio) などの反転パターンや、価格のブレイクアウトを待ってからエントリーします。
*   **デリバティブ・トラップチェック**: 資金調達率 (Funding Rate) と未決済建玉 (OI) を深く監視。費率が極端 (>0.03% または <-0.01%) な場合は「混雑したトレード」と見なし、スクイーズを避けるためエントリーを強制停止します。
*   **コア・ポジション管理**:
    - **動的エクスポージャー上限**: BTC SMA200 に基づく市場相場 (Regime) に応じて、ロング/ショートの総上限をリアルタイムで割り当てます (例: 強気相場ではロング上限 98%、弱気相場では 40%)。
    - **ボラティリティ調整レバレッジ**: 恐怖強欲指数と連動。市場が極端な状態 (<20 または >80) では、レバレッジを 2倍に強制制限する「防御モード」を発動します。
    - **スロット制限**: 同時に保有できるポジションを 3つに制限し、特定の通貨へのリスク集中を防ぎます。

### 4. データ層と展開アーキテクチャの分離 (V2.0 更新)
*   **クラウドネイティブ MongoDB**: GitHub のコミットによる同期から脱却しました。実行ログ、ポートフォリオの状態、市場判断はすべてミリ秒単位で MongoDB に保存されます。
*   **サーバーレスフロントエンド**: React/TypeScript で構築され、Vercel でデプロイ。サイバーパンク風のレイアウト、多言語対応 (i18n)、リアルタイム収益曲線、AI 分析レポートを提供します。
*   **自動化コンテナスケジューリング**: Railway 等のクラウドプラットフォームで動作。4時間足の確定時刻 (0時, 4時, 8時...) に合わせて、感知・分析・取引のループを実行します。

### 5. 多チャネル・リアルタイム報
*   Telegram (HTML レンダリング) および Discord 通信を統合。AI の判断理由、注文、決済、重大な市場変化が即座にスマートフォンに届きます。

---

# 🛠️ 技術スタックとアーキテクチャ

### **Backend (Python 3.10+)**
*   **`ai_trader.py`**: 脳。DeepSeek API 向けに複雑なプロンプトを構築し、意思決定を行います。
*   **`crypto_brain.py`**: 情報局。Moralis、マクロ、ニュース等の外部 API データを統合します。
*   **`technical_analysis.py`**: 計算エンジン。RSI、ADX、星評価、流動性指標を計算します。
*   **`okx_executor.py`**: 実行エンジン。OKX V5 API の署名、注文、認証を処理します。
*   **`db_client.py`**: 永続化エンジン。MongoDB との状態管理を担当します。
*   **`run_loop.py`**: スケジューラー。K線確定時刻にワークフローを起動します。

---

# 🚀 クイックスタート & デプロイガイド

初心者の型でもスムーズに開始できるように、以下の手順に従ってください。

### 0. 準備するもの (Prerequisites)
1.  **Python 3.10+**: [ダウンロード](https://www.python.org/downloads/)
2.  **Node.js 18+**: [ダウンロード](https://nodejs.org/)
3.  **MongoDB 环境**: 無料の [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) の使用を推奨します。

---

### 1. 環境変数の設定 (`.env`)
`backend` ディレクトリに `.env` という名前のファイルを作成し、以下を記入してください。

| 変数名 | 取得元 (Source) | 説明 |
| :--- | :--- | :--- |
| `OKX_API_KEY` | [OKX API ページ](https://www.okx.com/account/my-api) | 「取引」権限を有効にしてください |
| `DEEPSEEK_API_KEY` | [DeepSeek 開発プラットフォーム](https://platform.deepseek.com/) | 少量のリポジトリチャージを推奨 |
| `MONGODB_URI` | [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) | `mongodb+srv://...` 形式の接続文字列 |
| `MORALIS_API_KEYS` | [Moralis Admin](https://admin.moralis.io/) | オンチェーン資金監視用 |
| `SOLANA_API_KEYS` | [Helius](https://www.helius.dev/) | Solana データ取得用 |

---

### 2. バックエンドエンジンの起動
```bash
cd backend
# 1. 仮想環境の作成 (推奨)
python3 -m venv venv
source venv/bin/activate  # Windows ユーザーは venv\Scripts\activate

# 2. 依存関係のインストール (2-3 分かかります)
pip install -r requirements.txt

# 3. メインプログラムの実行
python run_loop.py
```

---

### 3. フロントエンドダッシュボードの起動
```bash
cd frontend
# 1. 依存関係のインストール
npm install

# 2. 開発サーバーの起動
npm run dev
# http://localhost:3000 でダッシュボードを確認できます
```

---

### 4. クラウドデプロイ (Railway & Vercel)
*   **バックエンド (Railway)**: GitHub リポジトリを Railway に連携すると、自動的にスクリプトが認識されます。Railway パネルで `.env` の内容を設定してください。
*   **フロントエンド (Vercel)**: `frontend` ディレクトリを Vercel に連携すると、自動的にビルドとデプロイが行われます。

---

# ☕️ お茶代をサポート (Buy Me a Coffee)

Star ⭐ とフォローありがとうございます！更新は随時行われます。
作者の連絡先はホームページにあります。質問があればいつでもご連絡ください。
他のプロジェクトもぜひチェックしてください。PR や Issue も大歓迎です！
スポンサーありがとうございます！もしこのプロジェクトがお役に立ちましたら、ミルクティー一杯分のご支援をお願いします~~（一日中ハッピーになります 😊😊）
thank you~~~

| Alipay (アリペイ) | Solana (SOL/USDC) |
| :---: | :---: |
| <img src="frontend/public/alipay_qr.png" width="200" /> | <img src="frontend/public/sol_qr.png" width="200" /> |
| `newjowu@gmail.com` | `2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY` |

### 🚀 Solana Blink (ワンクリック決済)
Blink 対応ウォレット (Phantom/Backpack 等) をお使いの方は、以下のリンクから直接寄付できます：
[Solana で寄付する](https://www.dial.to/?action=solana-action:https://action.solscan.io/api/donate?receiver=2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY)

---
*サポートに感謝します！寄付金はサーバー代と DeepSeek API の費用に充てられます。*

# 🛡️ リスク警告 (Disclaimer)
仮想通貨市場の極端な状況下では、いかなる高度なロジックでも資産損失の可能性があります。本プロジェクトは学習・デモ目的であり、**REAL 模式 (実盤)** での運用による損失について作者は一切の責任を負いません。まずはペーパートレードでのテストを強く推奨します。
