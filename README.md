# SolMigrator — 复现与使用说明

本文档为复现与运行本仓库中迁移/测试自动化工具的说明。请按顺序完成环境配置、依赖安装与运行步骤。

---

## 环境配置

- 操作系统：Linux 5.15.167.4-microsoft-standard-WSL2
- Python：3.10.19
- Node.js：v22.21.1
- npm / npx：随 Node.js 安装。

推荐安装 `nvm` 并切换 Node 版本：

```bash
# 安装 nvm（若未安装）
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.5/install.sh | bash
# 重新加载 shell 后安装并使用最新稳定版 Node
nvm install --lts
nvm use --lts
node -v
npm -v
```

---

## 安装依赖

1. Python 依赖

```bash
cd ./Code/Src && python -m pip install
# 1. 卸载错误的 slither 包
pip uninstall -y slither

# 2. 安装正确的 slither-analyzer 包
pip install slither-analyzer

```

1. Node / Hardhat 项目依赖

```bash
cd ./Code/Src/Hardhat
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox 
cd ./Code/TestExecutor
npm install
npm install --save-dev @nomicfoundation/hardhat-toolbox
```

---

## 复现实验说明（RQ1 / RQ2 / RQ3）

下面给出复现论文中三个研究问题（RQ1、RQ2、RQ3）结果的命令示例。所有命令均在仓库根目录下相对路径运行（多数命令需要网络/API Key 与 Geth Archive 节点）。

通用前提：
- 需要在 Etherscan 注册并获取 `ETHERSCAN_API_KEY`。
- 需要一个 Geth Archive 节点或其他支持 `debug_traceTransaction` 的 JSON-RPC 提供者，记录为 `GETH_ARCHIVE_PROVIDER`（例如 `http://localhost:8545`）。（我们使用的是quiknode）

### RQ1（增强测试用例）

```bash
cd Code/Src
python3 main.py augment \
	--contract_folder ../../Experiment/RQ1/ \
	--augmentation_folder ../../Experiment/RQ1/ \
	--etherscan_api YOUR_ETHERSCAN_API_KEY \
	--http_provider YOUR_GETH_ARCHIVE_PROVIDER
```

该命令会对 `Experiment/RQ1` 中的数据集（论文中的 Dataset1）执行测试增强，并将增强结果（JSON 测试用例与执行痕迹）保存在 `Experiment/RQ1/` 下相应目录。

### RQ2（迁移与评估 — ERC20/Top 集）

先进行增强（如果尚未完成）：

```bash
cd Code/Src
python3 main.py augment \
	--contract_folder ../../Experiment/RQ2/Top_ERC20/ \
	--augmentation_folder ../../Experiment/RQ2/Top_ERC20/ \
	--etherscan_api YOUR_ETHERSCAN_API_KEY \
	--http_provider YOUR_GETH_ARCHIVE_PROVIDER
```

然后执行迁移（将增强的测试迁移到目标合约对）：

```bash
cd Code/Src
python3 main.py migrate \
	--contract_folder ../../Experiment/RQ2/Top_ERC20/ \
	--augmentation_folder ../../Experiment/RQ2/Top_ERC20/ \
	--migration_folder ../../Experiment/RQ2/Top_ERC20/ \
	--etherscan_api YOUR_ETHERSCAN_API_KEY \
	--http_provider YOUR_GETH_ARCHIVE_PROVIDER
```

迁移结果会写入 `Experiment/RQ2/Top_ERC20/migrated_test_case/`，每个子目录以 `sourceTarget` 命名，包含 `.json`、`_result.json`、以及可能的 `*.test.js`。

若仅想迁移指定源-目标对，可加 `--source` 与 `--target` 参数，例如：

```bash
python3 main.py migrate \
	--contract_folder ../../Experiment/RQ2/Top_ERC20/ \
	--augmentation_folder ../../Experiment/RQ2/Top_ERC20/ \
	--migration_folder ../../Experiment/RQ2/Top_ERC20/ \
	--source CroToken_0xa0b73e1ff0b80914ab6fe0444e65848c4c34450b \
	--target FetchToken_0xaea46A60368A7bD060eec7DF8CBa43b7EF41Ad85 \
	--etherscan_api YOUR_ETHERSCAN_API_KEY \
	--http_provider YOUR_GETH_ARCHIVE_PROVIDER
```

### RQ3（基于迁移结果的对比评估）

RQ3 的评估依赖于 RQ2 的迁移输出与真实链上交易的比对（结果 CSV 存放在 `Experiment/RQ3/`）。复现流程：


复制 RQ2 中迁移成功的交易路径 `*.test.js` 到 `Code/TestExecutor/test` 并执行 `npx hardhat test`

## 批量脚本

编写了一个自动化脚本，可完成RQ2和RQ3的统计、复制、运行测试。
脚本位置：`tools/migration_test_runner.py`。

基本示例：仅统计（不修改任何文件）：

```bash
python3 tools/migration_test_runner.py --dry-run
```

复制迁移目录中的 `*.test.js` 到 `Code/TestExecutor/test`（会写文件，但不运行测试）：

```bash
python3 tools/migration_test_runner.py --copy
```

复制并运行测试（注意：会修改 `Code/TestExecutor/test`，并对每个复制的文件执行 `npx hardhat test`，可能耗时并受本地 Node/Hardhat 配置影响）：

```bash
python3 tools/migration_test_runner.py --copy --run-tests
```

运行选项说明：
- `--dry-run`：模拟复制，不写文件。也会生成汇总 JSON（dry-run 也会尝试写 summary）。
- `--copy`：把 `migrated_test_case` 内的 `*.test.js` 复制到 `Code/TestExecutor/test`，目标文件名会以迁移目录名为前缀以避免重名。
- `--run-tests`：在 `--copy` 后执行，对每个复制的测试文件运行 `npx hardhat test`（使用 `Code/TestExecutor` 目录作为 cwd）。

输出：脚本会在运行结束后将汇总结果保存为：

`Experiment/RQ2/Top_ERC20/migration_test_summary.json`

并在控制台打印按合约与迁移对的表格统计。

---
