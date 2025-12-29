#!/usr/bin/env python3
"""
migration_test_runner.py

功能：
1) 统计 Experiment/RQ2/Top_ERC20/augmented_test_case 目录中每个合约增强的测试用例数量（统计文件数与 it() 出现次数）。
2) 统计 Experiment/RQ2/Top_ERC20/migrated_test_case 目录中迁移结果（读取 *_result.json 若有），并统计每个迁移目录的测试文件数量。
3) 将 migrated_test_case 中的测试文件复制到 Code/TestExecutor/test（避免重名），并替换常见旧依赖名为 `@nomicfoundation` 版本。
4) 可选运行每个复制后的测试文件：在 `Code/TestExecutor` 下使用 `npx hardhat test test/<file>`，检查输出中是否包含关键词 `passing`（不区分大小写）。
5) 将所有结果汇总为 JSON 并保存到 `Experiment/RQ2/Top_ERC20/migration_test_summary.json`。

用法：
  python3 migration_test_runner.py [--copy] [--run-tests] [--dry-run]
  默认只做统计（不复制、不运行）。

"""
import os
import re
import json
import shutil
import subprocess
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / 'Experiment' / 'RQ2' / 'Top_ERC20'
AUG_DIR = EXP_DIR / 'augmented_test_case'
MIG_DIR = EXP_DIR / 'migrated_test_case'
TEST_EXECUTOR_TEST_DIR = ROOT / 'Code' / 'TestExecutor' / 'test'
SUMMARY_PATH = EXP_DIR / 'migration_test_summary.json'


def count_tests_in_file(p: Path):
    try:
        text = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return 0
    # Count 'it(' occurrences as approximate test-case count
    it_count = len(re.findall(r"\bit\s*\(", text))
    return it_count


def gather_augmented_stats():
    stats = {}
    if not AUG_DIR.exists():
        return stats
    for child in sorted(AUG_DIR.iterdir()):
        if child.is_dir():
            # Count numeric test case files like 0.json, 1.json, ... (ignore *_result.json and *_assertion.json)
            json_files = [p for p in child.iterdir() if p.is_file() and p.suffix == '.json']
            case_ids = []
            result_files = []
            assertion_files = []
            for p in json_files:
                name = p.name
                if re.match(r'^\d+\.json$', name):
                    case_ids.append(name.split('.')[0])
                elif name.endswith('_result.json'):
                    result_files.append(name)
                elif name.endswith('_assertion.json'):
                    assertion_files.append(name)
            stats[child.name] = {
                'path': str(child),
                'test_case_count': len(case_ids),
                'case_ids': sorted(case_ids, key=lambda x: int(x)),
                'result_files': result_files,
                'assertion_files': assertion_files,
            }
    return stats


def gather_migrated_stats():
    stats = {}
    if not MIG_DIR.exists():
        return stats
    for child in sorted(MIG_DIR.iterdir()):
        if child.is_dir():
            # identify case json files (numeric), migrated test js files (*.test.js), and result files
            json_files = [p for p in child.iterdir() if p.is_file() and p.suffix == '.json']
            case_ids = []
            result_files = {}
            for p in json_files:
                name = p.name
                if re.match(r'^\d+\.json$', name):
                    case_ids.append(name.split('.')[0])
                elif name.endswith('_result.json'):
                    try:
                        txt = p.read_text(encoding='utf-8', errors='ignore').strip()
                        if txt:
                            result_files[p.name] = json.loads(txt)
                        else:
                            result_files[p.name] = None
                    except Exception:
                        result_files[p.name] = None

            test_js_files = [p.name for p in child.glob('*.test.js') if p.is_file()]

            stats[child.name] = {
                'path': str(child),
                'case_count': len(case_ids),
                'case_ids': sorted(case_ids, key=lambda x: int(x)),
                'test_js_files': test_js_files,
                'test_js_count': len(test_js_files),
                'result_files': result_files,
            }
    return stats


def make_unique_target_name(target_dir: Path, base_name: str):
    candidate = base_name
    i = 1
    while (target_dir / candidate).exists():
        candidate = f"{base_name.rsplit('.',1)[0]}_{i}.js"
        i += 1
    return candidate


def normalize_requires(text: str):
    # Replace common old package names to @nomicfoundation variants
    replacements = {
        "@nomiclabs/hardhat-ethers": "@nomicfoundation/hardhat-ethers",
        "@nomiclabs/hardhat-waffle": "@nomicfoundation/hardhat-chai-matchers",
        "@nomicfoundation/hardhat-chai-matchers": "@nomicfoundation/hardhat-chai-matchers",
        "@nomicfoundation/hardhat-ethers": "@nomicfoundation/hardhat-ethers",
        "@nomicfoundation/hardhat-network-helpers": "@nomicfoundation/hardhat-network-helpers",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def copy_migrated_tests(summary, dry_run=True):
    TEST_EXECUTOR_TEST_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for folder, info in summary['migrated'].items():
        src_dir = Path(info['path'])
        for fname in info.get('test_js_files', []):
            src = src_dir / fname
            if not src.exists():
                continue
            try:
                text = src.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            new_text = normalize_requires(text)
            base_name = f"{folder}__{src.name}"
            target_name = make_unique_target_name(TEST_EXECUTOR_TEST_DIR, base_name)
            target_path = TEST_EXECUTOR_TEST_DIR / target_name
            if dry_run:
                copied.append({'src': str(src), 'target': str(target_path), 'written': False})
            else:
                target_path.write_text(new_text, encoding='utf-8')
                copied.append({'src': str(src), 'target': str(target_path), 'written': True})
    return copied


def run_test_on_file(target_path: Path, timeout=300):
    # run `npx hardhat test test/<filename>` in Code/TestExecutor dir
    cwd = ROOT / 'Code' / 'TestExecutor'
    rel = Path('test') / target_path.name
    cmd = ['npx', 'hardhat', 'test', str(rel), '--no-compile']
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or '') + '\n' + (proc.stderr or '')
        passed = bool(re.search(r"\bpassing\b", out, flags=re.IGNORECASE))
        return {'returncode': proc.returncode, 'passed_keyword_passing': passed, 'output': out}
    except subprocess.TimeoutExpired as e:
        return {'returncode': None, 'passed_keyword_passing': False, 'output': f'Timeout after {timeout}s'}
    except Exception as e:
        return {'returncode': None, 'passed_keyword_passing': False, 'output': str(e)}


def main(args):
    res = {}
    res['augmented'] = gather_augmented_stats()
    res['migrated'] = gather_migrated_stats()

    print(f"Found {len(res['augmented'])} augmented contract dirs, {len(res['migrated'])} migrated dirs")

    # Copy tests if requested
    copied = []
    if args.copy or args.run_tests:
        copied = copy_migrated_tests(res, dry_run=args.dry_run)
        print(f"Prepared {len(copied)} test files (dry_run={args.dry_run})")

    test_results = []
    if args.run_tests and not args.dry_run:
        for item in copied:
            target = Path(item['target'])
            r = run_test_on_file(target)
            test_results.append({'target': str(target), **r})
            print(f"Ran {target.name}: passed_keyword_passing={r['passed_keyword_passing']} returncode={r['returncode']}")

    summary = {
        'augmented_stats': res['augmented'],
        'migrated_stats': res['migrated'],
        'copied_files': copied,
        'test_results': test_results,
    }

    try:
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(f"Saved summary to {SUMMARY_PATH}")
    except Exception as e:
        print(f"Failed to write summary: {e}")

    # 打印统计表格
    def print_summary_table(summary):
        aug = summary.get('augmented_stats', {})
        mig = summary.get('migrated_stats', {})
        copied = summary.get('copied_files', [])
        results = summary.get('test_results', [])

        total_aug_dirs = len(aug)
        total_aug_js = sum(v.get('js_file_count', 0) for v in aug.values())
        total_aug_its = sum(v.get('it_count', 0) for v in aug.values())

        total_mig_dirs = len(mig)
        total_mig_js = sum(v.get('js_file_count', 0) for v in mig.values())
        total_mig_its = sum(v.get('it_count', 0) for v in mig.values())

        total_copied = len(copied)
        total_tests_run = len(results)
        tests_passed = sum(1 for r in results if r.get('passed_keyword_passing'))
        tests_failed = total_tests_run - tests_passed

        # 打印每个增强合约的行
        print('\nAugmented contracts:')
        print('-' * 80)
        print(f"{'Contract':40} | {'#cases':>6} | {'#results':>8} | {'#asserts':>8}")
        print('-' * 80)
        visible_aug = 0
        for name, info in aug.items():
            cases = info.get('test_case_count', 0)
            results_count = len(info.get('result_files', []))
            asserts_count = len(info.get('assertion_files', []))
            # skip rows where all counts are zero
            if cases == 0 and results_count == 0 and asserts_count == 0:
                continue
            visible_aug += 1
            # display only the contract name before the first underscore (omit address)
            display_name = name.split('_')[0] if '_' in name else name
            print(f"{display_name:40} | {cases:6d} | {results_count:8d} | {asserts_count:8d}")

        # 打印每个迁移对的行（源_to_目标）
        print('\nMigrated pairs:')
        print('-' * 120)
        print(f"{'Pair (source->target)':60} | {'#cases':>6} | {'#test.js':>8} | {'#result files':>12}")
        print('-' * 120)
        visible_mig = 0
        for name, info in mig.items():
            cases = info.get('case_count', 0)
            test_js = info.get('test_js_count', 0)
            result_files = len(info.get('result_files', {}))
            # skip rows where all counts are zero
            if cases == 0 and test_js == 0 and result_files == 0:
                continue
            visible_mig += 1
            parts = name.split('_')
            if len(parts) >= 3:
                src = parts[0]
                dst = parts[2]
                pair = f"{src} -> {dst}"
            else:
                pair = name
            print(f"{pair:60} | {cases:6d} | {test_js:8d} | {result_files:12d}")

        # 总计
        print('\nTotals:')
        print('-' * 40)
        print(f"Total augmented contracts (all): {total_aug_dirs}")
        print(f"Total augmented contracts (visible): {visible_aug}")
        print(f"Total augmented test cases: {sum(v.get('test_case_count',0) for v in aug.values())}")
        print(f"Total migrated pairs (all): {total_mig_dirs}")
        print(f"Total migrated pairs (visible): {visible_mig}")
        print(f"Total migrated test cases: {sum(v.get('case_count',0) for v in mig.values())}")
        print(f"Total copied files: {total_copied}")
        print(f"Total tests executed: {total_tests_run}")
        print(f"Tests passed (keyword 'passing'): {tests_passed}")
        print(f"Tests failed/other: {tests_failed}")

    print_summary_table(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--copy', action='store_true', help='Copy migrated tests into Code/TestExecutor/test')
    parser.add_argument('--run-tests', action='store_true', help='Run tests after copying')
    parser.add_argument('--dry-run', action='store_true', help='Do not write files when copying (just simulate)')
    args = parser.parse_args()
    main(args)
