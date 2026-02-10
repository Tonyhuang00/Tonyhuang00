# Binance 合約交易機器人 (Python / PyCharm)

此專案提供一個固定策略的 Binance 合約交易機器人範例，支援：

- 顯示資金、持倉與狀態
- 連輸進入冷靜期（停止開倉）
- 連勝時增加下單本金
- 本金不足固定每單金額時，自動縮單為本金 0.9x

## 功能概覽

- **策略**：EMA 快慢線交叉（固定策略）
- **風控**：止盈、止損、連輸冷靜期
- **資金管理**：
  - 低於固定每單金額時，自動用 `balance * 0.9` 當作下單本金
  - 連勝時依比例增加下單本金

## 環境需求

- Python 3.10+
- PyCharm（或其他 IDE）

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

1. 複製設定檔並改名為 `config.json`

```bash
cp config.example.json config.json
```

2. 填入 Binance API 金鑰與交易參數

> 建議先使用 `use_testnet=true` 測試。

## 執行

```bash
python bot.py
```

## 注意事項

- 這是教學示範用途，請先在測試網環境驗證。
- 交易風險由使用者自行承擔。
